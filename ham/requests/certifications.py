"""ONE canonical intake certification module: wording + codes + version (PRD §6.2, §41;
Q-103; PRD-guardian B1).

Before this fixup there were three independent copies of "the two certification ticks" —
this module's own older 5-statement wording, `ham.requester_portal.attestation`'s 4-code
2-tick wording, and a third, slightly different wording hard-coded directly into
`ham/web/templates/web/requester/r6_review.html`. All three used different vocabularies for
the *same* real-world tick boxes, which meant the review screen (R6) could show text that did
not match what actually got persisted. This module is now the only place the wording, the
codes, and the version live; R6's template renders `STATEMENT_TEXT` via context (see
`ham.web.views_requester._step_context`) instead of hard-coding its own copy, and
`ham.requests.services.submit_request` stores exactly the codes the requester ticked
(`payload.attested_statements`, unmodified) plus `ATTESTATION_VERSION` — never a re-derived
"the statements this relationship requires" list. A test
(`tests/requests/test_fix_a_certifications.py`) asserts the stored text equals the rendered
text for every relationship.

Pure Python, no Django, so `ham.requester_portal` (which sits *above* this app in the layer
order and may import downward) and any future audit/report code can import it without a model
dependency.

PRD-GAP Q-103: this wording is a draft, pending review by the owner and ideally church
counsel before launch, per the plan's own note — unchanged by this fixup.

Bump `ATTESTATION_VERSION` (and add a changelog note) whenever any `STATEMENT_TEXT` value
changes — existing requests keep whatever version they actually attested to (append-only,
CLAUDE.md); this constant only affects requests submitted from now on.
"""

from __future__ import annotations

from enum import StrEnum

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
        "I own this home, and I give HAM permission to do the work we agree on. The "
        "information I've given is true to the best of my knowledge."
    ),
    StatementCode.FAMILY_AUTHORITY: (
        "The property owner has authorized me to make this request. The information I've "
        "given is true to the best of my knowledge."
    ),
    StatementCode.TENANT_AUTHORITY: (
        "I rent this home. Before any work begins, I'll get written permission from my "
        "landlord or property owner. The information I've given is true to the best of my "
        "knowledge."
    ),
    StatementCode.RESPONSIBILITY: (
        "If my HOA, condominium association, landlord or property manager needs to approve "
        "work, I'll get their OK. What I've shared is true to the best of my knowledge."
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


def statements_satisfied(relationship: RelationshipToProperty | str, accepted) -> bool:
    """Whether ``accepted`` (the codes the requester actually ticked) cover both required
    statements for ``relationship`` — Q-099 "certifications" required field."""
    required = {code.value for code in required_statements(relationship)}
    return required.issubset(set(accepted))


# Kept as an alias: `ham.requests.services.submit_request` (a lower-layer, S2.2-owned module)
# already called this name before the fixup; renaming every call site is unnecessary churn.
statements_satisfy_relationship = statements_satisfied


def owner_name_required(relationship: RelationshipToProperty | str) -> bool:
    """intake.md §3 `Property.owner_name` "required for authorized_family_member"."""
    return RelationshipToProperty(relationship) is RelationshipToProperty.AUTHORIZED_FAMILY_MEMBER


def statement_text_for(relationship: RelationshipToProperty | str) -> dict[str, str]:
    """R6's own two tick-box texts, in stable order (authority tick, then responsibility
    tick), keyed by their string code — what `ham.web.views_requester` puts in context for
    the review template to render, instead of the template hard-coding its own copy."""
    return {code.value: STATEMENT_TEXT[code] for code in required_statements(relationship)}


__all__ = [
    "ATTESTATION_VERSION",
    "RelationshipToProperty",
    "STATEMENT_TEXT",
    "StatementCode",
    "owner_name_required",
    "required_statements",
    "statement_text_for",
    "statements_satisfied",
    "statements_satisfy_relationship",
]
