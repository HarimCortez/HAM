"""Q-103: the two versioned intake certification ticks (docs/ux/intake.md R6, PRD §6.2, §41).

"2 ticks: (1) authority statement worded by relationship, (2) HOA/landlord responsibility +
'true to the best of my knowledge'." Each accepted request stores ``ATTESTATION_VERSION`` and
the exact statement codes ticked (never re-derived later), so a future wording change never
silently rewrites what an old requester actually agreed to (append-only, CLAUDE.md).

PRD-GAP Q-103: this wording is a draft, pending review by the owner and ideally church
counsel before launch, per the plan's own note.
"""

from __future__ import annotations

from enum import StrEnum

# Bump this (and add a changelog entry — CLAUDE.md "no magic numbers"/versioned records)
# whenever any STATEMENT_TEXT below changes. Existing requests keep whatever version they
# actually attested to; this constant only affects requests submitted from now on.
ATTESTATION_VERSION = "2026-09-28.1"


class RelationshipToProperty(StrEnum):
    """Q-105: exactly three values ("I own it" / "I rent it" / "It's a family member's
    home"); no fourth "helper" relationship — a helper fills the form in *for* the resident,
    who is the requester (docs/ux/intake.md R3)."""

    OWNER = "owner"
    TENANT = "tenant"
    AUTHORIZED_FAMILY_MEMBER = "authorized_family_member"


class StatementCode(StrEnum):
    """One code per possible tick-box text. Tick 1 (authority) is relationship-specific;
    tick 2 (responsibility) is the same for everyone."""

    OWNER_AUTHORITY = "owner_authority"
    FAMILY_AUTHORITY = "family_authority"
    TENANT_AUTHORITY = "tenant_authority"
    RESPONSIBILITY = "responsibility"


STATEMENT_TEXT: dict[StatementCode, str] = {
    StatementCode.OWNER_AUTHORITY: (
        "I own this property and I give HAM permission to work there. The information I've "
        "given is true to the best of my knowledge."
    ),
    StatementCode.FAMILY_AUTHORITY: (
        "The property owner has authorized me to make this request. The information I've "
        "given is true to the best of my knowledge."
    ),
    StatementCode.TENANT_AUTHORITY: (
        "I will get written permission from the property owner or landlord before any work "
        "begins. The information I've given is true to the best of my knowledge."
    ),
    StatementCode.RESPONSIBILITY: (
        "I'm responsible for any approval my HOA, condominium association, landlord or "
        "property manager requires."
    ),
}

# The authority statement code required for each relationship (tick 1); tick 2
# (RESPONSIBILITY) is required for every relationship.
_AUTHORITY_BY_RELATIONSHIP: dict[RelationshipToProperty, StatementCode] = {
    RelationshipToProperty.OWNER: StatementCode.OWNER_AUTHORITY,
    RelationshipToProperty.AUTHORIZED_FAMILY_MEMBER: StatementCode.FAMILY_AUTHORITY,
    RelationshipToProperty.TENANT: StatementCode.TENANT_AUTHORITY,
}


def required_statements(
    relationship: RelationshipToProperty | str,
) -> tuple[StatementCode, StatementCode]:
    """The exact two statement codes this relationship must tick, in a stable order."""
    rel = RelationshipToProperty(relationship)
    return (_AUTHORITY_BY_RELATIONSHIP[rel], StatementCode.RESPONSIBILITY)


def statements_satisfied(relationship: RelationshipToProperty | str, accepted: set[str]) -> bool:
    """Whether ``accepted`` (the codes the requester actually ticked) cover both required
    statements for ``relationship`` — Q-099 "certifications" required field."""
    required = {code.value for code in required_statements(relationship)}
    return required.issubset(accepted)


def owner_name_required(relationship: RelationshipToProperty | str) -> bool:
    """intake.md §3 `Property.owner_name` "required for authorized_family_member"."""
    return RelationshipToProperty(relationship) is RelationshipToProperty.AUTHORIZED_FAMILY_MEMBER
