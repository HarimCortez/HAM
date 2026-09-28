from __future__ import annotations

from ham.platform.church import ChurchProfileView
from ham.requester_portal.attestation import RelationshipToProperty, required_statements
from ham.requester_portal.choices import (
    AVAILABILITY_ANY_TIME,
    ContactPreference,
    Hazard,
    NeedCategory,
    PropertyType,
)
from ham.requester_portal.forms import validate_intake_payload

CHURCH = ChurchProfileView(
    name="Test Church",
    short_name="Test",
    mission_line="",
    display_font="",
    ui_font="",
    logo_on_dark="",
    logo_on_light="",
    logo_mark="",
    logo_alt="",
    phone="305-555-0100",
    email="ham@example.org",
    time_zone="America/New_York",
    website_url="",
    serves_days=(1, 2, 3, 4, 5, 7),
)


def _base_payload(**overrides) -> dict:
    data = {
        "full_name": "Doris Palmer",
        "email": "doris.p@gmail.com",
        "phone": "(305) 555-0177",
        "relationship_to_property": RelationshipToProperty.OWNER.value,
        "line1": "1400 NW Example Ave",
        "city": "Miami",
        "state": "FL",
        "postal_code": "33125",
        "property_type": PropertyType.HOUSE.value,
        "need_category": NeedCategory.ROOF_OR_CEILING.value,
        "description": "Water comes through my bedroom ceiling when it rains.",
        "hazards": [Hazard.NONE_KNOWN.value],
        "availability": [AVAILABILITY_ANY_TIME],
        "contact_preference": ContactPreference.EMAIL.value,
        "attested_statements": [c.value for c in required_statements(RelationshipToProperty.OWNER)],
    }
    data.update(overrides)
    return data


def test_valid_payload_passes():
    cleaned, errors = validate_intake_payload(_base_payload(), church=CHURCH)
    assert errors == {}
    assert cleaned is not None
    assert cleaned["email"] == "dorisp@gmail.com"  # Gmail dot-folding (matching.normalize_email)
    assert cleaned["phone"] == "+13055550177"
    assert cleaned["hazards"] == ["none_known"]


def test_missing_required_fields_are_reported():
    _cleaned, errors = validate_intake_payload({}, church=CHURCH)
    for field in (
        "full_name",
        "email",
        "phone",
        "relationship_to_property",
        "line1",
        "city",
        "state",
        "postal_code",
        "property_type",
        "need_category",
        "description",
        "hazards",
        "attested_statements",
    ):
        assert field in errors, field


def test_no_email_path_requires_no_email_field_and_forces_phone_contact():
    payload = _base_payload(no_email=True, email="")
    del payload["contact_preference"]
    cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert errors == {}
    assert cleaned["email"] is None
    assert cleaned["contact_preference"] == ContactPreference.PHONE_CALL.value


def test_no_email_with_email_present_is_an_error():
    payload = _base_payload(no_email=True)
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "email" in errors


def test_family_member_requires_owner_name():
    payload = _base_payload(
        relationship_to_property=RelationshipToProperty.AUTHORIZED_FAMILY_MEMBER.value,
        attested_statements=[
            c.value for c in required_statements(RelationshipToProperty.AUTHORIZED_FAMILY_MEMBER)
        ],
    )
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "owner_name" in errors

    payload["owner_name"] = "Mrs. Hall"
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert errors == {}


def test_hazards_none_known_cannot_combine_with_others():
    payload = _base_payload(hazards=[Hazard.NONE_KNOWN.value, Hazard.MOLD.value])
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "hazards" in errors


def test_hazards_something_else_requires_note():
    payload = _base_payload(hazards=[Hazard.SOMETHING_ELSE.value])
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "hazard_note" in errors

    payload["hazard_note"] = "A loose railing on the porch."
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert errors == {}


def test_urgent_requires_justification():
    payload = _base_payload(urgent_requested=True)
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "urgency_justification" in errors

    payload["urgency_justification"] = "Water is coming in fast."
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert errors == {}


def test_availability_must_be_a_day_the_church_serves():
    payload = _base_payload(availability=["6"])  # Saturday, not in CHURCH.serves_days
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "availability" in errors

    payload["availability"] = ["7", AVAILABILITY_ANY_TIME]
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert errors == {}


def test_certifications_required():
    payload = _base_payload(attested_statements=[])
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "attested_statements" in errors


def test_invalid_email_is_rejected():
    payload = _base_payload(email="not-an-email")
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "email" in errors


def test_invalid_phone_is_rejected():
    payload = _base_payload(phone="123")
    _cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "phone" in errors
