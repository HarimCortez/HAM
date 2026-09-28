"""Fixed choice lists for the public intake form (docs/ux/intake.md; Q-111, Q-113). These are
UX/content, not "fixed business rules" in the ``ham.rules`` sense (no timedelta/limit/weight)
— CLAUDE.md's rules-module requirement is for deadlines, limits, weights and retention
periods; a fixed multiple-choice vocabulary belongs with the form that offers it, same as
``ham.requests.states``' enums. Kept in one place so ``ham.requester_portal.forms`` and any
later leadership screen agree on the exact codes.

PRD-guardian M1/UX M2: need category (Q-109) and property type (Q-110) used to have a second,
independently-coded copy of their vocabulary here, translated into ``ham.requests.models``'
codes only at submission time. There is now exactly ONE vocabulary for each, defined on
``ham.requests.models.NeedCategory``/``PropertyType`` (the persisted layer) — this module
re-exports them so existing imports of ``ham.requester_portal.choices.NeedCategory``/
``PropertyType`` keep working without churn across every call site.
"""

from __future__ import annotations

from enum import StrEnum

from ham.requests.models import (  # noqa: F401 - re-exported
    NeedCategory,
    PropertyType,
    UrgencyReason,
)
from ham.requests.presentation import (  # noqa: F401 - re-exported
    NEED_CATEGORY_LABELS,
    PROPERTY_TYPE_LABELS,
    URGENCY_REASON_LABELS,
)


class ContactPreference(StrEnum):
    """Q-111: Email · Phone call only (the architecture's `text_message` value is never
    offered by this form, per the decided default)."""

    EMAIL = "email"
    PHONE_CALL = "phone_call"


CONTACT_PREFERENCE_LABELS: dict[ContactPreference, str] = {
    ContactPreference.EMAIL: "Email",
    ContactPreference.PHONE_CALL: "Phone call",
}


class Hazard(StrEnum):
    """Q-113: hazards, a required answer including an explicit "none known" option."""

    DOGS_OR_OTHER_ANIMALS = "dogs_or_other_animals"
    MOLD = "mold"
    EXPOSED_WIRING = "exposed_wiring"
    SAGGING_FLOORS_ROOF_STAIRS = "sagging_floors_roof_stairs"
    PESTS = "pests"
    SOMETHING_ELSE = "something_else"
    NONE_KNOWN = "none_known"


HAZARD_LABELS: dict[Hazard, str] = {
    Hazard.DOGS_OR_OTHER_ANIMALS: "Dogs or other animals",
    Hazard.MOLD: "Mold",
    Hazard.EXPOSED_WIRING: "Exposed wiring",
    Hazard.SAGGING_FLOORS_ROOF_STAIRS: "Sagging floors, roof or stairs",
    Hazard.PESTS: "Pests",
    Hazard.SOMETHING_ELSE: "Something else",
    Hazard.NONE_KNOWN: "None that I know of",
}

# ISO weekday numbers (1=Monday..7=Sunday), matching `ChurchProfile.serves_days` (Q-112).
WEEKDAY_LABELS: dict[int, str] = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}

AVAILABILITY_ANY_TIME = "any_time"
AVAILABILITY_MORNINGS = "mornings"
AVAILABILITY_AFTERNOONS = "afternoons"

# UX M4/N-M1: `UrgencyReason`/`URGENCY_REASON_LABELS` used to be a second, independently
# coded copy of this vocabulary (docs/ux/intake.md R2 "Why is it urgent?" chips) -- there is
# now exactly one, on `ham.requests.models` (re-exported above), same "duplicate vocabulary"
# fix pattern already applied to `NeedCategory`/`PropertyType` (see this module's own
# docstring).
