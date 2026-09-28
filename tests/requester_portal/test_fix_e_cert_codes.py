"""FIX-E PRD re-check regression: `ham.requester_portal.forms.validate_intake_payload` must
store only certification codes within `required_statements(relationship)` -- a stray/forged
code riding along with the two real ticks (or one belonging to a *different* relationship's
own statement set) is dropped, never persisted verbatim. New file per wave brief.
"""

from __future__ import annotations

from ham.requester_portal.forms import validate_intake_payload
from ham.requests.certifications import RelationshipToProperty, required_statements

from .test_forms import CHURCH, _base_payload


def test_only_codes_required_for_this_relationship_are_stored():
    required = {c.value for c in required_statements(RelationshipToProperty.OWNER)}
    payload = _base_payload(
        attested_statements=[*required, "not_a_real_statement", "hoa_responsibility"]
    )
    cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert errors == {}
    assert set(cleaned["attested_statements"]) == required
    assert "not_a_real_statement" not in cleaned["attested_statements"]
    assert "hoa_responsibility" not in cleaned["attested_statements"]


def test_a_tenants_own_authority_code_is_dropped_for_an_owner_submission():
    """The authority-tick code differs by relationship (`_AUTHORITY_BY_RELATIONSHIP`) -- a
    tenant's own code has no business being stored on an owner's request even though both are
    otherwise "real" statement codes somewhere in the system."""
    owner_required = {c.value for c in required_statements(RelationshipToProperty.OWNER)}
    tenant_required = {c.value for c in required_statements(RelationshipToProperty.TENANT)}
    extra_tenant_only = tenant_required - owner_required
    assert extra_tenant_only, "expected the two relationships to use different authority codes"

    payload = _base_payload(
        relationship_to_property=RelationshipToProperty.OWNER.value,
        attested_statements=[*owner_required, *extra_tenant_only],
    )
    cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert errors == {}
    assert set(cleaned["attested_statements"]) == owner_required


def test_only_junk_codes_still_fails_validation():
    payload = _base_payload(attested_statements=["not_a_real_statement"])
    cleaned, errors = validate_intake_payload(payload, church=CHURCH)
    assert "attested_statements" in errors
