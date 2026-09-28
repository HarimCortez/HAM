"""FIX-F2 item 3 (UX M7): "Check on your request" (R11b) sends exactly one E4 "here's the
link" email per matching request -- never the code email, never a second E3 "new link" email,
and never creates a `RequesterVerificationChallenge` at all. New file per wave brief.
"""

from __future__ import annotations

import uuid

import pytest
from django.core import mail

from ham.audit.models import AuditEvent
from ham.jobs import run_due_jobs_now
from ham.requester_portal import services
from ham.requester_portal.models import RequesterAccessLink, RequesterVerificationChallenge

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _lookups(real_portal_lookups):
    pass


class TestFindMyRequestSendsE4Directly:
    def test_sends_one_link_only_email_no_code_no_challenge(self, real_portal_lookups):
        from ham.authz.context import RequesterContext
        from ham.requests.certifications import required_statements
        from ham.requests.services import SubmittedRequestPayload, submit_request
        from ham.requests.states import VerificationMethod

        payload = SubmittedRequestPayload(
            full_name="Find My Request Test",
            phone="+13055550177",
            email="find-me@example.org",
            line1="1 Test St",
            city="Miami",
            state="FL",
            postal_code="33101",
            property_type="house",
            relationship_to_property="owner",
            need_category="roof_or_ceiling",
            preferred_contact_method="email",
            attested_statements=required_statements("owner"),
            verification_method=VerificationMethod.EMAIL_CODE,
            verified_value="find-me@example.org",
        )
        request = submit_request(
            RequesterContext(request_id=None),
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=payload,
        )
        # Drains the "request received" email and duplicate-check job `submit_request`
        # itself triggers, so they're not mistaken for `find_my_request`'s own send below
        # (and so the deferred job doesn't leak into a later test).
        run_due_jobs_now()

        mail.outbox.clear()
        result = services.find_my_request(email="find-me@example.org")
        assert result.status == "sent"
        run_due_jobs_now()

        # Exactly one email, never the code wording, never a second "new link" email.
        assert len(mail.outbox) == 1
        sent = mail.outbox[0]
        assert request.display_number in sent.subject
        assert "code" not in sent.body.lower()
        assert "your old link no longer works" not in sent.body.lower()
        assert "open my request page" in sent.body.lower()

        # No verification challenge exists -- R11b never asks anyone to type a code at all.
        assert not RequesterVerificationChallenge.objects.filter(request_id=request.id).exists()

        # A fresh live access link was issued for the request.
        assert RequesterAccessLink.objects.filter(
            request_id=request.id, revoked_at__isnull=True
        ).exists()

        # Its own, dedicated audit action -- not the generic "requester_link.regenerated".
        assert AuditEvent.objects.filter(
            action="requester_link.found", target_id=str(request.id)
        ).exists()
        assert not AuditEvent.objects.filter(
            action="requester_link.regenerated", target_id=str(request.id)
        ).exists()

    def test_unknown_address_sends_nothing(self):
        mail.outbox.clear()
        result = services.find_my_request(email="nobody-at-all@example.org")
        assert result.status == "sent"  # identical response either way (no enumeration)
        run_due_jobs_now()
        assert mail.outbox == []
