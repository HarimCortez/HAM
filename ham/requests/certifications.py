"""Intake certification wording and versions (PRD §6.2, §41; intake.md D3, Q-102). Pure
Python, no Django, so ``ham.requests.services`` and any future audit/report code can import
it without a model dependency.

PRD-GAP Q-102: draft wording from intake.md plan §0 D3, awaiting owner/counsel review. HAM
stores the exact version a requester agreed to, forever, with the request (never edited --
a new wording is a new version; old requests keep the old words, same discipline as §41
agreements).
"""

from __future__ import annotations

# PRD-GAP Q-102: proposed default in use; owner/counsel to review before launch.
CURRENT_ATTESTATION_VERSION = "intake-v1"

STATEMENT_TRUE_TO_KNOWLEDGE = "true_to_knowledge"
STATEMENT_OWNER_PERMISSION = "owner_permission"
STATEMENT_FAMILY_AUTHORIZED = "family_authorized"
STATEMENT_TENANT_PERMISSION_PENDING = "tenant_permission_pending"
STATEMENT_HOA_RESPONSIBILITY = "hoa_responsibility"

# Draft wording, intake.md plan §0 D3.
ATTESTATION_STATEMENTS: dict[str, str] = {
    STATEMENT_TRUE_TO_KNOWLEDGE: "The information I've given is true to the best of my knowledge.",
    STATEMENT_OWNER_PERMISSION: "I own this property and I give HAM permission to work there.",
    STATEMENT_FAMILY_AUTHORIZED: ("The property owner has authorized me to make this request."),
    STATEMENT_TENANT_PERMISSION_PENDING: (
        "I will get written permission from the property owner or landlord before any work begins."
    ),
    STATEMENT_HOA_RESPONSIBILITY: (
        "I'm responsible for any approval my HOA, condominium association, landlord or "
        "property manager requires."
    ),
}

# Required statement codes by relationship to the property (Q-102). Everyone gives the
# "true to my knowledge" and HOA-responsibility statements; the middle one depends on how
# they're connected to the property (§6.2).
REQUIRED_STATEMENTS_BY_RELATIONSHIP: dict[str, tuple[str, ...]] = {
    "owner": (
        STATEMENT_TRUE_TO_KNOWLEDGE,
        STATEMENT_OWNER_PERMISSION,
        STATEMENT_HOA_RESPONSIBILITY,
    ),
    "authorized_family_member": (
        STATEMENT_TRUE_TO_KNOWLEDGE,
        STATEMENT_FAMILY_AUTHORIZED,
        STATEMENT_HOA_RESPONSIBILITY,
    ),
    "tenant": (
        STATEMENT_TRUE_TO_KNOWLEDGE,
        STATEMENT_TENANT_PERMISSION_PENDING,
        STATEMENT_HOA_RESPONSIBILITY,
    ),
}


def required_statements(relationship: str) -> tuple[str, ...]:
    try:
        return REQUIRED_STATEMENTS_BY_RELATIONSHIP[relationship]
    except KeyError as exc:
        raise ValueError(f"unknown relationship_to_property: {relationship!r}") from exc


def statements_satisfy_relationship(relationship: str, attested: tuple[str, ...]) -> bool:
    """Every required statement code for ``relationship`` is present in ``attested``."""
    required = set(required_statements(relationship))
    return required.issubset(set(attested))
