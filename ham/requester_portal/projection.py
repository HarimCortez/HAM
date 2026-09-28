"""Requester-facing status wording (docs/ux/navigation.md §5) and contact masking (Q-137).

Pure functions over already-known field values — this module never queries `ham.requests`
tables itself (that app's models are S2.2's, built in a different worktree in parallel); the
secure-page view (S2.7, once merged) loads the real request/requester/property rows through
`ham.requests`' own authorized query functions and passes the handful of fields these
functions need. Step 2 only ever shows `SUBMITTED`, `NEEDS_PHONE_CHECK`, `AWAITING_APPROVAL`
and `CANCELLED` (step 3 adds the rest of navigation.md §5's table).
"""

from __future__ import annotations

from dataclasses import dataclass

# navigation.md §5 (step-2 rows only; step 3 adds Approved/Rejected/etc.).
_STATUS_WORDING: dict[str, str] = {
    "SUBMITTED": "We've received your request.",
    "NEEDS_PHONE_CHECK": (
        "A HAM leader will call you to confirm your request before it goes further."
    ),
    "AWAITING_APPROVAL": "Our pastors or Board are reviewing your request.",
}

# Q-107/Q-140: pre-decision cancel reasons, in the requester's own words (never "spam", which
# gets no note at all per docs/ux/intake.md).
_CANCEL_REASON_WORDING: dict[str, str] = {
    "spam": "",
    "requester_withdrew": "You let us know it wasn't needed anymore.",
    "duplicate_submission": "It matched a request you'd already sent us.",
    # PRD-guardian N5: this key must match `ham.requests.states.CancelReason.
    # COULDNT_REACH_THEM.value` exactly ("couldnt_reach_them") -- it used to be spelled
    # "couldnt_reach" here, so this wording silently never showed for that reason.
    "couldnt_reach_them": "We weren't able to reach you to confirm it.",
}


def status_wording(status: str, *, cancel_reason: str | None = None) -> str:
    """The plain-language sentence for the secure page's status card. Returns "" for a
    status/reason this function doesn't know (a later step's status), so the caller can fall
    back to its own wording rather than show something wrong."""
    if status == "CANCELLED":
        reason_text = _CANCEL_REASON_WORDING.get(cancel_reason or "", "")
        base = "This request has been closed."
        return f"{base} {reason_text}".strip() + " You're always welcome to submit a new request."
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
    "MaskedContact",
    "mask_email",
    "mask_phone",
    "mask_street",
    "masked_contact",
    "status_wording",
]
