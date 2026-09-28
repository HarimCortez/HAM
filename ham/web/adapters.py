"""Adapters for two commands S3b is also expected to add (`church_profile.update`,
`outbox.retry` — see the build note in this slice's task list: "S3b adds the command — same
adapter approach"). The screens need to work end-to-end now, so each function below is a
real, working `@command`-wrapped implementation using the shared pipeline
(`ham.authz.commands`), kept in `ham.web` (rather than `ham.platform`/`ham.outbox`) precisely
so it doesn't collide with a file S3b is also editing.

**Merge note:** if S3b lands an equivalent command in `ham.platform.services` /
`ham.outbox.services` (or elsewhere), delete the duplicate here and have the two view modules
that import these (`ham.web.views_admin_settings`) call the shared one instead. Keep the
call signatures (`ctx, **fields` / `ctx, *, delivery_id`) so that swap is a one-line change.
"""

from __future__ import annotations

import uuid

from ham.authz.commands import CommandResult, command
from ham.authz.context import ActorContext
from ham.outbox import services as outbox_services


@command("church_profile.update")
def update_church_profile(
    ctx: ActorContext,
    *,
    ham_phone: str = "",
    ham_email: str = "",
    time_zone: str = "",
    website_url: str = "",
) -> CommandResult:
    """foundation.md §7 `POST /admin/settings/church` (Administrator, step 1 owner: S3b per
    the task list, but wired here so the screen works now)."""
    from ham.platform.models import ChurchProfile

    profile = ChurchProfile.objects.select_for_update().get(pk=ChurchProfile.get_solo().pk)
    before = {
        "ham_phone": profile.ham_phone,
        "ham_email": profile.ham_email,
        "time_zone": profile.time_zone,
        "website_url": profile.website_url,
    }
    profile.ham_phone = ham_phone
    profile.ham_email = ham_email
    profile.time_zone = time_zone
    profile.website_url = website_url
    profile.updated_by_id = ctx.user_id
    profile.save(update_fields=["ham_phone", "ham_email", "time_zone", "website_url", "updated_at"])
    after = {
        "ham_phone": ham_phone,
        "ham_email": ham_email,
        "time_zone": time_zone,
        "website_url": website_url,
    }
    return CommandResult(
        value=profile,
        audit_action="church_profile.updated",
        target_type="church_profile",
        target_id=str(profile.pk),
        before=before,
        after=after,
    )


@command("outbox.retry")
def retry_outbox_delivery(ctx: ActorContext, *, delivery_id: uuid.UUID | str) -> CommandResult:
    """foundation.md §7 `POST /admin/integrations/deliveries/<id>/retry`."""
    outbox_services.retry_delivery(delivery_id)
    return CommandResult(
        value=None,
        audit_action="outbox.retried",
        target_type="outbox_delivery",
        target_id=str(delivery_id),
    )
