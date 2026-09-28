"""`audit_event`: append-only (foundation.md §3, PRD §58, §59, §70.6).

`seq` (bigserial) is the real primary key so ordering and pagination are cheap and
monotonic; `id` is a stable UUIDv7 used everywhere else (exports, detail links) so a leaked
sequence number never becomes a guessable "how many events exist" counter on its own — it is
combined with server-side authorization on every read.

DB triggers (see the second migration) refuse UPDATE always, and refuse DELETE unless the
transaction ran `SET LOCAL ham.audit_purge = 'on'` (only the retention job does that). The
Python-level guards below are defense in depth, not the actual control.
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import models

from ham.platform.ids import uuid7

ACTOR_TYPE_USER = "user"
ACTOR_TYPE_SYSTEM = "system"
ACTOR_TYPE_REQUESTER = "requester"
ACTOR_TYPE_CHOICES = (
    (ACTOR_TYPE_USER, "User"),
    (ACTOR_TYPE_SYSTEM, "System"),
    (ACTOR_TYPE_REQUESTER, "Requester"),
)


class AppendOnlyError(RuntimeError):
    """Raised by Python-level guards; the DB trigger is the real enforcement."""


class AuditEvent(models.Model):
    seq = models.BigAutoField(primary_key=True)
    id = models.UUIDField(default=uuid7, unique=True, editable=False)
    occurred_at = models.DateTimeField()

    actor_type = models.CharField(max_length=16, choices=ACTOR_TYPE_CHOICES)
    # The real person (the Administrator, when impersonating). Null only for actor_type=system.
    actor_user_id = models.UUIDField(null=True, blank=True)
    # Set only while impersonating: the effective identity being acted as.
    acting_as_user_id = models.UUIDField(null=True, blank=True)
    impersonation_id = models.UUIDField(null=True, blank=True)
    actor_roles = ArrayField(models.CharField(max_length=32), default=list, blank=True)

    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=64)
    target_id = models.CharField(max_length=64)
    project_id = models.UUIDField(null=True, blank=True)

    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    # request_id always; IP/user agent only for auth.* events (foundation.md §3: **S**).
    context = models.JSONField(default=dict, blank=True)
    rules_version = models.CharField(max_length=32)

    class Meta:
        db_table = "audit_event"
        indexes = [
            models.Index(fields=["occurred_at"], name="audit_occurred_at_idx"),
            models.Index(fields=["actor_user_id", "occurred_at"], name="audit_actor_idx"),
            models.Index(fields=["project_id", "occurred_at"], name="audit_project_idx"),
            models.Index(fields=["action", "occurred_at"], name="audit_action_idx"),
        ]
        ordering = ("-seq",)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"AuditEvent({self.action} #{self.seq})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError(
                "AuditEvent is append-only; use ham.audit.services.record() to create a new "
                "row, never update an existing one (PRD §58)."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError(
            "AuditEvent rows are never deleted except by the retention purge job "
            "(PRD §58, Q-036), which uses raw SQL with `SET LOCAL ham.audit_purge = 'on'`."
        )
