"""Inbox queries and the read/acknowledge services (intake.md §5/§6/§10, PRD §35).

"Needs response" is never a query against `Notification` — it is
`ham.notifications.attention.attention_items_for(ctx)` (computed live by every registered
provider). "Updates" and the urgent banner *are* `Notification` rows.

Marking something read is a personal bookkeeping action (like a page view, intake.md §9.8
"page views ... are not audited") scoped by ownership, not a `@command` — it changes nothing
anyone else can see and isn't consequential enough to audit. Acknowledging an urgent
notification *is* consequential (it is what makes the app-wide urgent banner go away for that
person, §10/§35), so it goes through the one write path with its own audit event.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

from ham.authz.commands import CommandResult, PermissionDenied, command
from ham.platform.clock import now as clock_now

from .attention import AttentionItem, attention_items_for
from .models import Notification


def needs_response_for(ctx: Any) -> list[AttentionItem]:
    """Every attention item for this actor, in provider registration order (a provider is
    expected to put urgent items first within its own contribution — intake.md §6 "urgent
    first"). Includes muted rows (intake.md §6: Director/AD see the same rows, muted, not
    excluded outright) — callers render `muted` items with de-emphasized styling."""
    return attention_items_for(ctx)


def needs_response_count(ctx: Any) -> int:
    """The Inbox/Home badge count: muted rows don't count (intake.md §6 "excluded from
    counts" — a Director/AD isn't the one who resolves a pastor's decision)."""
    return sum(item.count for item in attention_items_for(ctx) if not item.muted)


def updates_for(ctx: Any, *, limit: int = 50) -> list[Notification]:
    """The Inbox "Updates" list: this recipient's stored notifications, newest first."""
    return list(
        Notification.objects.filter(recipient_user_id=ctx.user_id).order_by("-created_at")[:limit]
    )


def unread_update_count(ctx: Any) -> int:
    return Notification.objects.filter(recipient_user_id=ctx.user_id, read_at__isnull=True).count()


def _unacknowledged_urgent_qs(ctx: Any):
    return Notification.objects.filter(
        recipient_user_id=ctx.user_id, requires_ack=True, acknowledged_at__isnull=True
    )


def urgent_banner_for(ctx: Any) -> Notification | None:
    """The app-wide urgent banner (§10, §35, Q-123): an urgent notification requiring
    acknowledgement stays until acknowledged, "regardless of the person's email preferences"
    — that override is about the *email* channel (`ham.identity.notifications`/S2.6 builders
    skip the `notify_email` check for these); this in-app query has no preference to check at
    all, it simply shows whatever is still unacknowledged."""
    return _unacknowledged_urgent_qs(ctx).order_by("-created_at").first()


def urgent_banner_count_for(ctx: Any) -> int:
    """Visual QA M12: the banner shows how many urgent items are waiting (e.g. "2 urgent
    requests need a pastor"), not only the newest one's own title -- acknowledging the shown
    one still leaves the rest for the next page load."""
    return _unacknowledged_urgent_qs(ctx).count()


def get_owned_notification(ctx: Any, notification_id: UUID) -> Notification | None:
    """Read-only counterpart to `mark_read` -- same ownership scoping (`ctx.user_id`), never
    mutates. N7: `ham.web.views.notification_open` uses this instead of `mark_read` while
    impersonating, so opening a notification link doesn't silently mark the *impersonated*
    person's own inbox item read on their behalf -- an unaudited state change on someone
    else's account that they'd have no way to notice happened."""
    return Notification.objects.filter(pk=notification_id, recipient_user_id=ctx.user_id).first()


def mark_read(ctx: Any, notification_id: UUID) -> Notification | None:
    """Ownership-scoped, not authorized by the matrix (route-level `shell.use` is enough — any
    signed-in leader may mark their own Updates read; the ownership filter below is what stops
    them reading someone else's). Idempotent; returns `None` if `notification_id` isn't this
    recipient's (never distinguishes "doesn't exist" from "isn't yours" — nothing to
    enumerate, notification ids are UUIDv7 and never shown to anyone but their recipient)."""
    notification = get_owned_notification(ctx, notification_id)
    if notification is None:
        return None
    if notification.read_at is None:
        notification.read_at = clock_now()
        notification.save(update_fields=["read_at"])
    return notification


def _resource_for_ack(ctx: Any, *, notification_id: UUID, **_: Any) -> Any:
    notification = Notification.objects.filter(pk=notification_id).first()
    if notification is None:
        # Scope.SELF treats a `None` resource as "nothing to check yet" and lets the service
        # body raise (see ham.authz.matrix._self_scope_ok) — the same pattern used elsewhere
        # for a resource that must be loaded to know whether it's owned.
        return None
    return SimpleNamespace(user_id=notification.recipient_user_id)


@command("notification.acknowledge", resource_from=_resource_for_ack)
def acknowledge_notification(ctx: Any, *, notification_id: UUID) -> CommandResult:
    notification = Notification.objects.select_for_update().filter(pk=notification_id).first()
    if notification is None:
        raise ValueError("notification not found")
    if notification.recipient_user_id != ctx.user_id:  # pragma: no cover - defensive re-check
        raise PermissionDenied("notification.acknowledge: not the recipient")
    if notification.acknowledged_at is None:
        notification.acknowledged_at = clock_now()
        notification.save(update_fields=["acknowledged_at"])
    return CommandResult(
        value=notification,
        audit_action="notification.acknowledged",
        target_type="notification",
        target_id=str(notification.id),
        after={"kind": notification.kind, "urgent": notification.urgent},
    )
