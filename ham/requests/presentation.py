"""Plain-language labels for leadership screens (intake.md L1/L2; Q-132 list rows carry only
HAM # + category, never a raw enum value). Mirrors `ham.audit.labels`'s "add every new code
here too, or the UI shows the raw value" convention.

Pure lookups only -- no DB, no I/O -- so templates and tests can import this freely.
"""

from __future__ import annotations

from datetime import UTC, datetime

import phonenumbers

from .matching import DEFAULT_PHONE_REGION, MatchReason
from .models import (
    NeedCategory,
    PreferredContactMethod,
    PropertyType,
    RelationshipToProperty,
    UrgencyReason,
)
from .states import CancelReason, RequestStatus, VerificationMethod

# Q-113 hazard codes (`ham.requester_portal.choices.Hazard`) duplicated here rather than
# imported: `ham.requests` sits *below* `ham.requester_portal` in the layer order
# (intake.md §2: `web -> requester_portal -> media -> requests -> ...`), so this app may
# never import that one (see `ham.requests.services`'s module docstring for the same rule).
# Keep these in sync with `ham.requester_portal.choices.HAZARD_LABELS` by hand.
HAZARD_LABELS: dict[str, str] = {
    "dogs_or_other_animals": "Dogs or other animals",
    "mold": "Mold",
    "exposed_wiring": "Exposed wiring",
    "sagging_floors_roof_stairs": "Sagging floors, roof or stairs",
    "pests": "Pests",
    "something_else": "Something else",
    "none_known": "None that I know of",
}

# ISO weekday numbers (1=Monday..7=Sunday) plus the two time-of-day words and "any time
# works" (`ham.requester_portal.choices.WEEKDAY_LABELS`/`AVAILABILITY_*`), duplicated for
# the same layering reason as HAZARD_LABELS above.
_WEEKDAY_LABELS: dict[str, str] = {
    "1": "Monday",
    "2": "Tuesday",
    "3": "Wednesday",
    "4": "Thursday",
    "5": "Friday",
    "6": "Saturday",
    "7": "Sunday",
}
AVAILABILITY_LABELS: dict[str, str] = {
    **_WEEKDAY_LABELS,
    "any_time": "Any time works",
    "mornings": "Mornings",
    "afternoons": "Afternoons",
}

NEED_CATEGORY_LABELS: dict[str, str] = dict(NeedCategory.choices)
URGENCY_REASON_LABELS: dict[str, str] = dict(UrgencyReason.choices)
PROPERTY_TYPE_LABELS: dict[str, str] = dict(PropertyType.choices)
RELATIONSHIP_LABELS: dict[str, str] = dict(RelationshipToProperty.choices)
CONTACT_METHOD_LABELS: dict[str, str] = dict(PreferredContactMethod.choices)

# Staff-facing status words (§52); the requester-facing chip words (N§5) are a separate,
# smaller set the secure page owns (S2.7) -- these are for leadership screens only.
STATUS_LABELS: dict[str, str] = {
    RequestStatus.NEEDS_PHONE_CHECK.value: "Needs a phone check",
    RequestStatus.SUBMITTED.value: "Submitted",
    RequestStatus.AWAITING_APPROVAL.value: "Awaiting Approval",
    RequestStatus.CANCELLED.value: "Cancelled",
    RequestStatus.APPROVED.value: "Approved",
    RequestStatus.REJECTED.value: "Rejected",
    RequestStatus.RECONSIDERATION_PENDING.value: "Reconsideration pending",
}

# Chip tone token suffix (`.chip--<tone>` in shell.css); color is never the only signal --
# every chip in the templates also carries an icon + the word above.
STATUS_TONES: dict[str, str] = {
    RequestStatus.NEEDS_PHONE_CHECK.value: "attention",
    RequestStatus.SUBMITTED.value: "info",
    RequestStatus.AWAITING_APPROVAL.value: "info",
    RequestStatus.CANCELLED.value: "neutral",
    RequestStatus.APPROVED.value: "success",
    RequestStatus.REJECTED.value: "danger",
    RequestStatus.RECONSIDERATION_PENDING.value: "attention",
}

# Icon per status tone (C§5 "color is never the only signal" -- every status chip pairs its
# tone with a matching icon, not just a color).
STATUS_ICONS: dict[str, str] = {
    RequestStatus.NEEDS_PHONE_CHECK.value: "phone-call",
    RequestStatus.SUBMITTED.value: "inbox",
    RequestStatus.AWAITING_APPROVAL.value: "hourglass",
    RequestStatus.CANCELLED.value: "ban",
    RequestStatus.APPROVED.value: "circle-check",
    RequestStatus.REJECTED.value: "circle-alert",
    RequestStatus.RECONSIDERATION_PENDING.value: "hourglass",
}

# Q-107/Q-140: the only four pre-decision close reasons; order matches L10's radio list.
CANCEL_REASON_LABELS: dict[str, str] = {
    CancelReason.SPAM.value: "This is spam or a test",
    CancelReason.REQUESTER_WITHDREW.value: "The requester asked us to withdraw it",
    CancelReason.DUPLICATE_SUBMISSION.value: "The same request was sent twice",
    CancelReason.COULDNT_REACH_THEM.value: "We couldn't reach them",
}

# Short closed-banner phrasing (L2 "Closed Oct 8 · {reason} · {actor}").
CANCEL_REASON_BANNER_LABELS: dict[str, str] = {
    CancelReason.SPAM.value: "Closed as spam or a test",
    CancelReason.REQUESTER_WITHDREW.value: "The requester asked us to withdraw it",
    CancelReason.DUPLICATE_SUBMISSION.value: "The same request sent twice",
    CancelReason.COULDNT_REACH_THEM.value: "We couldn't reach them",
}

# Q-115: keyed duplicate-match chip words (L5); never a score.
MATCH_REASON_LABELS: dict[str, str] = {
    MatchReason.ADDRESS.value: "Same address",
    MatchReason.PHONE.value: "Same phone",
    MatchReason.EMAIL.value: "Same email",
    MatchReason.NAME_ZIP.value: "Same name and ZIP",
}

VERIFICATION_METHOD_LABELS: dict[str, str] = {
    VerificationMethod.EMAIL_CODE.value: "code",
    VerificationMethod.EMAIL_LINK.value: "link",
    VerificationMethod.STAFF_PHONE_CALL.value: "phone call",
}

SOURCE_LABELS: dict[str, str] = {
    "public_form": "Public form",
    "church_link": "Church-issued link",
    "assisted": "Entered on someone's behalf",
}


def need_category_label(value: str) -> str:
    return NEED_CATEGORY_LABELS.get(value, value)


def status_label(value: str) -> str:
    return STATUS_LABELS.get(value, value)


def status_tone(value: str) -> str:
    return STATUS_TONES.get(value, "neutral")


def status_icon(value: str) -> str:
    return STATUS_ICONS.get(value, "circle-help")


def cancel_reason_label(value: str) -> str:
    return CANCEL_REASON_LABELS.get(value, value)


def match_reason_label(value: str) -> str:
    return MATCH_REASON_LABELS.get(value, value)


def hazard_labels(known_hazards: str) -> list[dict[str, str]]:
    """Visual QA M1 / usability M1: `AssistanceRequest.known_hazards` is stored as
    comma-joined hazard codes, with an optional free-text note appended in parentheses
    (`ham.requester_portal.services._payload_from_cleaned`) -- turns that back into a list of
    `{"code", "label", "note"}` dicts for L2, instead of printing the raw string
    ("dogs_or_other_animals") to a leader. Never raises on an unrecognized code (falls back to
    the code itself so nothing silently disappears).

    Usability re-check M1: two leftover bugs fixed here.
    (1) The wrapper-note parse used to split on the *last* " (" in the stored string
    (``rpartition``), which mis-parsed a note that itself contained " (" (e.g. a note reading
    "help (please)" produced note="please" and left "help" stuck onto the codes). Hazard codes
    themselves never contain a parenthesis, so the wrapper's opening "(" is always the
    *first* " (" in the string -- ``partition`` (not ``rpartition``) is unambiguous and robust
    to any parenthesis the requester's own note text contains.
    (2) A bare "none_known" answer is not itself a hazard -- it is filtered out of the
    returned list entirely so the caller's own empty-list branch renders the neutral "None
    that they know of" line (no warning-triangle icon) instead of a hazard-shaped item.
    """
    stored = (known_hazards or "").strip()
    if not stored:
        return []
    note = ""
    if stored.endswith(")") and " (" in stored:
        stored, _, note = stored.partition(" (")
        note = note[:-1]
    elif not any(code in stored for code in HAZARD_LABELS) and "," not in stored:
        # A single free-text note with no recognized code in front of it (e.g. the
        # "Something else" hazard note stands alone with nothing to strip).
        note, stored = stored, ""
    codes = [c.strip() for c in stored.split(",") if c.strip() and c.strip() != "none_known"]
    if not codes and note:
        return [{"code": "", "label": "", "note": note}]
    return [
        {"code": code, "label": HAZARD_LABELS.get(code, code), "note": note if i == 0 else ""}
        for i, code in enumerate(codes)
    ]


def urgency_line(reason_code: str, justification: str) -> str:
    """UX M4/N-M1: composes "Reason label. Their words" for display only (L2) -- never
    stored this way; `AssistanceRequest.urgency_reason` (a code) and `.urgency_justification`
    (the requester's own free text) are always kept as two separate fields, so re-saving a
    draft or re-rendering this line twice never duplicates/re-prefixes anything."""
    label = URGENCY_REASON_LABELS.get(reason_code, "")
    justification = (justification or "").strip()
    if label and justification:
        return f"{label}. {justification}"
    return label or justification


def availability_labels(preferred_availability: str) -> list[str]:
    """Visual QA M1: `preferred_availability` is stored as a comma-joined list of ISO weekday
    numbers plus time-of-day words (e.g. "1, 3, any_time") -- turns that into plain-language
    labels ("Monday", "Wednesday", "Any time works") instead of showing the raw codes."""
    stored = (preferred_availability or "").strip()
    if not stored:
        return []
    return [AVAILABILITY_LABELS.get(v.strip(), v.strip()) for v in stored.split(",") if v.strip()]


def format_phone_national(value: str | None) -> str:
    """Visual QA M10/M13, usability M10: a stored E.164 phone (`+13055550142`) formatted as
    `(305) 555-0142` for display -- Doris and Marcus both need to read/say a number aloud, not
    an internal storage format. Falls back to the raw value for anything that doesn't parse
    (so a bad number is still visible rather than silently blanked)."""
    if not value:
        return ""
    try:
        parsed = phonenumbers.parse(value, DEFAULT_PHONE_REGION)
    except phonenumbers.NumberParseException:
        return value
    if not phonenumbers.is_valid_number(parsed):
        return value
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)


def relative_age(moment: datetime, *, now: datetime | None = None) -> str:
    """Visual/usability M11/M13: "3 days" / "2 h" instead of an absolute timestamp on a list
    row, so the urgent-first/oldest-first ordering reads at a glance. The full time still
    belongs in a `<time title>`/`church_time` filter next to this, never replaced by it."""
    if moment is None:
        return ""
    now = now or datetime.now(UTC)
    delta = now - moment
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = 0
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min"
    if hours < 24:
        return f"{hours} h"
    return f"{days} day" if days == 1 else f"{days} days"
