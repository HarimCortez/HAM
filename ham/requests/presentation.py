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
    RejectionReason,
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
    # FIX-G UX minor: "you" (not "I") -- this label is read back on the requester's own
    # secure page, addressing them directly, not quoting their own first-person form answer
    # (`ham.requester_portal.choices.Hazard`'s R4 checkbox label stays first-person, since
    # that one *is* the requester answering about themselves).
    "none_known": "None that you know of",
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
    # FIX-F1 status casing: sentence case everywhere ("Needs a phone check", not title case).
    RequestStatus.AWAITING_APPROVAL.value: "Awaiting approval",
    RequestStatus.CANCELLED.value: "Cancelled",
    RequestStatus.APPROVED.value: "Approved",
    RequestStatus.REJECTED.value: "Rejected",
    RequestStatus.RECONSIDERATION_PENDING.value: "Reconsideration pending",
}

# Chip tone token suffix (`.chip--<tone>` in shell.css); color is never the only signal --
# every chip in the templates also carries an icon + the word above.
# M3 (step3 visual QA / C§26a): Rejected is neutral, never red/danger -- a decline isn't a
# system error, and the spec is explicit that it must never alarm. Reconsideration pending
# reads as "in motion" (attention), not merely "waiting" (it used to share `hourglass`/
# `attention` with the plain Awaiting-approval wait state).
STATUS_TONES: dict[str, str] = {
    RequestStatus.NEEDS_PHONE_CHECK.value: "attention",
    RequestStatus.SUBMITTED.value: "info",
    RequestStatus.AWAITING_APPROVAL.value: "info",
    RequestStatus.CANCELLED.value: "neutral",
    RequestStatus.APPROVED.value: "info",
    RequestStatus.REJECTED.value: "neutral",
    RequestStatus.RECONSIDERATION_PENDING.value: "attention",
}

# Icon per status tone (C§5 "color is never the only signal" -- every status chip pairs its
# tone with a matching icon, not just a color).
STATUS_ICONS: dict[str, str] = {
    RequestStatus.NEEDS_PHONE_CHECK.value: "phone-call",
    RequestStatus.SUBMITTED.value: "inbox",
    RequestStatus.AWAITING_APPROVAL.value: "hourglass",
    RequestStatus.CANCELLED.value: "ban",
    RequestStatus.APPROVED.value: "badge-check",
    RequestStatus.REJECTED.value: "circle-x",
    RequestStatus.RECONSIDERATION_PENDING.value: "rotate-ccw",
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

# S3.6 (docs/architecture/approvals.md D2, Q-154; owner box + design-system/screens/
# approvals.md §0.1): the five decline-reason labels for the A3 radio cards, and HAM's own
# suggested (fully editable) kind message per reason -- the approver's edited text is what's
# actually stored (`Approval.reason`); these are prefill copy only, never re-applied later.
REJECTION_REASON_LABELS: dict[str, str] = dict(RejectionReason.choices)

REJECTION_REASON_PREFILLS: dict[str, str] = {
    RejectionReason.FAMILY_OR_OTHERS_CAN_HELP.value: (
        "From what you've shared, it sounds like family or others may be able to help with "
        "this. HAM's volunteers focus on work people can't manage any other way."
    ),
    RejectionReason.OWNER_OR_LANDLORD_RESPONSIBLE.value: (
        "Because you rent your home, this repair is the responsibility of the owner or "
        "landlord. We'd encourage you to ask them first."
    ),
    RejectionReason.NOT_HELP_HAM_OFFERS.value: (
        "This isn't the kind of work our volunteer teams are able to take on."
    ),
    RejectionReason.COULDNT_CONFIRM.value: (
        "We weren't able to confirm the details we needed to go ahead."
    ),
    RejectionReason.ANOTHER_REASON.value: "",
}

# Fix 3A / L4 / Q-179 (owner decision, 2026-09-28): the decline message the requester reads
# is 1,000 characters (same as the reconsideration note); the "Why approved (leaders only)"
# note is 200. Form-validation constants, not `ham.rules` entries (approvals.md §2.4 "Text
# limits ... don't go in the rules module").
DECLINE_MESSAGE_MAX_CHARS = 1000
APPROVAL_NOTE_MAX_CHARS = 200


# Fix 3A / UX M6 / PRD guardian minor 1: the leadership preview (A3 "What the requester will
# read") must render EXACTLY what the requester email sends -- one shared builder, called by
# both `ham.requester_portal.notifications._build_rejected_email` (E10, prefixed with "Hi
# {first}, ") and `ham.web.views_requests`'s decline sheet context (which passes
# `greeting="Hi there"` as a stand-in, since the requester's first name is never shown to
# leaders, Q-170). Real deadline date and reconsideration count come from the caller (never a
# literal "14 days" typed into a template).
def reconsideration_preview_deadline_text(now) -> str:
    """The church-local date a decline recorded right now would print on E10/A3 -- same
    format (`"Tue, Oct 20"`) and same calendar-day math (`.states.reconsideration_deadline`)
    as the email actually sent once the decision is recorded, so the preview's date is never
    off by the time a leader spends filling in the sheet."""
    from zoneinfo import ZoneInfo

    from ham.platform.church import church_profile

    from .states import reconsideration_deadline

    zone = ZoneInfo(church_profile().time_zone)
    deadline = reconsideration_deadline(now, zone)
    return deadline.astimezone(zone).strftime("%a, %b %-d")


def decline_outcome_text(
    message: str,
    *,
    final: bool,
    deadline_text: str = "",
    church_phone: str = "",
) -> str:
    """The body of E10 (still reconsiderable) or E13 (final) -- Q-154's kind message plus the
    sympathy line, the "once" reconsideration offer with its real deadline, and the church
    phone line when one is on file."""
    if final:
        return (
            "we looked at your request again, and we're sorry, we're still not able to "
            f"help with this one. Here's why: \"{message}\". You're welcome to send a new "
            "request in the future if things change."
        )
    reconsider_clause = (
        f" If you think we've missed something, you can ask us to reconsider, once, "
        f"until {deadline_text}."
        if deadline_text
        else ""
    )
    phone_clause = (
        f" Or call us at {church_phone} -- we're glad to talk it through." if church_phone else ""
    )
    return (
        "we're sorry. After looking carefully at your request, we aren't able to help with "
        f'this one. Here\'s why: "{message}".{reconsider_clause}{phone_clause}'
    )


def rejection_reason_label(value: str) -> str:
    return REJECTION_REASON_LABELS.get(value, value)


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

    FIX-G UX minor: the free-text note is always about the "Something else" hazard (it's the
    only hazard the form even collects a note for) -- it used to be attached to whichever
    hazard happened to be ticked *first*, which misattributed it to an unrelated hazard
    whenever "Something else" wasn't the first checkbox ticked. Now attached to the
    "something_else" item specifically, wherever it falls in the ticked list; if that code
    somehow isn't present (defensive -- the form itself requires it), the note is returned as
    its own separate item (`code=""`, same shape the caller already renders as a plain "Note:
    ..." line for a note with no codes at all) instead of silently landing on a different
    hazard.
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
    items = [{"code": code, "label": HAZARD_LABELS.get(code, code), "note": ""} for code in codes]
    if note:
        target = next((item for item in items if item["code"] == "something_else"), None)
        if target is None and len(items) == 1:
            # No ambiguity with exactly one ticked hazard -- attach the note there, same as
            # before, even though the form itself only ever pairs a note with "something_else"
            # (defensive: this module's input is a stored string, not a fresh form submission).
            target = items[0]
        if target is not None:
            target["note"] = note
        else:
            items.append({"code": "", "label": "", "note": note})
    return items


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
