"""S2.6: `ham.requester_portal.notifications` -- requester email builders (docs/ux/intake.md
§7 rows E2/E2u/E3/E5/E6/E7; Q-102 "every requester email carries the link"; §68 neutral
subjects).
"""

from __future__ import annotations

import uuid

import pytest
from django.core import mail

from ham.jobs import run_due_jobs_now
from ham.media.services import reopen_batch
from ham.outbox.models import OutboxEvent
from ham.requester_portal import services
from ham.requester_portal.models import RequesterAccessLink
from ham.requester_portal.notifications import (
    _build_closed_email,
    _build_more_photos_email,
    _build_new_link_email,
    _build_request_received_email,
)
from ham.requests.models import Requester
from ham.requests.services import cancel_request, submit_request
from tests.requests.conftest import actor_ctx, make_payload, no_email_payload

pytestmark = pytest.mark.django_db


DISTINCTIVE_NAME = "Zbigniew Kowalczyk"
DISTINCTIVE_STREET = "8842 Windswept Hollow Terrace"
DISTINCTIVE_PHONE = "+13055559981"
DISTINCTIVE_EMAIL = "zbigniew.kowalczyk@example.org"


@pytest.fixture
def requester_ctx():
    from ham.authz.context import RequesterContext

    return RequesterContext(request_id=None)


@pytest.fixture
def director_ctx():
    return actor_ctx(roles=frozenset({"HAM_DIRECTOR"}))


@pytest.fixture(autouse=True)
def _real_portal_lookups():
    """Some sibling test modules (e.g. `test_links.py`) register fakes for
    `ham.requester_portal.services`'s cross-app lookups and reset the globals to `None` on
    teardown rather than restoring the real ones -- so, run after them in the same session,
    this module cannot rely on `RequesterPortalConfig.ready()`'s process-startup registration
    still being in place (same fixture as `test_submission_flow.py`'s own, duplicated here for
    the same reason: calling `ready()` again would also re-register the periodic purge jobs)."""
    from ham.requests import queries as requests_queries

    def _facts_lookup(request_id):
        facts = requests_queries.request_facts_for_portal(request_id)
        return services.RequestLinkFacts(status=facts.status, closed_at=facts.closed_at)

    services.register_request_facts_lookup(_facts_lookup)
    services.register_request_contact_lookup(requests_queries.request_contact_for_portal)
    services.register_email_to_request_ids_lookup(requests_queries.request_ids_for_portal_email)
    yield
    services._request_facts_lookup = None  # noqa: SLF001 - test isolation
    services._request_contact_lookup = None  # noqa: SLF001
    services._email_to_request_ids_lookup = None  # noqa: SLF001


def _submit(ctx, **overrides):
    payload = make_payload(
        full_name=DISTINCTIVE_NAME,
        phone=DISTINCTIVE_PHONE,
        email=DISTINCTIVE_EMAIL,
        line1=DISTINCTIVE_STREET,
        **overrides,
    )
    return submit_request(ctx, draft_id=uuid.uuid4(), verification_id=uuid.uuid4(), payload=payload)


def _event(event_type: str, *, aggregate_type: str, aggregate_id, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )


class TestRequestReceivedEmail:
    def test_sends_with_the_link_when_email_present(self, requester_ctx):
        request = _submit(requester_ctx)
        issued = services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)

        event = _event(
            "RequestSubmitted",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "source": "public_form", "urgent": False},
        )
        email = _build_request_received_email(event)
        assert email is not None
        assert email.to == DISTINCTIVE_EMAIL
        assert issued.token in email.text_body
        assert request.display_number in email.subject

    def test_urgent_adds_the_urgent_line(self, requester_ctx):
        request = _submit(requester_ctx, urgent_requested=True, urgency_justification="leak")
        services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)
        event = _event(
            "RequestSubmitted",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "source": "public_form", "urgent": True},
        )
        email = _build_request_received_email(event)
        assert email is not None
        assert "911" in email.text_body

    def test_no_email_on_file_means_no_email(self, requester_ctx):
        payload = no_email_payload(full_name=DISTINCTIVE_NAME, phone=DISTINCTIVE_PHONE)
        request = submit_request(
            requester_ctx, draft_id=uuid.uuid4(), verification_id=None, payload=payload
        )
        event = _event(
            "RequestSubmitted",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "source": "public_form", "urgent": False},
        )
        assert _build_request_received_email(event) is None

    @pytest.mark.django_db(transaction=True)
    def test_end_to_end_through_the_outbox(self, requester_ctx):
        """The real submit_and_issue_link -> outbox -> email path (not just the builder in
        isolation): guards the app registration in `RequesterPortalConfig.ready()`."""
        from ham.requester_portal import drafts, verification

        payload = {
            "full_name": DISTINCTIVE_NAME,
            "email": DISTINCTIVE_EMAIL,
            "phone": DISTINCTIVE_PHONE,
            "relationship_to_property": "owner",
            "line1": DISTINCTIVE_STREET,
            "city": "Miami",
            "state": "FL",
            "postal_code": "33125",
            "property_type": "house",
            "need_category": "roof_or_ceiling",
            "description": "leak",
            "hazards": ["none_known"],
            "availability": ["any_time"],
            "contact_preference": "email",
            "attested_statements": ["owner_authority", "responsibility"],
        }
        start = drafts.start_draft(email=DISTINCTIVE_EMAIL)
        draft = start.draft
        assert draft is not None
        drafts.save_step(draft.id, payload)
        from ham.platform import otp
        from ham.requester_portal.models import RequesterVerificationChallenge

        result = verification.request_intake_verification(
            draft_id=draft.id, email=DISTINCTIVE_EMAIL
        )
        assert result.status == "sent"
        run_due_jobs_now()
        challenge = RequesterVerificationChallenge.objects.get(draft_id=draft.id, purpose="intake")
        challenge.code_hash = otp.hash_value("111222")
        challenge.save(update_fields=["code_hash"])
        verify_result = verification.verify_code(
            purpose="intake", email=DISTINCTIVE_EMAIL, code="111222"
        )
        assert verify_result.ok

        mail.outbox.clear()
        submission = services.submit_and_issue_link(
            draft_id=draft.id, verification_id=verify_result.challenge.id
        )
        run_due_jobs_now()
        received = [m for m in mail.outbox if "We received your" in m.subject]
        assert len(received) == 1
        assert submission.issued_link is not None
        assert submission.issued_link.token in received[0].body
        assert DISTINCTIVE_NAME not in received[0].subject
        assert DISTINCTIVE_STREET not in received[0].subject
        assert DISTINCTIVE_PHONE not in received[0].subject


class TestNewLinkEmail:
    def test_initial_kind_sends_nothing(self, requester_ctx):
        request = _submit(requester_ctx)
        issued = services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)
        event = _event(
            "RequesterAccessLinkIssued",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={
                "request_id": str(request.id),
                "link_id": str(issued.link.id),
                "kind": "initial",
            },
        )
        assert _build_new_link_email(event) is None

    def test_regenerated_kind_sends_the_new_link(self, requester_ctx):
        request = _submit(requester_ctx)
        services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)
        issued = services.issue_link(
            request_id=request.id, kind=RequesterAccessLink.KIND_REGENERATED
        )
        event = _event(
            "RequesterAccessLinkIssued",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={
                "request_id": str(request.id),
                "link_id": str(issued.link.id),
                "kind": "regenerated",
            },
        )
        email = _build_new_link_email(event)
        assert email is not None
        assert issued.token in email.text_body
        # Fix round N3/Q-149: an open (not yet closed) request's regenerated link follows
        # normal access rather than the rules-module 14-day lifetime, so the email must not
        # claim a fixed day count it doesn't have.
        assert "stays open" in email.text_body
        assert "no longer works" in email.text_body


class TestMorePhotosEmail:
    def test_reopened_batch_emails_the_leaders_reason(self, requester_ctx, director_ctx):
        request = _submit(requester_ctx)
        services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)
        batch = reopen_batch(director_ctx, request_id=request.id, reason="one more of the roof")

        event = _event(
            "RequestMediaBatchOpened",
            aggregate_type="media_batch",
            aggregate_id=batch.id,
            payload={"request_id": str(request.id), "batch_id": str(batch.id)},
        )
        email = _build_more_photos_email(event)
        assert email is not None
        assert "one more of the roof" in email.text_body
        assert "/r/" in email.text_body


class TestClosedEmail:
    def test_withdrew_sends_a_kind_note(self, requester_ctx, director_ctx):
        request = _submit(requester_ctx)
        cancel_request(
            director_ctx, request_id=request.id, reason_code="requester_withdrew", note=""
        )
        event = _event(
            "RequestCancelled",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "reason_code": "requester_withdrew"},
        )
        email = _build_closed_email(event)
        assert email is not None
        assert "welcome to ask again" in email.text_body

    def test_duplicate_submission_names_the_church_phone(self, requester_ctx, director_ctx):
        request = _submit(requester_ctx)
        cancel_request(
            director_ctx, request_id=request.id, reason_code="duplicate_submission", note=""
        )
        event = _event(
            "RequestCancelled",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "reason_code": "duplicate_submission"},
        )
        email = _build_closed_email(event)
        assert email is not None
        assert "still open" in email.text_body

    def test_spam_sends_nothing(self, requester_ctx, director_ctx):
        request = _submit(requester_ctx)
        cancel_request(director_ctx, request_id=request.id, reason_code="spam", note="")
        event = _event(
            "RequestCancelled",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "reason_code": "spam"},
        )
        assert _build_closed_email(event) is None

    def test_couldnt_reach_them_sends_nothing(self, requester_ctx, director_ctx):
        no_email = no_email_payload(full_name=DISTINCTIVE_NAME)
        request = submit_request(
            requester_ctx, draft_id=uuid.uuid4(), verification_id=None, payload=no_email
        )
        cancel_request(
            director_ctx, request_id=request.id, reason_code="couldnt_reach_them", note=""
        )
        event = _event(
            "RequestCancelled",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "reason_code": "couldnt_reach_them"},
        )
        assert _build_closed_email(event) is None


class TestPIIFreeSubjects:
    """Every requester email builder: subjects never carry the distinctive name/street/phone
    (§68). The address itself is expected in `.to`, never in `.subject`."""

    def _all_events(self, request, requester, batch, link):
        return [
            _event(
                "RequestSubmitted",
                aggregate_type="request",
                aggregate_id=request.id,
                payload={"request_id": str(request.id), "source": "public_form", "urgent": False},
            ),
            _event(
                "RequesterAccessLinkIssued",
                aggregate_type="request",
                aggregate_id=request.id,
                payload={
                    "request_id": str(request.id),
                    "link_id": str(link.link.id),
                    "kind": "regenerated",
                },
            ),
            _event(
                "RequestMediaBatchOpened",
                aggregate_type="media_batch",
                aggregate_id=batch.id,
                payload={"request_id": str(request.id), "batch_id": str(batch.id)},
            ),
        ]

    def test_no_pii_in_any_requester_email_subject(self, requester_ctx, director_ctx):
        request = _submit(requester_ctx)
        services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)
        link = services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_REGENERATED)
        batch = reopen_batch(director_ctx, request_id=request.id, reason="more of the roof")
        requester = Requester.objects.get(request=request)

        builders = [
            _build_request_received_email,
            _build_new_link_email,
            _build_more_photos_email,
        ]
        events = self._all_events(request, requester, batch, link)
        for builder, event in zip(builders, events, strict=True):
            email = builder(event)
            assert email is not None
            for forbidden in (DISTINCTIVE_NAME, DISTINCTIVE_STREET, DISTINCTIVE_PHONE):
                assert forbidden not in email.subject
