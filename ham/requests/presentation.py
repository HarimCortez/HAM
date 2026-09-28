"""Plain-language labels for leadership screens (intake.md L1/L2; Q-132 list rows carry only
HAM # + category, never a raw enum value). Mirrors `ham.audit.labels`'s "add every new code
here too, or the UI shows the raw value" convention.

Pure lookups only -- no DB, no I/O -- so templates and tests can import this freely.
"""

from __future__ import annotations

from .matching import MatchReason
from .models import NeedCategory, PreferredContactMethod, PropertyType, RelationshipToProperty
from .states import CancelReason, RequestStatus, VerificationMethod

NEED_CATEGORY_LABELS: dict[str, str] = dict(NeedCategory.choices)
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


def cancel_reason_label(value: str) -> str:
    return CANCEL_REASON_LABELS.get(value, value)


def match_reason_label(value: str) -> str:
    return MATCH_REASON_LABELS.get(value, value)
