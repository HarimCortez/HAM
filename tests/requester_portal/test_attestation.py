from __future__ import annotations

from ham.requester_portal.attestation import (
    RelationshipToProperty,
    StatementCode,
    owner_name_required,
    required_statements,
    statements_satisfied,
)


def test_two_ticks_per_relationship():
    for rel in RelationshipToProperty:
        codes = required_statements(rel)
        assert len(codes) == 2
        assert StatementCode.RESPONSIBILITY in codes


def test_statements_satisfied_requires_both():
    required = {c.value for c in required_statements(RelationshipToProperty.OWNER)}
    assert statements_satisfied(RelationshipToProperty.OWNER, required)
    assert not statements_satisfied(RelationshipToProperty.OWNER, {next(iter(required))})
    assert not statements_satisfied(RelationshipToProperty.OWNER, set())


def test_owner_name_required_only_for_family_member():
    assert owner_name_required(RelationshipToProperty.AUTHORIZED_FAMILY_MEMBER)
    assert not owner_name_required(RelationshipToProperty.OWNER)
    assert not owner_name_required(RelationshipToProperty.TENANT)
