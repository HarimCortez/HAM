"""Step-2 fix round (FIX-A) M9/Q-114: an intake source code (``?c=``) resolves to an active
`IntakeSource` and records ``source="church_link"``; an unknown or deactivated code falls back
silently to ``source="public_form"``, never blocking submission.
"""

from __future__ import annotations

import datetime as dt

import pytest

from ham.jobs import run_due_jobs_now
from ham.platform import otp
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now
from ham.requester_portal import drafts, services, verification
from ham.requester_portal.models import IntakeSource, RequesterVerificationChallenge

pytestmark = pytest.mark.django_db(transaction=True)

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    c = FixedClock(T0)
    set_clock(c)
    return c


@pytest.fixture(autouse=True)
def _real_portal_lookups(real_portal_lookups):
    """Order-dependence fix (test-engineer pass, step 3): used to re-register its own copy of
    the real lookups and reset the globals to `None` on teardown rather than restoring them --
    confirmed (running the suite in reverse file order) to leak a `RuntimeError` into later,
    unrelated files. Depending on the shared `tests/conftest.py::real_portal_lookups` fixture
    keeps this file's own behavior identical while its teardown restores the real callables
    instead of `None`."""


def _base_payload(**overrides) -> dict:
    data = {
        "full_name": "Doris Palmer",
        "email": "doris.p@example.org",
        "phone": "(305) 555-0177",
        "relationship_to_property": "owner",
        "line1": "1400 NW Example Ave",
        "city": "Miami",
        "state": "FL",
        "postal_code": "33125",
        "property_type": "house",
        "need_category": "roof_or_ceiling",
        "description": "Water comes through my bedroom ceiling when it rains.",
        "hazards": ["none_known"],
        "availability": ["any_time"],
        "contact_preference": "email",
        "attested_statements": ["owner_authority", "responsibility"],
    }
    data.update(overrides)
    return data


def _submit(email: str, *, intake_source_code: str = "") -> services.SubmissionResult:
    start = drafts.start_draft(email=email)
    draft = start.draft
    assert draft is not None
    drafts.save_step(draft.id, _base_payload(email=email, intake_source_code=intake_source_code))
    result = verification.request_intake_verification(draft_id=draft.id, email=email)
    assert result.status == "sent"
    run_due_jobs_now()
    challenge = RequesterVerificationChallenge.objects.get(draft_id=draft.id, purpose="intake")
    challenge.code_hash = otp.hash_value("654321")
    challenge.save(update_fields=["code_hash"])
    verify_result = verification.verify_code(
        purpose="intake", email=email, code="654321", draft_id=draft.id
    )
    assert verify_result.ok and verify_result.challenge is not None
    submission = services.submit_and_issue_link(
        draft_id=draft.id, verification_id=verify_result.challenge.id
    )
    run_due_jobs_now()
    return submission


def test_active_code_resolves_to_church_link_source():
    source = IntakeSource.objects.create(
        code="ABC123", label="Front lobby QR", created_at=clock_now()
    )
    submission = _submit("doris.p@example.org", intake_source_code="ABC123")
    assert submission.request.source == "church_link"
    assert submission.request.intake_source_id == source.id


def test_unknown_code_falls_back_to_public_form_and_still_submits():
    submission = _submit("someone@example.org", intake_source_code="NOPE99")
    assert submission.request.source == "public_form"
    assert submission.request.intake_source_id is None


def test_deactivated_code_falls_back_to_public_form():
    IntakeSource.objects.create(
        code="OLD001",
        label="Retired flyer",
        created_at=clock_now(),
        deactivated_at=clock_now(),
    )
    submission = _submit("another@example.org", intake_source_code="OLD001")
    assert submission.request.source == "public_form"
    assert submission.request.intake_source_id is None


def test_no_code_at_all_is_public_form():
    submission = _submit("nocode@example.org")
    assert submission.request.source == "public_form"
    assert submission.request.intake_source_id is None
