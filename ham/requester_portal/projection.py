"""Requester-facing status wording (docs/ux/navigation.md §5) and contact masking (Q-137).

Pure functions over already-known field values — this module never queries `ham.requests`
tables itself (that app's models are S2.2's, built in a different worktree in parallel); the
secure-page view (S2.7, once merged) loads the real request/requester/property rows through
`ham.requests`' own authorized query functions and passes the handful of fields these
functions need. Step 2 only ever shows `SUBMITTED`, `NEEDS_PHONE_CHECK`, `AWAITING_APPROVAL`
and `CANCELLED` (step 3 adds the rest of navigation.md §5's table).

S3.4 adds the step-3 rows (docs/ux/approvals.md §6 R13-R19, design-system/screens/approvals.md
§5.2-§5.6, §26a): Approved, Not approved (open/reconsiderable and final), Taking another look.
Same rules as the step-2 wording above: pure, no `ham.requests` import, and **never** the
decider's name or route (Q-171) -- these functions only ever take an already-known outcome/
stage/flag, never an `Approval` row or a user id.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# navigation.md §5 (step-2 rows only; step 3 adds Approved/Rejected/etc.).
_STATUS_WORDING: dict[str, str] = {
    "SUBMITTED": "We've received your request.",
    "NEEDS_PHONE_CHECK": (
        "A HAM leader will call you to confirm your request before it goes further."
    ),
    "AWAITING_APPROVAL": "Our pastors or Board are reviewing your request.",
}

# C§26 / C§26a: the requester-facing chip word/tone/icon for each status this step shows
# (staff status -> requester word, design-system/components.md §26 and §26a). Tone tokens are
# the `.chip--<tone>` suffix; icon names are from `ham/web/static/web/icons.svg`. REJECTED is
# not here (open vs final needs `closed`, not just the status) -- see `rejected_chip` below.
REQUESTER_STATUS_CHIPS: dict[str, tuple[str, str, str]] = {
    "SUBMITTED": ("Received", "info", "inbox"),
    "NEEDS_PHONE_CHECK": ("Received", "info", "inbox"),
    "AWAITING_APPROVAL": ("Being reviewed", "info", "hourglass"),
    "CANCELLED": ("Closed", "neutral", "ban"),
    # §26a
    "APPROVED": ("Approved", "success", "circle-check"),
    "RECONSIDERATION_PENDING": ("Taking another look", "info", "rotate-ccw"),
}


def rejected_chip(*, closed: bool) -> tuple[str, str, str]:
    """§26a: Rejected shows a neutral chip either way (never red) -- "Not approved" while it
    can still be reconsidered, "Closed" once final (window passed or reconsidered)."""
    return ("Closed", "neutral", "ban") if closed else ("Not approved", "neutral", "circle-x")


# usability M14: "What happens next" per status -- the welcome page (R7) and the plain secure
# page (R10) share this list instead of R7 hard-coding its own and R10 having none at all.
STATUS_NEXT_STEPS: dict[str, list[str]] = {
    "SUBMITTED": [
        "Our pastors or Board review your request, usually within a few days.",
        "If it's approved, someone from HAM will call you to arrange a visit.",
    ],
    "NEEDS_PHONE_CHECK": [
        "A HAM leader will call you to confirm it's you who asked.",
        "After that call, our pastors or Board review your request.",
    ],
    "AWAITING_APPROVAL": [
        "Our pastors or Board are looking at your request now.",
        "If it's approved, someone from HAM will call you to arrange a visit.",
    ],
}

# --------------------------------------------------------------------------------------
# Step 3 (approvals.md §6 R14/R15/R17/R18; design-system/screens/approvals.md §5.2-§5.6)
# --------------------------------------------------------------------------------------
_APPROVED_SENTENCE = "Good news: your request is approved."
_APPROVED_AFTER_RECONSIDERATION_SENTENCE = (
    "Good news: after taking another look, we've approved your request."
)
# owner box / §11: the approval copy keeps this line (design-system §26a checklist item,
# approvals-contracts.md task brief). Numbered list, R14/R18a "What happens next".
APPROVED_NEXT_STEPS: tuple[str, ...] = (
    "Someone from HAM will call you to arrange a visit to look at the work.",
    "The visit helps us plan; it doesn't yet promise the work.",
    "You don't need to do anything right now.",
)
URGENT_CERTIFIED_ALERT = (
    "Because it's urgent, HAM's leaders have been told right away and will contact you soon. "
    "If anyone is in danger, call 911."
)

_REJECTED_OPEN_SENTENCE = (
    "We're sorry. After looking carefully at your request, we aren't able to help with this one."
)
REJECTED_SYMPATHY_LINE = "We know this isn't the answer you hoped for."
RECONSIDER_OFFER_LINE = "If you think we've missed something, you can ask us to reconsider, once."

_REJECTED_FINAL_AFTER_RECONSIDERATION_SENTENCE = (
    "We looked at your request again, and we're sorry, we're still not able to help with this one."
)
_REJECTED_FINAL_WINDOW_PASSED_SENTENCE = "We weren't able to help with this request."
REJECTED_FINAL_NEXT_STEP = "You're welcome to send a new request in the future if things change."

_RECONSIDERATION_PENDING_SENTENCE = "We're taking another look at your request."
RECONSIDERATION_PENDING_NEXT_STEP = "We'll let you know what we decide, by email and on this page."

# R10 status table: "Awaiting Approval + question open" replaces the plain AWAITING_APPROVAL
# next-step pair with this one line while a question is open (design-system §5.1).
AWAITING_APPROVAL_QUESTION_NEXT_STEP = (
    "We have a question for you below. Your answer helps us decide."
)


def approved_sentence(*, after_reconsideration: bool) -> str:
    """R14 / R18a "Good news" sentence (never the §11 line -- that's in `APPROVED_NEXT_STEPS`)."""
    return _APPROVED_AFTER_RECONSIDERATION_SENTENCE if after_reconsideration else _APPROVED_SENTENCE


def rejected_open_sentence() -> str:
    """R15's fixed sentence (the reason message itself is separate, shown in its own quote
    block -- this function never sees it)."""
    return _REJECTED_OPEN_SENTENCE


def rejected_final_sentence(*, after_reconsideration: bool) -> str:
    """R18b (declined on reconsideration) vs R18c (window passed, never asked)."""
    return (
        _REJECTED_FINAL_AFTER_RECONSIDERATION_SENTENCE
        if after_reconsideration
        else _REJECTED_FINAL_WINDOW_PASSED_SENTENCE
    )


def reconsideration_pending_sentence() -> str:
    """R17's fixed sentence."""
    return _RECONSIDERATION_PENDING_SENTENCE


def reconsider_ask_line(last_day: dt.date) -> str:
    """R15: "You can ask until Thu, Nov 5." -- the church-local calendar date the deadline
    ends on (`ham.requests.states.reconsideration_last_day`), never a time of day."""
    return f"You can ask until {last_day.strftime('%a, %b %-d')}."


def access_until_line(access_ends_at: dt.date) -> str:
    """R18b/R18c footer: "This page will stay available until {date}." (Q-116)."""
    return f"This page will stay available until {access_ends_at.strftime('%a, %b %-d')}."


# Q-107/Q-140: pre-decision cancel reasons, in the requester's own words (never "spam", which
# gets no note at all per docs/ux/intake.md). Usability M14: a duplicate close must not invite
# a second copy of the same still-open request, so it gets its own closing line instead of the
# generic "always welcome to submit a new request." every other reason keeps.
_CANCEL_REASON_WORDING: dict[str, str] = {
    "spam": "",
    "requester_withdrew": "You let us know it wasn't needed anymore.",
    "duplicate_submission": (
        "It matched a request you'd already sent us. Your other request is still open. If "
        "that's not right, please call us."
    ),
    # PRD-guardian N5: key must equal CancelReason.COULDNT_REACH_THEM.value.
    "couldnt_reach_them": "We weren't able to reach you to confirm it.",
}

_ALWAYS_WELCOME = "You're always welcome to submit a new request."


def cancel_reason_offers_new_request(cancel_reason: str | None) -> bool:
    """Usability M14: "Ask for help again" only makes sense once someone actually confirms
    they don't need HAM anymore -- not after a duplicate close (their other request is still
    open, asking again would just make a second duplicate)."""
    return cancel_reason == "requester_withdrew"


def status_wording(status: str, *, cancel_reason: str | None = None) -> str:
    """The plain-language sentence for the secure page's status card. Returns "" for a
    status/reason this function doesn't know (a later step's status), so the caller can fall
    back to its own wording rather than show something wrong."""
    if status == "CANCELLED":
        reason_text = _CANCEL_REASON_WORDING.get(cancel_reason or "", "")
        base = "This request has been closed."
        sentence = f"{base} {reason_text}".strip()
        if cancel_reason != "duplicate_submission":
            sentence = f"{sentence} {_ALWAYS_WELCOME}"
        return sentence
    return _STATUS_WORDING.get(status, "")


def _mask_local_part(local: str) -> str:
    if not local:
        return ""
    return f"{local[0]}•••"  # fixed-width mask (docs/ux/intake.md R11a "d•••@gmail.com")


def mask_email(email: str | None) -> str:
    """Q-137: email masked. ``d•••@gmail.com`` style (docs/ux/intake.md R11a)."""
    if not email or "@" not in email:
        return ""
    local, _, domain = email.partition("@")
    return f"{_mask_local_part(local)}@{domain}"


def mask_phone(phone: str | None) -> str:
    """Q-137: phone masked, keeping only the last 4 digits so a person can recognize their
    own number without the whole thing being on-screen."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) < 4:
        return ""
    return f"(•••) •••-{digits[-4:]}"


def mask_street(line1: str | None) -> str:
    """Q-137: street line masked entirely (city and ZIP are shown unmasked)."""
    return "Hidden" if line1 else ""


@dataclass(frozen=True, slots=True)
class MaskedContact:
    email: str
    phone: str
    street: str
    city: str
    postal_code: str


def masked_contact(
    *,
    email: str | None,
    phone: str | None,
    line1: str | None,
    city: str | None,
    postal_code: str | None,
) -> MaskedContact:
    """Q-137: "Email, phone and street line masked; city and ZIP shown." — the secure page's
    own contact card (not the leadership reveal card, which is `ham.requests.services.
    reveal_requester_pii`'s job and shows the real values to authorized staff only)."""
    return MaskedContact(
        email=mask_email(email),
        phone=mask_phone(phone),
        street=mask_street(line1),
        city=city or "",
        postal_code=postal_code or "",
    )


__all__ = [
    "APPROVED_NEXT_STEPS",
    "AWAITING_APPROVAL_QUESTION_NEXT_STEP",
    "MaskedContact",
    "REJECTED_FINAL_NEXT_STEP",
    "REJECTED_SYMPATHY_LINE",
    "RECONSIDER_OFFER_LINE",
    "RECONSIDERATION_PENDING_NEXT_STEP",
    "REQUESTER_STATUS_CHIPS",
    "STATUS_NEXT_STEPS",
    "URGENT_CERTIFIED_ALERT",
    "access_until_line",
    "approved_sentence",
    "cancel_reason_offers_new_request",
    "mask_email",
    "mask_phone",
    "mask_street",
    "masked_contact",
    "reconsideration_pending_sentence",
    "reconsider_ask_line",
    "rejected_chip",
    "rejected_final_sentence",
    "rejected_open_sentence",
    "status_wording",
]
