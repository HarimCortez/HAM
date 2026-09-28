"""FIX-F2 item 2 (UX M6): the R8 code screen's wording fits the purpose -- intake ("Last
step ... to send your request") vs. link regeneration ("Enter the code to open your request
page"), no "your answers are saved" outside intake. New file per wave brief.
"""

from __future__ import annotations

import uuid

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from ham.jobs import run_due_jobs_now
from ham.requester_portal.models import RequesterAccessLink
from tests.web.test_requester_portal_screens import _fill_wizard

pytestmark = pytest.mark.django_db(transaction=True)


class TestIntakeWording:
    def test_r8_shows_intake_wording_and_last_step_eyebrow(self, client: Client):
        _fill_wizard(client)
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Last step" in content
        assert "Your answers are saved" in content
        assert "to send your request" in content.lower()


class TestLinkRegenerationWording:
    def test_r8_for_a_new_link_never_says_answers_are_saved_or_last_step(
        self, client: Client, real_portal_lookups
    ):
        from ham.authz.context import RequesterContext
        from ham.requester_portal import services
        from ham.requests.certifications import required_statements
        from ham.requests.services import SubmittedRequestPayload, submit_request
        from ham.requests.states import VerificationMethod

        payload = SubmittedRequestPayload(
            full_name="Regen Wording Test",
            phone="+13055550198",
            email="regen-wording@example.org",
            line1="1 Test St",
            city="Miami",
            state="FL",
            postal_code="33101",
            property_type="house",
            relationship_to_property="owner",
            need_category="plumbing_or_water",
            preferred_contact_method="email",
            attested_statements=required_statements("owner"),
            verification_method=VerificationMethod.EMAIL_CODE,
            verified_value="regen-wording@example.org",
        )
        request = submit_request(
            RequesterContext(request_id=None),
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=payload,
        )
        # Drains the duplicate-check job `submit_request` deferred, so it doesn't leak into a
        # later test's `run_due_jobs_now()` call.
        run_due_jobs_now()
        issued = services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)

        mail.outbox.clear()
        resp = client.post(
            reverse("web:request_help_link_expired_send", kwargs={"token": issued.token}),
            data={},
            follow=True,
        )
        # An old link past its own validity window is enough to reach the "send a code"
        # button; the assertion here is about R8's wording, so it's fine either way whether
        # this exact link was still "current" -- what matters is the resulting R8 render.
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Last step" not in content
        assert "Your answers are saved" not in content
        normalized = " ".join(content.lower().split())
        assert "open your request page" in normalized
        assert "confirm your request" not in normalized

        run_due_jobs_now()
        assert len(mail.outbox) == 1
        # Item 2 + Minor: the code email itself is purpose-aware too, never "Confirm your
        # request"/"Your answers are saved" for a link-regeneration send.
        sent = mail.outbox[0]
        assert "confirm your request" not in sent.subject.lower()
        assert "your answers are saved" not in sent.body.lower()
