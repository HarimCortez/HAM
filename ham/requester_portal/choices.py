"""Fixed choice lists for the public intake form (docs/ux/intake.md; Q-109, Q-110, Q-111,
Q-113). These are UX/content, not "fixed business rules" in the ``ham.rules`` sense (no
timedelta/limit/weight) — CLAUDE.md's rules-module requirement is for deadlines, limits,
weights and retention periods; a fixed multiple-choice vocabulary belongs with the form that
offers it, same as ``ham.requests.states``' enums. Kept in one place so
``ham.requester_portal.forms`` and any later leadership screen agree on the exact codes.
"""

from __future__ import annotations

from enum import StrEnum


class NeedCategory(StrEnum):
    """Q-109: "What kind of help?", one required choice, list per docs/ux/intake.md."""

    ROOF_OR_CEILING = "roof_or_ceiling"
    PLUMBING_OR_WATER = "plumbing_or_water"
    ELECTRICAL = "electrical"
    DOORS_WINDOWS_LOCKS = "doors_windows_locks"
    FLOORS_OR_STAIRS = "floors_or_stairs"
    RAMPS_RAILS_GRAB_BARS = "ramps_rails_grab_bars"
    PAINTING_OR_WALLS = "painting_or_walls"
    YARD_OR_OUTSIDE = "yard_or_outside"
    SOMETHING_ELSE = "something_else"


NEED_CATEGORY_LABELS: dict[NeedCategory, str] = {
    NeedCategory.ROOF_OR_CEILING: "Roof or ceiling",
    NeedCategory.PLUMBING_OR_WATER: "Plumbing or water",
    NeedCategory.ELECTRICAL: "Electrical",
    NeedCategory.DOORS_WINDOWS_LOCKS: "Doors, windows or locks",
    NeedCategory.FLOORS_OR_STAIRS: "Floors or stairs",
    NeedCategory.RAMPS_RAILS_GRAB_BARS: "Ramps, rails or grab bars",
    NeedCategory.PAINTING_OR_WALLS: "Painting or walls",
    NeedCategory.YARD_OR_OUTSIDE: "Yard or outside",
    NeedCategory.SOMETHING_ELSE: "Something else or not sure",
}


class PropertyType(StrEnum):
    """Q-110: property type choices."""

    HOUSE = "house"
    TOWNHOUSE = "townhouse"
    APARTMENT_OR_CONDO = "apartment_or_condo"
    MOBILE_OR_MANUFACTURED_HOME = "mobile_or_manufactured_home"
    OTHER = "other"


PROPERTY_TYPE_LABELS: dict[PropertyType, str] = {
    PropertyType.HOUSE: "House",
    PropertyType.TOWNHOUSE: "Townhouse",
    PropertyType.APARTMENT_OR_CONDO: "Apartment or condo",
    PropertyType.MOBILE_OR_MANUFACTURED_HOME: "Mobile or manufactured home",
    PropertyType.OTHER: "Other",
}


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


class UrgencyReason(StrEnum):
    """docs/ux/intake.md R2 "Why is it urgent?" chips (§10). `ham.requester_portal.forms`
    only validates the free-text `urgency_justification` it feeds into (required once urgent
    is ticked); S2.7's step view folds the chosen chip's label into that text before saving,
    so this vocabulary is UI-only, same reasoning as the rest of this module's docstring."""

    SOMEONE_COULD_GET_HURT = "someone_could_get_hurt"
    WATER_OR_DAMAGE = "water_or_damage"
    NO_UTILITIES = "no_utilities"
    CANT_GET_IN_OR_OUT = "cant_get_in_or_out"
    SOMETHING_ELSE = "something_else"


URGENCY_REASON_LABELS: dict[UrgencyReason, str] = {
    UrgencyReason.SOMEONE_COULD_GET_HURT: "Someone could get hurt",
    UrgencyReason.WATER_OR_DAMAGE: "Water is coming in or damage is getting worse",
    UrgencyReason.NO_UTILITIES: "No power, water, heat or cooling",
    UrgencyReason.CANT_GET_IN_OR_OUT: "Can't get in or out of the home safely",
    UrgencyReason.SOMETHING_ELSE: "Something else",
}
