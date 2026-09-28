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

**Coordination note resolved (usability re-check M7):** docs/ux/intake.md lists "new link"
(E3, after R11a "my link expired") and "find-my-request result" (E4, after R11b "check on my
request") as two differently-worded emails. An earlier slice noted that intake-contracts.md
§7's route table sent both flows through the same `requester_link.regenerate` action and the
same `RequesterAccessLinkIssued` (`kind="regenerated"`) outbox event, with nothing in the
payload to tell the two origins apart, and flagged it here rather than silently picking one.
Resolution: R11b ("check on your request") no longer goes through that shared path at all —
`ham.requester_portal.services._issue_and_notify_found_link` issues the link and sends E4
directly (see `send_found_request_email` below), with its own `requester_link.found` audit
action, never touching `RequesterAccessLinkIssued`/`_build_new_link_email` (E3). R11a ("my
link expired") is the only flow left on the shared `requester_link.regenerate` /
`RequesterAccessLinkIssued` path, so E3's wording ("your old link no longer works") is now
always the right wording for whoever receives it.
"""

from __future__ import annotations

from django.conf import settings
from django.urls import reverse

from ham.integrations.email.notifications import NotificationEmail, register_notification
from ham.outbox.models import OutboxEvent
from ham.platform.church import church_profile
from ham.platform.clock import now as clock_now
from ham.platform.crypto import decrypt

from .models import RequesterAccessLink


def _first_name(full_name: str) -> str:
    full_name = (full_name or "").strip()
    return full_name.split()[0] if full_name else "there"


def _current_link(request_id) -> RequesterAccessLink | None:
    """The requester's current live link row. `None` for a no-email (`NEEDS_PHONE_CHECK`)
    request, which never has one."""
    return (
        RequesterAccessLink.objects.filter(request_id=request_id, revoked_at__isnull=True)
        .order_by("-issued_at")
        .first()
    )


def _link_url(link: RequesterAccessLink) -> str:
    """Security review H4: every requester email used to hard-code ``/r/<token>``, but the
    real secure-page route (`ham.web.urls_requester`) is `/request-help/r/<token>`
    (`web:request_help_secure_page`) -- every emailed link 404'd. Building it through
    `reverse()` against the real URLconf, instead of a second hard-coded path guess, means a
    route rename can't silently break this again without also failing
    `test_every_emailed_url_resolves` (S2.6/fix-round tests)."""
    token = decrypt(link.token_ciphertext)
    base = str(settings.HAM_BASE_URL).rstrip("/")
    path = reverse("web:request_help_secure_page", kwargs={"token": token})
    return f"{base}{path}"


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

    link = _current_link(request.id)
    if link is None:  # pragma: no cover - defensive; issue_link always runs first
        return None
    link_url = _link_url(link)

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
def _link_expiry_note(link: RequesterAccessLink, request) -> str:
    """PRD guardian N3 / Q-149: the new-link email used to always say "This link works for
    14 days", even when the real link (`RequesterAccessLink.expires_at`, or -- when that's
    unset -- normal access ending with the request) lasts a different amount of time (e.g. a
    link regenerated for a request that's still open follows normal access and has no fixed
    end at all). States the link's actual end instead of the rules-module lifetime."""
    if link.expires_at is not None:
        remaining = link.expires_at - clock_now()
        days = max(1, round(remaining.total_seconds() / 86400))
        plural = "" if days == 1 else "s"
        return f"This link works for {days} more day{plural}."
    from ham.requester_portal.validity import normal_access_ends_at

    ends_at = normal_access_ends_at(status=request.status, closed_at=request.closed_at)
    if ends_at is not None:
        return f"This link works until {ends_at.strftime('%B %-d, %Y')}."
    return "This link works for as long as your request stays open."


def _build_new_link_email(event: OutboxEvent) -> NotificationEmail | None:
    if event.payload.get("kind") != RequesterAccessLink.KIND_REGENERATED:
        return None
    request_id = event.payload.get("request_id") or event.aggregate_id
    request, requester = _request_and_requester(request_id)
    if request is None or requester is None or requester.email is None:
        return None

    link = _current_link(request.id)
    if link is None:  # pragma: no cover - defensive
        return None
    link_url = _link_url(link)

    text = (
        f"Here's your new link. Your old link no longer works. {_link_expiry_note(link, request)}"
        f"\n\nOpen my request page: {link_url}"
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

    link = _current_link(request.id)
    if link is None:  # pragma: no cover - defensive
        return None
    link_url = _link_url(link)

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


# ---------------------------------------------------------------------------------------
# E4: "Your HAM request #047" (R11b "Check on your request" result, one per matching
# request -- Q-117). Sent immediately by `ham.requester_portal.services.
# _issue_and_notify_found_link`, the same way `ham.requester_portal.verification`'s code
# emails are sent immediately, never through the outbox (usability re-check M7: this used to
# ride the generic `RequesterAccessLinkIssued`/E3 "new link" path, which is wrong wording for
# a "here's your link" result and also fired a second, unwanted email on top of a code email
# that had nowhere to be typed in).
# ---------------------------------------------------------------------------------------
def send_found_request_email(*, display_number: str, email: str, link: RequesterAccessLink) -> None:
    """``display_number`` comes from the caller's own registered facts lookup
    (`ham.requester_portal.services.RequestLinkFacts.display_number`), not a direct
    `ham.requests.models.AssistanceRequest` query here -- this app sits *above* `ham.requests`
    in the layers contract for its cross-app *reads* on the hot path (it already imports
    `ham.requests.models` elsewhere in this module for the outbox-driven builders, which are
    a legal, one-way downward read; this function is kept lookup-driven instead so it works
    identically whether or not this specific request row is reachable, matching every other
    "portal facts" cross-app boundary in this app)."""
    from ham.integrations.email.service import send_transactional_email

    subject = f"Your {display_number}" if display_number else "Your HAM request"
    link_url = _link_url(link)
    text = f"Here's the link to your request.\n\nOpen my request page: {link_url}"
    send_transactional_email(
        to=email,
        subject=subject,
        text_body=text,
        category="requester_found_link",
    )


def register() -> None:
    """Called once from `RequesterPortalConfig.ready()`."""
    register_notification("RequestSubmitted", _build_request_received_email)
    register_notification("RequesterAccessLinkIssued", _build_new_link_email)
    register_notification("RequestMediaBatchOpened", _build_more_photos_email)
    register_notification("RequestCancelled", _build_closed_email)


__all__ = ["register", "send_found_request_email"]
