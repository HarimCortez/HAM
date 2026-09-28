"""End-to-end integration test for the S2.3 orchestration (intake-contracts.md §8.3, §3):
draft -> verification code sent -> code verified -> `submit_and_issue_link` -> `resolve_token`
returns the request. Uses the *real* app-registered lookups
(`ham.requester_portal.apps.RequesterPortalConfig.ready()`, wired against real
`ham.requests.queries` functions) rather than the fakes the other unit tests in this directory
register, so a regression in the wiring itself (the "known loose end" this test guards) fails
here even if every other test's fakes still pass.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from django.core import mail

from ham.audit.models import AuditEvent
from ham.jobs import run_due_jobs_now
from ham.outbox.models import OutboxEvent
from ham.platform import otp
from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal import drafts, services, verification
from ham.requester_portal.models import RequesterAccessLink, RequesterVerificationChallenge
from ham.requests.models import Requester
from ham.requests.states import RequestStatus

pytestmark = pytest.mark.django_db(transaction=True)

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    c = FixedClock(T0)
    set_clock(c)
    return c


@pytest.fixture(autouse=True)
def _real_portal_lookups(real_portal_lookups):
    """Shared fixture (`tests/conftest.py::real_portal_lookups`): registers the real
    `ham.requester_portal.services` lookups (the exact same production callables
    `RequesterPortalConfig.ready()` uses) and restores them -- not `None` -- on teardown, so
    this module doesn't depend on run order relative to sibling files that register fakes
    (e.g. `test_links.py`)."""


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


def _verified_challenge(draft_id, *, email: str, code: str = "654321"):
    result = verification.request_intake_verification(draft_id=draft_id, email=email)
    assert result.status == "sent"
    run_due_jobs_now()
    challenge = RequesterVerificationChallenge.objects.get(draft_id=draft_id, purpose="intake")
    challenge.code_hash = otp.hash_value(code)
    challenge.save(update_fields=["code_hash"])
    verify_result = verification.verify_code(purpose="intake", email=email, code=code)
    assert verify_result.ok, verify_result.reason
    assert verify_result.challenge is not None
    return verify_result.challenge


class TestFullEmailIntakeFlow:
    def test_draft_code_submit_link_resolve(self, clock: FixedClock):
        start = drafts.start_draft(email="doris.p@example.org")
        assert start.status == "created"
        draft = start.draft
        assert draft is not None

        assert drafts.save_step(draft.id, _base_payload()) is not None

        mail.outbox.clear()
        challenge = _verified_challenge(draft.id, email="doris.p@example.org")
        assert len(mail.outbox) == 1  # the code+link email

        result = services.submit_and_issue_link(draft_id=draft.id, verification_id=challenge.id)
        request = result.request
        assert request.status == RequestStatus.SUBMITTED.value
        assert result.issued_link is not None
        token = result.issued_link.token

        # The stored request/property rows got the *translated* (ham.requests) vocabulary,
        # not the portal's own form codes (see `services._NEED_CATEGORY_TRANSLATION` et al).
        assert request.need_category == "roof"
        assert request.property.property_type == "single_family_home"
        requester = Requester.objects.get(request=request)
        assert requester.email == "doris.p@example.org"

        # requester_link.issued is audited (the loose end this test guards).
        event = AuditEvent.objects.get(action="requester_link.issued", target_id=str(request.id))
        assert event.actor_type == "requester"
        assert event.actor_user_id is None

        # The draft is consumed: resuming it now yields nothing.
        assert drafts.load_payload(draft.id) is None

        # resolve_token round-trips through the *real* registered facts lookup.
        ctx = services.resolve_token(token)
        assert ctx is not None
        assert ctx.request_id == request.id

        # The duplicate-check job (deferred by `submit_request`) moves the request on.
        run_due_jobs_now()
        request.refresh_from_db()
        assert request.status == RequestStatus.AWAITING_APPROVAL.value

        # regenerate_link: old (now-superseded) token no longer resolves, but a fresh code
        # is sent to the address on file (the real `register_request_contact_lookup`).
        mail.outbox.clear()
        regenerate_result = services.regenerate_link(token=token, email="doris.p@example.org")
        assert regenerate_result.status == "sent"
        run_due_jobs_now()
        assert len(mail.outbox) == 1
        assert RequesterVerificationChallenge.objects.filter(
            request_id=request.id, purpose="link_regeneration"
        ).exists()

        # find_my_request: the real email->request-ids lookup finds this request.
        mail.outbox.clear()
        find_result = services.find_my_request(email="doris.p@example.org")
        assert find_result.status == "sent"
        run_due_jobs_now()
        assert len(mail.outbox) == 1


class TestNoEmailIntakeFlow:
    def test_submit_without_email_lands_in_needs_phone_check_with_no_link(self, clock: FixedClock):
        start = drafts.start_draft()
        draft = start.draft
        assert draft is not None
        payload = _base_payload(
            email=None,
            no_email=True,
            full_name="No Email Guy",
            phone="(305) 555-0122",
        )
        assert drafts.save_step(draft.id, payload) is not None

        result = services.submit_and_issue_link(draft_id=draft.id, verification_id=None)
        request = result.request
        assert request.status == RequestStatus.NEEDS_PHONE_CHECK.value
        assert result.issued_link is None
        assert not RequesterAccessLink.objects.filter(request_id=request.id).exists()

        requester = Requester.objects.get(request=request)
        assert requester.email is None

        # No RequestSubmitted duplicate-check job runs yet for a phone-check request; no
        # link-issued audit either, since none was issued.
        assert not AuditEvent.objects.filter(
            action="requester_link.issued", target_id=str(request.id)
        ).exists()
        assert AuditEvent.objects.filter(
            action="request.submitted", target_id=str(request.id)
        ).exists()
        assert OutboxEvent.objects.filter(
            event_type="RequestSubmitted", aggregate_id=request.id
        ).exists()


class TestPortalLookupsRegisteredAtAppReady:
    """intake-contracts.md §8.3: without these three registrations, `issue_link`/
    `resolve_token`/`regenerate_link`/`find_my_request` raise `RuntimeError` at runtime. Runs
    against this module's own `_real_portal_lookups` fixture (the same callables
    `ham.requester_portal.apps.RequesterPortalConfig.ready()` registers at process startup) --
    proof that after `ready()` runs, none of the three raise `RuntimeError`, only ordinary
    "not found" results, for a request id that doesn't exist."""

    def test_facts_lookup_raises_value_error_not_runtime_error_for_unknown_request(self):
        with pytest.raises(ValueError):
            services._facts(uuid.uuid4())  # noqa: SLF001 - exercising the registered callable

    def test_contact_lookup_returns_none_for_unknown_request(self):
        assert services._contact(uuid.uuid4()) is None  # noqa: SLF001

    def test_email_lookup_returns_empty_list_for_unknown_email(self):
        assert services._requests_for_email("nobody@example.org") == []  # noqa: SLF001
