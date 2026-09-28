"""Public intake form validation (Q-099 required fields; docs/ux/intake.md R2-R6).

Deliberately a plain validation function over a dict, not a single ``django.forms.Form``: the
form is a multi-step wizard (docs/ux/intake.md R2..R6) whose answers accumulate into one
``IntakeDraft`` across several requests (``ham.requester_portal.drafts.save_step``), and the
*whole* payload is validated once, together, right before a verification code is sent — a
per-step Django ``Form`` subclass can still wrap one ``field_group`` below for step-level
inline errors; the full-payload check here is what actually gates "may this draft be
verified/submitted" (Q-100).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ham.platform.church import ChurchProfileView, is_valid_us_state
from ham.requests.certifications import (
    RelationshipToProperty,
    owner_name_required,
    required_statements,
    statements_satisfied,
)
from ham.requests.matching import normalize_email, normalize_phone, zip5

from .choices import (
    AVAILABILITY_AFTERNOONS,
    AVAILABILITY_ANY_TIME,
    AVAILABILITY_MORNINGS,
    ContactPreference,
    Hazard,
    NeedCategory,
    PropertyType,
)

_AVAILABILITY_TIME_WORDS = {AVAILABILITY_ANY_TIME, AVAILABILITY_MORNINGS, AVAILABILITY_AFTERNOONS}

_MAX_TEXT = 4000  # generous cap so a description/note can never blow up the encrypted payload


@dataclass(frozen=True, slots=True)
class ValidatedIntake:
    """What a successfully validated payload becomes: normalized values, ready to hand to
    ``ham.requests.services.submit_request`` (S2.2) once the draft is verified."""

    cleaned: dict = field(default_factory=dict)


def _require_text(data: dict, errors: dict, key: str, *, label: str, max_len: int = 200) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        errors[key] = f"{label} is required."
    elif len(value) > max_len:
        errors[key] = f"{label} is too long."
    return value


def validate_intake_payload(
    data: dict, *, church: ChurchProfileView
) -> tuple[dict | None, dict[str, str]]:
    """Validate a merged draft payload. Returns ``(cleaned, {})`` on success or
    ``(None, errors)`` keyed by field name (S2.7 shows these inline, per field, next to the
    step that collects it — no field is silently defaulted)."""
    errors: dict[str, str] = {}
    cleaned: dict = {}

    cleaned["full_name"] = _require_text(data, errors, "full_name", label="Name")

    # --- Email or "I don't use email" (Q-025) ------------------------------------------
    no_email = bool(data.get("no_email"))
    raw_email = str(data.get("email") or "").strip()
    if no_email:
        if raw_email:
            errors["email"] = "Remove the email address, or untick “I don’t use email.”"
        cleaned["email"] = None
        cleaned["contact_preference"] = ContactPreference.PHONE_CALL.value
    else:
        normalized_email = normalize_email(raw_email) if raw_email else None
        if not raw_email:
            errors["email"] = "Enter an email address, or choose “I don’t use email.”"
        elif normalized_email is None:
            errors["email"] = "That doesn't look like a valid email address."
        cleaned["email"] = normalized_email
        contact_pref = str(data.get("contact_preference") or "").strip()
        try:
            cleaned["contact_preference"] = ContactPreference(contact_pref).value
        except ValueError:
            errors["contact_preference"] = "Choose how we should reach you."
    cleaned["no_email"] = no_email

    # --- Anything else about reaching/visiting (Q-148, optional) -------------------------
    cleaned["contact_note"] = str(data.get("note") or "").strip()[:_MAX_TEXT]

    # --- Phone (always required, Q-099) -------------------------------------------------
    raw_phone = str(data.get("phone") or "").strip()
    normalized_phone = normalize_phone(raw_phone) if raw_phone else None
    if not raw_phone:
        errors["phone"] = "Enter a phone number."
    elif normalized_phone is None:
        errors["phone"] = "That doesn't look like a valid phone number."
    cleaned["phone"] = normalized_phone

    # --- Relationship + property authority (Q-105, §6.2) --------------------------------
    relationship_raw = str(data.get("relationship_to_property") or "").strip()
    relationship: RelationshipToProperty | None = None
    try:
        relationship = RelationshipToProperty(relationship_raw)
        cleaned["relationship_to_property"] = relationship.value
    except ValueError:
        errors["relationship_to_property"] = "Choose your relationship to the property."

    if relationship is not None and owner_name_required(relationship):
        cleaned["owner_name"] = _require_text(
            data, errors, "owner_name", label="The property owner's name"
        )
    else:
        cleaned["owner_name"] = ""

    # --- Address (Q-099) -----------------------------------------------------------------
    cleaned["line1"] = _require_text(data, errors, "line1", label="Street address")
    cleaned["line2"] = str(data.get("line2") or "").strip()[:200]
    cleaned["city"] = _require_text(data, errors, "city", label="City")
    # Q-147: exactly one of the 50 states + DC, not just "any text up to 2 characters" --
    # prefilled from the church's own state on R3 ("Florida · Change") so most requesters
    # never have to touch this field at all.
    raw_state = str(data.get("state") or "").strip().upper()
    if not raw_state:
        errors["state"] = "Choose a state."
    elif not is_valid_us_state(raw_state):
        errors["state"] = "That doesn't look like a US state."
    cleaned["state"] = raw_state if is_valid_us_state(raw_state) else ""
    raw_zip = str(data.get("postal_code") or "").strip()
    normalized_zip = zip5(raw_zip)
    if not raw_zip:
        errors["postal_code"] = "Enter a ZIP code."
    elif normalized_zip is None:
        errors["postal_code"] = "That doesn't look like a valid ZIP code."
    cleaned["postal_code"] = normalized_zip

    property_type_raw = str(data.get("property_type") or "").strip()
    try:
        cleaned["property_type"] = PropertyType(property_type_raw).value
    except ValueError:
        errors["property_type"] = "Choose the type of home."

    # --- What's needed (Q-109) ------------------------------------------------------------
    category_raw = str(data.get("need_category") or "").strip()
    try:
        cleaned["need_category"] = NeedCategory(category_raw).value
    except ValueError:
        errors["need_category"] = "Choose what kind of help is needed."

    cleaned["description"] = _require_text(
        data, errors, "description", label="What's needed", max_len=_MAX_TEXT
    )

    # --- Urgent (optional; justification required iff ticked) ----------------------------
    urgent_requested = bool(data.get("urgent_requested"))
    cleaned["urgent_requested"] = urgent_requested
    justification = str(data.get("urgency_justification") or "").strip()
    if urgent_requested and not justification:
        errors["urgency_justification"] = "Tell us why this is urgent."
    cleaned["urgency_justification"] = justification if urgent_requested else ""

    # --- Hazards: required, "none known" is a valid answer (Q-113) -----------------------
    hazards_raw = data.get("hazards") or []
    if not isinstance(hazards_raw, list) or not hazards_raw:
        errors["hazards"] = "Choose at least one (or “None that I know of”)."
        cleaned["hazards"] = []
    else:
        try:
            hazards = [Hazard(h).value for h in hazards_raw]
        except ValueError:
            errors["hazards"] = "Choose from the list."
            hazards = []
        if Hazard.NONE_KNOWN.value in hazards and len(hazards) > 1:
            errors["hazards"] = "“None that I know of” can't be combined with other hazards."
        cleaned["hazards"] = hazards
    hazard_note = str(data.get("hazard_note") or "").strip()
    if Hazard.SOMETHING_ELSE.value in cleaned.get("hazards", []) and not hazard_note:
        errors["hazard_note"] = "Tell us more about the hazard."
    cleaned["hazard_note"] = hazard_note[:_MAX_TEXT]

    # --- Availability (Q-112): days HAM serves + time-of-day chips -----------------------
    # M5/Q-099 (decided): availability is required, same as the other §6.1 fields -- "Any
    # time works" is itself a valid, single-chip answer, so an empty list is always a
    # missing-answer error, never "nothing to say here".
    availability_raw = data.get("availability") or []
    allowed_days = {str(d) for d in church.serves_days}
    if not isinstance(availability_raw, list):
        availability_raw = []
    bad_availability = [
        v for v in availability_raw if v not in _AVAILABILITY_TIME_WORDS and v not in allowed_days
    ]
    if not availability_raw:
        errors["availability"] = "Choose at least one time (Any time works counts)."
    elif bad_availability:
        errors["availability"] = "Choose from the times we offer."
    cleaned["preferred_availability"] = [
        str(v) for v in availability_raw if v not in bad_availability
    ]

    # --- Certifications (Q-103) -----------------------------------------------------------
    accepted = set(data.get("attested_statements") or [])
    if relationship is None:
        if not accepted:
            errors["attested_statements"] = "Tick both statements."
        # No relationship yet to check codes against -- store nothing rather than guess.
        cleaned["attested_statements"] = []
    else:
        if not statements_satisfied(relationship, accepted):
            errors["attested_statements"] = "Tick both statements."
        # PRD-guardian cert-codes fix: store only codes within this relationship's own
        # `required_statements(relationship)` -- a stray/forged code in the POST body (one
        # that isn't even offered for this relationship) is dropped, never persisted
        # verbatim. `statements_satisfied` only checks a *subset* relationship, so it alone
        # wouldn't have caught extra junk riding along with the two real ticks.
        allowed_codes = {code.value for code in required_statements(relationship)}
        cleaned["attested_statements"] = sorted(accepted & allowed_codes)

    # --- Church-issued source code (Q-114), optional --------------------------------------
    cleaned["intake_source_code"] = str(data.get("intake_source_code") or "").strip().upper()[:6]

    if errors:
        return None, errors
    return cleaned, {}


__all__ = ["ValidatedIntake", "validate_intake_payload"]
