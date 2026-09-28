"""Q-127 retention sweep (intake.md D4): 7 years after close, erase requester PII; a spam
close is erased entirely after 90 days.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from ham.audit.models import AuditEvent
from ham.platform.clock import now as clock_now
from ham.requests.jobs import run_retention_sweep_now
from ham.requests.models import AssistanceRequest, Property, Requester
from ham.requests.services import cancel_request, submit_request

from .conftest import make_payload

pytestmark = pytest.mark.django_db


def _closed(requester_ctx, director_ctx, *, reason: str, **payload_overrides):
    req = submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**payload_overrides),
    )
    cancel_request(director_ctx, request_id=req.id, reason_code=reason)
    return req


class TestRetentionSweep:
    def test_pii_erased_seven_years_after_close(self, requester_ctx, director_ctx):
        req = _closed(
            requester_ctx,
            director_ctx,
            reason="requester_withdrew",
            full_name="Old Record",
            email="old@example.org",
        )
        AssistanceRequest.objects.filter(id=req.id).update(
            closed_at=clock_now() - dt.timedelta(days=366 * 8)
        )
        run_retention_sweep_now()

        requester = Requester.objects.get(request_id=req.id)
        property_ = Property.objects.get(request_id=req.id)
        assert requester.anonymized_at is not None
        assert requester.full_name == ""
        assert requester.email is None
        assert requester.email_key is None
        assert property_.line1 == ""
        assert property_.address_key is None
        # request itself still exists (ZIP/category/outcome kept for reporting).
        assert AssistanceRequest.objects.filter(id=req.id).exists()
        assert AuditEvent.objects.filter(
            target_id=str(req.id), action="request.pii_purged"
        ).exists()

    def test_not_yet_due_is_left_alone(self, requester_ctx, director_ctx):
        req = _closed(
            requester_ctx,
            director_ctx,
            reason="requester_withdrew",
            full_name="Recent Record",
            email="recent@example.org",
        )
        run_retention_sweep_now()
        requester = Requester.objects.get(request_id=req.id)
        assert requester.anonymized_at is None
        assert requester.full_name == "Recent Record"

    def test_spam_request_erased_entirely_after_90_days(self, requester_ctx, director_ctx):
        req = _closed(
            requester_ctx,
            director_ctx,
            reason="spam",
            full_name="Spammer",
            email="spammer@example.org",
        )
        AssistanceRequest.objects.filter(id=req.id).update(
            closed_at=clock_now() - dt.timedelta(days=91)
        )
        run_retention_sweep_now()
        assert not AssistanceRequest.objects.filter(id=req.id).exists()
        assert AuditEvent.objects.filter(target_id=str(req.id), action="request.purged").exists()

    def test_spam_not_yet_due_is_kept(self, requester_ctx, director_ctx):
        req = _closed(
            requester_ctx,
            director_ctx,
            reason="spam",
            full_name="Spammer Two",
            email="spammer2@example.org",
        )
        AssistanceRequest.objects.filter(id=req.id).update(
            closed_at=clock_now() - dt.timedelta(days=10)
        )
        run_retention_sweep_now()
        assert AssistanceRequest.objects.filter(id=req.id).exists()

    def test_open_requests_are_never_touched(self, requester_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        run_retention_sweep_now()
        requester = Requester.objects.get(request_id=req.id)
        assert requester.anonymized_at is None
