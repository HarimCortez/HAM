"""`record()`: the only way to create an `AuditEvent` (foundation.md §1 "One write path").

Called by `ham.authz.commands.command()` inside the same transaction as the change it
records. `bootstrap_administrator` (no signed-in actor exists yet) calls this directly with
`ctx=None` and an explicit system actor.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ham.platform.clock import now as clock_now
from ham.rules import RULES_VERSION

from .models import ACTOR_TYPE_REQUESTER, ACTOR_TYPE_SYSTEM, ACTOR_TYPE_USER, AuditEvent


def record(
    *,
    ctx: Any | None,
    action: str,
    target_type: str,
    target_id: str,
    project_id: UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    context: dict[str, Any] | None = None,
    actor_type: str | None = None,
    actor_user_id: UUID | None = None,
    acting_as_user_id: UUID | None = None,
    impersonation_id: UUID | None = None,
) -> AuditEvent:
    """Append one audit event (foundation.md §3). `ctx` is an `ActorContext`,
    `ham.authz.context.RequesterContext` or `ham.authz.context.SystemContext` (S2.0, intake.md
    §5/§6 "the audit principal branch for requester/system actors") — this module never
    imports `ham.authz` (layering: `ham.authz` -> `ham.audit`, never the reverse), so the
    branch below duck-types on `ctx.roles` rather than `isinstance`. Pass `ctx=None` only for
    actions with no `ActorContext` at all yet (e.g. `bootstrap_administrator`, before any
    `User` row exists) and supply `actor_type`/`actor_user_id` explicitly."""
    event_context = dict(context or {})
    if ctx is not None:
        ctx_roles = set(getattr(ctx, "roles", ()) or ())
        if "REQUESTER" in ctx_roles:
            # intake.md §5 "audit.record records actor_type = requester (with
            # context.link_id)": a requester has no `User` row (§3 `Requester` "not a User"),
            # so actor_user_id/acting_as_user_id/impersonation_id all stay null.
            actor_type = ACTOR_TYPE_REQUESTER
            actor_user_id = None
            acting_as_user_id = None
            impersonation_id = None
            actor_roles: list[str] = []
            link_id = getattr(ctx, "link_id", None)
            if link_id is not None:
                event_context.setdefault("link_id", str(link_id))
        elif "SYSTEM" in ctx_roles:
            actor_type = ACTOR_TYPE_SYSTEM
            actor_user_id = None
            acting_as_user_id = None
            impersonation_id = None
            actor_roles = []
        else:
            actor_type = ACTOR_TYPE_USER
            actor_user_id = ctx.real_user_id if ctx.is_impersonating else ctx.user_id
            acting_as_user_id = ctx.user_id if ctx.is_impersonating else None
            impersonation_id = ctx.impersonation_id
            actor_roles = sorted(ctx.roles)
    else:
        actor_type = actor_type or ACTOR_TYPE_SYSTEM
        actor_roles = []

    return AuditEvent.objects.create(
        occurred_at=clock_now(),
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        acting_as_user_id=acting_as_user_id,
        impersonation_id=impersonation_id,
        actor_roles=actor_roles,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        project_id=project_id,
        before=before,
        after=after,
        reason=reason,
        context=event_context,
        rules_version=RULES_VERSION,
    )
