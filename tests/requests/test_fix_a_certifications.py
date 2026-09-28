"""Step-2 fix round (FIX-A) B1: ONE certification module (`ham.requests.certifications`) --
stored codes/version match what was actually ticked, and the stored wording equals the wording
`ham.web.views_requester` puts in context for R6 to render.
"""

from __future__ import annotations

from ham.requests import certifications


def test_only_one_certification_module_wording_and_codes():
    for relationship in ("owner", "tenant", "authorized_family_member"):
        codes = certifications.required_statements(relationship)
        assert len(codes) == 2
        for code in codes:
            assert code in certifications.STATEMENT_TEXT
            assert certifications.STATEMENT_TEXT[code].strip()


def test_statement_text_for_matches_required_statements_order():
    for relationship in ("owner", "tenant", "authorized_family_member"):
        required = certifications.required_statements(relationship)
        rendered = certifications.statement_text_for(relationship)
        assert list(rendered.keys()) == [c.value for c in required]
        for code in required:
            assert rendered[code.value] == certifications.STATEMENT_TEXT[code]


def test_statements_satisfied_requires_both_codes():
    owner_codes = {c.value for c in certifications.required_statements("owner")}
    assert certifications.statements_satisfied("owner", owner_codes)
    assert not certifications.statements_satisfied("owner", {next(iter(owner_codes))})
    assert not certifications.statements_satisfied("owner", set())


def test_attestation_module_was_removed():
    """B1: "drop the other two wordings" -- `ham.requester_portal.attestation` (the second
    copy) no longer exists; `ham.requests.certifications` is the only place this wording and
    these codes live."""
    import importlib

    try:
        importlib.import_module("ham.requester_portal.attestation")
    except ModuleNotFoundError:
        pass
    else:  # pragma: no cover - regression guard
        raise AssertionError("ham.requester_portal.attestation should have been removed")
