"""Leadership email + in-app builders (PRD §35, §10; intake.md §6 "Who is notified";
docs/ux/intake.md §7 rows L-E1/L-E2/L-E3). Registered once from `RequestsConfig.ready()`,
onto the shared `ham.integrations.email.notifications` and `ham.notifications.inapp`
subscribers -- the same pattern `ham.identity.notifications` already uses for email, and
`ham.requests.attention` already uses for `ham.notifications`' registries.

Subjects/titles carry only the HAM #, category and the urgent flag -- never a requester name,
address, description or ZIP (§68; intake-contracts.md §6). Recipients are resolved through
`ham.identity.services.notification_recipients` (the one place auth tables are read,
intake-contracts.md §7), never by this module reading `User`/`RoleAssignment` itself.

**Duplicate flagged (Q-115):** no separate notification -- `request.duplicates_flagged` is an
audit event only; leaders see it on the request detail page's duplicate panel
(`request.history.view`, L2) the moment they open a request already in Awaiting Approval, so a
second alert would just repeat the same information already on L-E1/L-E2 (documented decision,
not a silent omission).
"""

from __future__ import annotations

from django.conf import settings

from ham.authz import roles
from ham.identity.services import notification_recipients
from ham.integrations.email.notifications import NotificationEmail, register_notification
from ham.notifications.inapp import InAppNotice, register_inapp
from ham.outbox.models import OutboxEvent

_PAS_BRD_DIR_AD = (
    roles.PASTOR,
    roles.BOARD_REPRESENTATIVE,
    roles.HAM_DIRECTOR,
    roles.ASSISTANT_DIRECTOR,
)
_DIR_AD = (roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR)


def _request_row(request_id):
    from .models import AssistanceRequest
    from .states import RequestStatus

    request = AssistanceRequest.objects.filter(id=request_id).first()
    if request is None:
        return None
    return request, RequestStatus(request.status)


def _deep_link(request_id) -> str:
    base = str(settings.HAM_BASE_URL).rstrip("/")
    return f"{base}/requests/{request_id}"


def _category_label(request) -> str:
    from .models import NeedCategory

    try:
        return NeedCategory(request.need_category).label
    except ValueError:  # pragma: no cover - defensive; every stored value is a valid choice
        return request.need_category


# ---------------------------------------------------------------------------------------
# L-E3: "Phone check needed" (RequestSubmitted, only when it lands in NEEDS_PHONE_CHECK)
# ---------------------------------------------------------------------------------------
def _phone_check_recipients_and_row(event: OutboxEvent):
    row = _request_row(event.aggregate_id)
    if row is None:
        return None, None
    request, status = row
    from .states import RequestStatus as RS

    if status is not RS.NEEDS_PHONE_CHECK:
        # The email path (SUBMITTED) has no leadership notice of its own yet -- leaders are
        # told once the duplicate check finishes and the request reaches AWAITING_APPROVAL
        # (RequestAwaitingApproval, below).
        return None, None
    return request, notification_recipients(_DIR_AD)


def _build_needs_phone_check_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    request, recipients = _phone_check_recipients_and_row(event)
    if request is None or not recipients:
        return None
    urgent = bool(event.payload.get("urgent"))
    title = f"Phone check needed · {request.display_number}"
    return [
        InAppNotice(
            recipient_user_id=user_id,
            kind="request_needs_phone_check",
            subject_type="request",
            subject_id=request.id,
            title=title,
            urgent=urgent,
            requires_ack=urgent,
        )
        for user_id, _email, _notify_email in recipients
    ]


def _build_needs_phone_check_emails(event: OutboxEvent) -> list[NotificationEmail] | None:
    request, recipients = _phone_check_recipients_and_row(event)
    if request is None or not recipients:
        return None
    urgent = bool(event.payload.get("urgent"))
    subject = f"Phone check needed · {request.display_number}"
    text = (
        f"A request without an email address is waiting for a phone check: "
        f"{request.display_number}.\n\nOpen it: {_deep_link(request.id)}"
    )
    return [
        NotificationEmail(to=email, subject=subject, text_body=text, category="leader_update")
        for _user_id, email, notify_email in recipients
        # Q-133: urgent overrides the preference; everyone else only if they opted in.
        if urgent or notify_email
    ] or None


# ---------------------------------------------------------------------------------------
# L-E1 / L-E2: "Request waiting for review" / "Urgent request needs a pastor"
# (RequestAwaitingApproval)
# ---------------------------------------------------------------------------------------
def _awaiting_approval_notice(*, user_id, request, title: str, urgent: bool) -> InAppNotice:
    return InAppNotice(
        recipient_user_id=user_id,
        kind="request_awaiting_approval",
        subject_type="request",
        subject_id=request.id,
        title=title,
        urgent=urgent,
        requires_ack=urgent,
    )


def _build_awaiting_approval_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    urgent = bool(event.payload.get("urgent"))
    category = _category_label(request)
    if urgent:
        title = f"Urgent request needs a pastor · {request.display_number} {category}"
    else:
        title = f"Request waiting for review · {request.display_number} {category}"

    notices = [
        # Only pastors get the urgent, must-acknowledge banner (§10, §35); the Board rep and
        # Director/AD get the same wording as an ordinary, dismissable update either way
        # (intake-contracts.md §6 "DIR, AD: in-app update").
        _awaiting_approval_notice(user_id=user_id, request=request, title=title, urgent=urgent)
        for user_id, _email, _notify_email in notification_recipients((roles.PASTOR,))
    ]
    notices += [
        _awaiting_approval_notice(user_id=user_id, request=request, title=title, urgent=False)
        for user_id, _email, _notify_email in notification_recipients(
            (roles.BOARD_REPRESENTATIVE, *_DIR_AD)
        )
    ]
    return notices or None


def _build_awaiting_approval_emails(event: OutboxEvent) -> list[NotificationEmail] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    urgent = bool(event.payload.get("urgent"))
    category = _category_label(request)
    link = _deep_link(request.id)

    if urgent:
        subject = f"Urgent request needs a pastor · {request.display_number} {category}"
        text = (
            f"An urgent request is waiting for a pastor's review: {request.display_number} "
            f"({category}).\n\nOpen it: {link}"
        )
        # Q-123: every pastor, by email, regardless of their preference. Director/AD get an
        # in-app update only for this event (see `_build_awaiting_approval_notices`).
        emails = [
            NotificationEmail(to=email, subject=subject, text_body=text, category="leader_update")
            for _user_id, email, _notify_email in notification_recipients((roles.PASTOR,))
        ]
        return emails or None

    subject = f"Request waiting for review · {request.display_number} {category}"
    text = (
        f"A request is waiting for a decision: {request.display_number} ({category}).\n\n"
        f"Open it: {link}"
    )
    emails = [
        NotificationEmail(to=email, subject=subject, text_body=text, category="leader_update")
        for _user_id, email, notify_email in notification_recipients(_PAS_BRD_DIR_AD)
        if notify_email
    ]
    return emails or None


# ---------------------------------------------------------------------------------------
# RequestCancelled: in-app update to Director/AD (intake.md §6)
# ---------------------------------------------------------------------------------------
def _build_cancelled_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    title = f"Closed · {request.display_number}"
    return [
        InAppNotice(
            recipient_user_id=user_id,
            kind="request_cancelled",
            subject_type="request",
            subject_id=request.id,
            title=title,
        )
        for user_id, _email, _notify_email in notification_recipients(_DIR_AD)
    ] or None


def register() -> None:
    """Called once from `RequestsConfig.ready()`."""
    register_notification("RequestSubmitted", _build_needs_phone_check_emails)
    register_inapp("RequestSubmitted", _build_needs_phone_check_notices)
    register_notification("RequestAwaitingApproval", _build_awaiting_approval_emails)
    register_inapp("RequestAwaitingApproval", _build_awaiting_approval_notices)
    register_inapp("RequestCancelled", _build_cancelled_notices)


__all__ = ["register"]
