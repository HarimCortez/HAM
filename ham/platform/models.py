"""`platform_church_profile`: the one Admin-editable row of church contact info
(foundation.md §3 "ChurchProfile", Q-026, Q-030). Brand fields (name, logos, fonts) live in
`brand.json` (see `ham.platform.brand`), never in the database.
"""

from __future__ import annotations

import uuid

from django.db import models

from ham.platform.ids import UUID7Field

# Fixed id for the singleton row (foundation.md: "singleton row"). A real primary key (rather
# than always querying "the first row") keeps concurrent get_or_create() calls race-free.
CHURCH_PROFILE_SINGLETON_ID = uuid.UUID("00000000-0000-7000-8000-000000000001")

# Q-030 default, used only until an Administrator sets it via `church_profile.update`
# (that audited command lands with S3a/S5; this app only owns the row and the read service).
DEFAULT_TIME_ZONE = "America/New_York"

# Q-112 (intake.md §8): "Days offered come from a church-profile 'days HAM serves' setting,
# default Sunday-Friday." Stored as ISO weekday numbers (1=Monday..7=Sunday) so the public
# intake form's availability question (`ham.requester_portal.forms`) can render church-local
# weekday choices without hard-coding them a second time anywhere (CLAUDE.md "no magic
# numbers"). Default is Sunday(7)-Friday(1-5): every day except Saturday(6).
DEFAULT_SERVES_DAYS: tuple[int, ...] = (1, 2, 3, 4, 5, 7)


def default_serves_days() -> list[int]:
    return list(DEFAULT_SERVES_DAYS)


class ChurchProfile(models.Model):
    id = UUID7Field()
    ham_phone = models.CharField(max_length=32, blank=True, default="")
    ham_email = models.EmailField(blank=True, default="")
    time_zone = models.CharField(max_length=64, default=DEFAULT_TIME_ZONE)
    website_url = models.URLField(blank=True, default="")
    # Q-112: ISO weekday numbers (1=Monday..7=Sunday) HAM serves requesters on. Used only to
    # populate the public intake form's availability choices — never an authorization or
    # staffing/scheduling rule.
    serves_days = models.JSONField(default=default_serves_days)
    updated_at = models.DateTimeField(auto_now=True)
    # Not a ForeignKey yet: ham.identity.User (S3a) doesn't exist in this slice. The audited
    # `church_profile.update` command (S3a's @command pipeline) will populate this from
    # ActorContext once it lands.
    updated_by_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "platform_church_profile"
        verbose_name = "Church profile"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Church profile ({self.ham_email or 'unset'})"

    @classmethod
    def get_solo(cls) -> ChurchProfile:
        """Return the singleton row, creating it with defaults on first use."""
        obj, _created = cls.objects.get_or_create(pk=CHURCH_PROFILE_SINGLETON_ID)
        return obj
