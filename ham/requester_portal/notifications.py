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

**Coordination note (usability re-check M7, superseded by FIX-G NM1/PRD NEW-2):**
docs/ux/intake.md lists "new link" (E3, after R11a "my link expired") and "find-my-request
result" (E4, after R11b "check on my request") as two differently-worded emails. R11b's own
*first* email (E4, "Open my request page" -- a one-time verification link, never a live
access link) is now sent by `ham.requester_portal.verification.request_find_verification`
directly (`send_transactional_email`, the same immediate-delivery mechanism codes/links
already use), not through this module or the outbox -- there is nothing to look up yet (no
request state has changed). Once that E4 link is clicked and confirmed, though, R11b and R11a
converge on the exact same path as each other from that point on
(`ham.web.views_requester.request_help_new_link` -> `regenerate_link_for_own_request`), so the
email that actually announces "your new link is ready" is the shared `RequesterAccessLinkIssued`
outbox event / `_build_new_link_email` (E3) below, for both flows -- its "your old link no
longer works" wording is accurate either way, since a link is always revoked at that point.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

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


def _reach_us_phrase(church) -> str:
    """UX minor: the church's phone printed in national format (`(305) 555-0142`, not the
    stored E.164 value -- `ham.requests.presentation.format_phone_national`, a legal downward
    import same as this module's other `ham.requests` reads), and gracefully omitting whichever
    of phone/email is unset instead of leaving a bare "Call  or email .". Lowercase, no leading
    "Questions?"/trailing period -- callers compose it into their own sentence."""
    from ham.requests.presentation import format_phone_national

    phone = format_phone_national(church.phone) if church.phone else ""
    email = (church.email or "").strip()
    if phone and email:
        return f"call {phone} or email {email}"
    if phone:
        return f"call {phone}"
    if email:
        return f"email {email}"
    return "contact us"


def _contact_line(church) -> str:
    phrase = _reach_us_phrase(church)
    return f"Questions? {phrase[0].upper()}{phrase[1:]}." if phrase != "contact us" else ""


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
    contact_line = _contact_line(church)
    text = (
        f"Thank you for reaching out, {_first_name(requester.full_name)}.\n\n"
        f"Your request number is {request.display_number}.\n\n"
        f"Open my request page: {link_url}"
        f"{urgent_line}\n\n"
        f"{what_next}"
    )
    if contact_line:
        text = f"{text}\n\n{contact_line}"
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
        "request is still open. If that's not right, please {reach_us}."
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
    text = template.format(reach_us=_reach_us_phrase(church))
    return NotificationEmail(
        to=requester.email,
        subject=f"Update on your {request.display_number}",
        text_body=text,
        category="requester_request_closed",
    )


# ---------------------------------------------------------------------------------------
# E4: R11b "Check on your request" result -- superseded by FIX-G NM1/PRD NEW-2. The first,
# unverified email ("Open my request page") is now built and sent by
# `ham.requester_portal.verification.request_find_verification` itself (no outbox event, same
# immediate-delivery mechanism as codes/links); once its link is clicked and confirmed, the
# actual "here's your link" announcement is the shared E3 builder below.
# ---------------------------------------------------------------------------------------


# ---------------------------------------------------------------------------------------
# S3.5 (approvals.md §4, docs/ux/approvals.md E9/E9u/E10/E13, Q-171/Q-174/Q-175). Every
# builder below carries the secure link (Q-102), a neutral subject ("Update on your HAM
# #047"), and never the decider's name or route (Q-171 -- the requester is only ever told
# "we"/"HAM"). No email at all for a no-email requester (`requester.email is None`), and
# none for `RequestCategoryChanged` (Q-109), `UrgencyNotCertified`/"not yet approved"
# `UrgencyCertified`, `RequestRejectionFinalized` (E14 -- she already had the deadline on
# E10) or `RequesterQuestionAnswered`/withdrawn (E15) -- none of those events are
# registered onto this module's builders at all, which is itself the "no email" decision
# (nothing to silently forget).
#
# Idempotency: every builder below is a pure read of already-committed rows keyed off the
# event's own ids/payload -- calling it twice for the same event returns the same
# `NotificationEmail` (or `None`), so a redelivered `OutboxDelivery` (outbox/dispatch.py's
# retry) never changes what would be sent, only whether it already was (that bookkeeping is
# `OutboxDelivery.status`'s job, not this module's).
# ---------------------------------------------------------------------------------------
def _reconsideration_deadline_text(request) -> str:
    """Q-174: the church-local calendar day printed in the email, e.g. "Tue, Oct 20"."""
    if request.reconsideration_deadline_at is None:
        return ""
    zone = ZoneInfo(church_profile().time_zone)
    local = request.reconsideration_deadline_at.astimezone(zone)
    return local.strftime("%a, %b %-d")


def _live_approval_for_stage(request_id, stage: str):
    from ham.requests.models import Approval

    return (
        Approval.objects.filter(request_id=request_id, stage=stage, undone_at__isnull=True)
        .order_by("-decided_at")
        .first()
    )


# ---------------------------------------------------------------------------------------
# E9 / E9u / E12: "Update on your HAM #047" -- approved (initial or on reconsideration),
# held (RequestApproved is only ever emitted at `effective_at`, never at decide time --
# approvals-contracts.md §4).
# ---------------------------------------------------------------------------------------
def _build_approved_email(event: OutboxEvent) -> NotificationEmail | None:
    request, requester = _request_and_requester(event.aggregate_id)
    if request is None or requester is None or requester.email is None:
        return None
    link = _current_link(request.id)
    if link is None:  # pragma: no cover - defensive
        return None
    link_url = _link_url(link)

    first = _first_name(requester.full_name)
    stage = event.payload.get("stage")
    urgent = bool(event.payload.get("urgent_approval"))
    if stage == "reconsideration":
        opener = f"Good news, {first}: after taking another look, we've approved your request."
    else:
        opener = f"Good news, {first}: your request is approved."
    # PRD §11 / owner decisions box: this exact line must survive -- "the visit helps us
    # plan; it doesn't yet promise the work" -- on every approval email, urgent or not.
    if urgent:
        next_steps = (
            "Because it's urgent, HAM's leaders have been told right away and will contact "
            "you soon. If anyone is in danger, call 911. The visit helps us plan; it "
            "doesn't yet promise the work can be done."
        )
    else:
        next_steps = (
            "Next, someone from HAM will call you to arrange a visit to look at the work. "
            "The visit helps us plan; it doesn't yet promise the work can be done."
        )
    text = f"{opener} {next_steps}\n\nOpen my request page: {link_url}"
    return NotificationEmail(
        to=requester.email,
        subject=f"Update on your {request.display_number}",
        text_body=text,
        category="requester_decision",
    )


# ---------------------------------------------------------------------------------------
# E10 / E13: "Update on your HAM #047" -- not approved (`final=false`, still
# reconsiderable) or final (`final=true`, on reconsideration or after 14 days). Held, same
# as E9/E9u above.
# ---------------------------------------------------------------------------------------
def _build_rejected_email(event: OutboxEvent) -> NotificationEmail | None:
    request, requester = _request_and_requester(event.aggregate_id)
    if request is None or requester is None or requester.email is None:
        return None
    link = _current_link(request.id)
    if link is None:  # pragma: no cover - defensive
        return None
    link_url = _link_url(link)

    stage = event.payload.get("stage", "initial")
    final = bool(event.payload.get("final"))
    approval = _live_approval_for_stage(request.id, stage)
    message = approval.reason.strip() if approval else ""
    first = _first_name(requester.full_name)

    # Fix 3A / UX M6 / PRD guardian minor 1: the same builder the leadership preview uses
    # (`ham.requests.presentation.decline_outcome_text`), so the preview promises exactly
    # what this email sends -- Q-154's kind message, the sympathy line, the real deadline
    # date and "once", and the church phone line when one is on file.
    from ham.requests.presentation import decline_outcome_text

    body = decline_outcome_text(
        message,
        final=final,
        deadline_text=_reconsideration_deadline_text(request),
        church_phone=church_profile().phone,
    )
    text = f"Hi {first}, {body}\n\nOpen my request page: {link_url}"
    return NotificationEmail(
        to=requester.email,
        subject=f"Update on your {request.display_number}",
        text_body=text,
        category="requester_decision",
    )


# ---------------------------------------------------------------------------------------
# E8: "A question about your HAM request #047" (RequesterQuestionAsked) -- the only
# requester email whose subject isn't the neutral "Update on your ..." form (Q-102's own
# example text).
# ---------------------------------------------------------------------------------------
def _build_question_asked_email(event: OutboxEvent) -> NotificationEmail | None:
    from ham.requests.models import RequestQuestion

    question_id = event.payload.get("question_id")
    question = RequestQuestion.objects.filter(id=question_id).first()
    if question is None:
        return None
    if question.answered_at is not None:
        # Asked and answered in the same step (a no-email request's phone callback, Q-159)
        # -- nothing for the requester to do, and a no-email request has no email anyway.
        return None
    request, requester = _request_and_requester(question.request_id)
    if request is None or requester is None or requester.email is None:
        return None
    link = _current_link(request.id)
    if link is None:  # pragma: no cover - defensive
        return None
    link_url = _link_url(link)

    text = (
        f'We have a question about your request: "{question.question}". You can answer '
        f"on your request page.\n\nOpen my request page: {link_url}"
    )
    return NotificationEmail(
        to=requester.email,
        subject=f"A question about your {request.display_number}",
        text_body=text,
        category="requester_question",
    )


# ---------------------------------------------------------------------------------------
# E11: "Update on your HAM #047" -- reconsideration request received (Q-175). Fires for
# both `via` (secure page and Director/AD-recorded phone) -- a no-email requester simply
# has no `requester.email` to send to either way, so the phone path is naturally silent.
# ---------------------------------------------------------------------------------------
def _build_reconsideration_received_email(event: OutboxEvent) -> NotificationEmail | None:
    request, requester = _request_and_requester(event.aggregate_id)
    if request is None or requester is None or requester.email is None:
        return None
    link = _current_link(request.id)
    if link is None:  # pragma: no cover - defensive
        return None
    link_url = _link_url(link)

    first = _first_name(requester.full_name)
    text = (
        f"Thank you, {first}. We've received your request to reconsider, and we'll take "
        f"another look. We'll let you know what we decide.\n\nOpen my request page: {link_url}"
    )
    return NotificationEmail(
        to=requester.email,
        subject=f"Update on your {request.display_number}",
        text_body=text,
        category="requester_reconsideration_received",
    )


def register() -> None:
    """Called once from `RequesterPortalConfig.ready()`."""
    register_notification("RequestSubmitted", _build_request_received_email)
    register_notification("RequesterAccessLinkIssued", _build_new_link_email)
    register_notification("RequestMediaBatchOpened", _build_more_photos_email)
    register_notification("RequestCancelled", _build_closed_email)
    # S3.5 (approvals.md §4, Q-171/Q-174/Q-175).
    register_notification("RequestApproved", _build_approved_email)
    register_notification("RequestRejected", _build_rejected_email)
    register_notification("RequesterQuestionAsked", _build_question_asked_email)
    register_notification("ReconsiderationRequested", _build_reconsideration_received_email)


__all__ = ["register"]
