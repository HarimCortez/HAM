"""FIX-G NM1/PRD NEW-2 (Medium/Major, §7.3/§58/§70.3): an unauthenticated "Check on your
request" (R11b) POST must not, by itself, issue a fresh live access link and revoke the
requester's old one. It now sends a one-time verification link first (reusing the link-
regeneration click-through machinery at `/request-help/new-link/<token>`); the actual link is
only issued -- and the old one only revoked -- once that link is clicked and confirmed.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from ham.audit.models import AuditEvent
from ham.authz.context import RequesterContext
from ham.jobs import run_due_jobs_now
from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal import services, verification
from ham.requester_portal.models import RequesterAccessLink, RequesterVerificationChallenge
from ham.requests.certifications import required_statements
from ham.requests.models import RequestContactVerification
from ham.requests.services import SubmittedRequestPayload, submit_request
from ham.requests.states import VerificationMethod
from ham.rules import RULES

pytestmark = pytest.mark.django_db(transaction=True)

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)

_NEW_LINK_RE = re.compile(r"/request-help/new-link/([^\s]+)")


def _submit_request(email: str):
    payload = SubmittedRequestPayload(
        full_name="Find Verification Test",
        phone="+13055550177",
        email=email,
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
        verified_value=email,
    )
    request = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=payload,
    )
    run_due_jobs_now()  # drains the RequestSubmitted email + duplicate-check job
    return request


def _extract_new_link_token(body: str) -> str:
    match = _NEW_LINK_RE.search(body)
    assert match is not None, body
    return match.group(1)


class TestOldLinkSurvivesUntilTheEmailedLinkIsClicked:
    def test_find_alone_never_issues_or_revokes_a_link(self, real_portal_lookups):
        request = _submit_request("still-works@example.org")
        old = services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)

        mail.outbox.clear()
        result = services.find_my_request(email="still-works@example.org")
        assert result.status == "sent"
        run_due_jobs_now()
        assert len(mail.outbox) == 1

        # The old link is completely untouched -- `find_my_request` never issued or revoked
        # anything by itself.
        old.link.refresh_from_db()
        assert old.link.revoked_at is None
        assert services.resolve_token(old.token) is not None
        assert (
            not RequesterAccessLink.objects.filter(request_id=request.id, revoked_at__isnull=True)
            .exclude(pk=old.link.id)
            .exists()
        )

    def test_clicking_and_confirming_the_link_issues_a_new_one_and_revokes_the_old(
        self, real_portal_lookups
    ):
        request = _submit_request("click-through@example.org")
        old = services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)

        mail.outbox.clear()
        services.find_my_request(email="click-through@example.org")
        run_due_jobs_now()
        assert len(mail.outbox) == 1
        token = _extract_new_link_token(str(mail.outbox[0].body))

        client = Client()
        consume = client.post(reverse("web:request_help_new_link", kwargs={"token": token}))
        assert consume.status_code == 302

        old.link.refresh_from_db()
        assert old.link.revoked_at is not None
        assert old.link.revoke_reason == RequesterAccessLink.REVOKE_SUPERSEDED
        assert services.resolve_token(old.token) is None

        live = RequesterAccessLink.objects.get(request_id=request.id, revoked_at__isnull=True)
        assert live.id != old.link.id

        # Audited exactly like R11a's own click-through re-verification: verification_method
        # + challenge id recorded, and a `RequestContactVerification` row written.
        event = AuditEvent.objects.get(
            action="requester_link.regenerated", target_id=str(request.id)
        )
        assert event.context["verification_method"] == "email_link"
        assert RequestContactVerification.objects.filter(
            request_id=request.id, method="email_link"
        ).exists()


class TestFindVerificationHasItsOwnRateLimits:
    def test_per_request_cooldown(self, real_portal_lookups):
        clock = FixedClock(T0)
        set_clock(clock)
        request = _submit_request("cooldown@example.org")

        mail.outbox.clear()
        first = services.find_my_request(email="cooldown@example.org")
        assert first.status == "sent"
        run_due_jobs_now()
        assert len(mail.outbox) == 1

        # Same request, too soon -- identical outward response (no enumeration), nothing
        # actually sent.
        mail.outbox.clear()
        second = services.find_my_request(email="cooldown@example.org")
        assert second.status == "sent"
        run_due_jobs_now()
        assert len(mail.outbox) == 0

        clock.advance(RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN + dt.timedelta(seconds=1))
        mail.outbox.clear()
        third = services.find_my_request(email="cooldown@example.org")
        assert third.status == "sent"
        run_due_jobs_now()
        assert len(mail.outbox) == 1
        assert (
            RequesterVerificationChallenge.objects.filter(
                request_id=request.id, purpose=RequesterVerificationChallenge.PURPOSE_FIND
            ).count()
            == 2
        )

    def test_per_address_daily_cap(self):
        clock = FixedClock(T0)
        set_clock(clock)
        email = "dailycap@example.org"
        statuses = [
            verification.request_find_verification(request_id=uuid.uuid4(), email=email).status
            for _ in range(RULES.intake.FIND_REQUEST_EMAILS_PER_ADDRESS_PER_DAY + 1)
        ]
        assert statuses[:-1] == ["sent"] * RULES.intake.FIND_REQUEST_EMAILS_PER_ADDRESS_PER_DAY
        assert statuses[-1] == "rate_limited"
