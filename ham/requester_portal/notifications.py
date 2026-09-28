"""Requester-facing email builders (PRD §35, §60.3, §68; docs/ux/intake.md §7 "Emails and
notifications", rows E2/E2u/E3/E5/E6/E7). Registered once from
`RequesterPortalConfig.ready()`, onto the shared `ham.integrations.email.notifications`
subscriber, the same pattern `ham.identity.notifications` already uses.

Every requester email carries the request's secure link as a plain URL (Q-102) except the
verification code email, which `ham.requester_portal.verification` already sends immediately
(not through the outbox — "code email if not already done", S2.6: it was already done, S2.3).
Subjects and previews are neutral (Q-102): the HAM # at most, never a name, address,
category, hazard or status (§68).

This module resolves everything it needs itself, from the ids/codes on the `OutboxEvent`, via
plain (legal, downward) imports of `ham.requests` — this app sits *above* `ham.requests` in
the layers contract (`ham.web -> ham.requester_portal -> ham.media -> ham.requests -> ...`),
same as `services.py`'s own `submit_and_issue_link` already does.

**Coordination note (documented, not silently decided):** docs/ux/intake.md lists "new link"
(E3, after R11a "my link expired") and "find-my-request result" (E4, after R11b "check on my
request") as two differently-worded emails, but intake-contracts.md §7's route table sends
*both* flows through the same `requester_link.regenerate` action and the same
`RequesterAccessLinkIssued` (`kind="regenerated"`) outbox event — the event payload
(`request_id`, `link_id`, `kind`) carries nothing to tell the two origins apart, and adding one
would be a new payload field invented by this slice, not a documented contract. One builder
below (`_build_new_link_email`, E3's wording) therefore fires for every regenerated link,
covering both R11a and R11b's result email; flagged here for the coordinator, not a silent
default.
"""

from __future__ import annotations

from django.conf import settings

from ham.integrations.email.notifications import NotificationEmail, register_notification
from ham.outbox.models import OutboxEvent
from ham.platform.church import church_profile
from ham.platform.crypto import decrypt
from ham.rules import RULES

from .models import RequesterAccessLink


def _first_name(full_name: str) -> str:
    full_name = (full_name or "").strip()
    return full_name.split()[0] if full_name else "there"


def _current_link_url(request_id) -> str | None:
    """The requester's current live link, decrypted (Q-102: "every requester email carries
    the link"). `None` for a no-email (`NEEDS_PHONE_CHECK`) request, which never has one."""
    link = (
        RequesterAccessLink.objects.filter(request_id=request_id, revoked_at__isnull=True)
        .order_by("-issued_at")
        .first()
    )
    if link is None:
        return None
    token = decrypt(link.token_ciphertext)
    base = str(settings.HAM_BASE_URL).rstrip("/")
    return f"{base}/r/{token}"


def _request_and_requester(request_id):
    """Lazy import: `ham.requests` (S2.2) sits below this app in the layers contract, a legal
    downward import, kept lazy only to match this app's existing convention
    (`services.py`'s own cross-app calls) of not importing another app's models at module top
    before Django finishes loading every app."""
    from ham.requests.models import AssistanceRequest, Requester

    request = AssistanceRequest.objects.filter(id=request_id).first()
    if request is None:
        return None, None
    requester = Requester.objects.filter(request_id=request_id).first()
    return request, requester


# ---------------------------------------------------------------------------------------
# E2 / E2u: "We received your HAM request #047" (RequestSubmitted, email path only)
# ---------------------------------------------------------------------------------------
def _build_request_received_email(event: OutboxEvent) -> NotificationEmail | None:
    request, requester = _request_and_requester(event.aggregate_id)
    if request is None or requester is None:
        return None
    if requester.email is None:
        # Q-025 "I don't use email": R7N is shown in the browser; no email exists to send to
        # (this is also the NEEDS_PHONE_CHECK submission path for the same event type).
        return None

    link_url = _current_link_url(request.id)
    if link_url is None:  # pragma: no cover - defensive; issue_link always runs first
        return None

    church = church_profile()
    urgent_line = ""
    if request.urgent_requested:
        urgent_line = (
            "\n\nBecause this is urgent, we've let our pastors know right away. If anyone is "
            "in danger, call 911."
        )
    what_next = (
        "What happens next:\n"
        "1. Our pastors or Board review your request, usually within a few days.\n"
        "2. If it's approved, someone from HAM will call you to arrange a visit to look at "
        "the work."
        if not request.urgent_requested
        else "What happens next:\n"
        "1. A pastor reviews urgent requests as soon as they can.\n"
        "2. If it's approved, HAM's leaders will contact you quickly to arrange a visit."
    )
    text = (
        f"Thank you for reaching out, {_first_name(requester.full_name)}.\n\n"
        f"Your request number is {request.display_number}.\n\n"
        f"Open my request page: {link_url}"
        f"{urgent_line}\n\n"
        f"{what_next}\n\n"
        f"Questions? Call {church.phone} or email {church.email}."
    )
    return NotificationEmail(
        to=requester.email,
        subject=f"We received your {request.display_number}",
        text_body=text,
        category="request_received",
    )


# ---------------------------------------------------------------------------------------
# E3: "Your new link for HAM request #047" (RequesterAccessLinkIssued, kind="regenerated")
# ---------------------------------------------------------------------------------------
def _build_new_link_email(event: OutboxEvent) -> NotificationEmail | None:
    if event.payload.get("kind") != RequesterAccessLink.KIND_REGENERATED:
        return None
    request_id = event.payload.get("request_id") or event.aggregate_id
    request, requester = _request_and_requester(request_id)
    if request is None or requester is None or requester.email is None:
        return None

    link_url = _current_link_url(request.id)
    if link_url is None:  # pragma: no cover - defensive
        return None

    days = RULES.requester_access.REGENERATED_REQUESTER_LINK_LIFETIME.days
    text = (
        f"Here's your new link. Your old link no longer works. This link works for {days} "
        f"days.\n\nOpen my request page: {link_url}"
    )
    return NotificationEmail(
        to=requester.email,
        subject=f"Your new link for {request.display_number}",
        text_body=text,
        category="requester_new_link",
    )


# ---------------------------------------------------------------------------------------
# E5: "Update on your HAM request #047" -- more photos asked (RequestMediaBatchOpened, L11)
# ---------------------------------------------------------------------------------------
def _build_more_photos_email(event: OutboxEvent) -> NotificationEmail | None:
    from ham.media.models import RequestMediaBatch

    batch = RequestMediaBatch.objects.filter(id=event.aggregate_id).first()
    if batch is None:
        return None
    request, requester = _request_and_requester(batch.request_id)
    if request is None or requester is None or requester.email is None:
        return None

    link_url = _current_link_url(request.id)
    if link_url is None:  # pragma: no cover - defensive
        return None

    reason = batch.reason.strip() or "a closer look at the work"
    text = f"We'd like a few more photos: {reason}.\n\nOpen my request page: {link_url}"
    return NotificationEmail(
        to=requester.email,
        subject=f"Update on your {request.display_number}",
        text_body=text,
        category="requester_more_photos",
    )


# ---------------------------------------------------------------------------------------
# E6 / E7: "Update on your HAM request #047" -- closed before any decision (RequestCancelled)
# ---------------------------------------------------------------------------------------
_CANCEL_TEXT: dict[str, str] = {
    "requester_withdrew": (
        "As you asked, we've closed your request. You're always welcome to ask again."
    ),
    "duplicate_submission": (
        "We already have this same request from you, so we've closed this copy. Your other "
        "request is still open. If that's not right, please call us at {phone}."
    ),
}


def _build_closed_email(event: OutboxEvent) -> NotificationEmail | None:
    reason_code = event.payload.get("reason_code", "")
    template = _CANCEL_TEXT.get(reason_code)
    if template is None:
        # Q-107: spam/test gets no email at all; "couldn't reach them" (Q-140) only ever
        # applies to a no-email request, which has nothing to send to either way.
        return None
    request, requester = _request_and_requester(event.aggregate_id)
    if request is None or requester is None or requester.email is None:
        return None

    church = church_profile()
    text = template.format(phone=church.phone)
    return NotificationEmail(
        to=requester.email,
        subject=f"Update on your {request.display_number}",
        text_body=text,
        category="requester_request_closed",
    )


def register() -> None:
    """Called once from `RequesterPortalConfig.ready()`."""
    register_notification("RequestSubmitted", _build_request_received_email)
    register_notification("RequesterAccessLinkIssued", _build_new_link_email)
    register_notification("RequestMediaBatchOpened", _build_more_photos_email)
    register_notification("RequestCancelled", _build_closed_email)


__all__ = ["register"]
