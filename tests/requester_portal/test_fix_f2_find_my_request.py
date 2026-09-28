"""FIX-F2 item 3 (UX M7): "Check on your request" (R11b) sends exactly one E4 "here's the
link" email per matching request -- never the code wording, never a second E3 "new link"
email.

FIX-G NM1/PRD NEW-2 updated this flow further: the E4 email is now a one-time verification
link (not a live access link) -- see `tests/requester_portal/test_fix_g_nm1_find_verification.
py` for the click-through/issuance regression tests. This file keeps the "exactly one email,
right wording" checks.
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


class TestFindMyRequestSendsE4VerificationLink:
    def test_sends_one_verification_link_only_email_no_code_no_live_link_yet(
        self, real_portal_lookups
    ):
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

        # FIX-G NM1: a `PURPOSE_FIND` verification challenge now exists (this is a one-time
        # verification link, not the code-entry flow -- R11b still never asks anyone to type
        # anything), but no live access link is issued -- and nothing is revoked -- until that
        # link is clicked and confirmed.
        assert RequesterVerificationChallenge.objects.filter(
            request_id=request.id, purpose=RequesterVerificationChallenge.PURPOSE_FIND
        ).exists()
        assert not RequesterAccessLink.objects.filter(
            request_id=request.id, revoked_at__isnull=True
        ).exists()

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
