"""S3.0: the two step-2 bugs the architect found (approvals.md §2.1 "Fix a constraint bug" /
"Fix a service bug"). Each test is written to demonstrate the bug: it documents the exact
input that the *old* code accepted/answered wrongly, and asserts the fixed behavior.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from ham.requests.models import AssistanceRequest
from ham.requests.services import is_request_open, submit_request
from ham.requests.states import RequestStatus

from .conftest import make_payload

pytestmark = pytest.mark.django_db


def _make_request(requester_ctx) -> AssistanceRequest:
    return submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(),
    )


class TestClosedAtConstraintIsMeaningful:
    """The old `req_closed_at_when_terminal` CHECK --
    `closed_at IS NULL OR status <> CANCELLED OR closed_at IS NOT NULL` -- is a tautology:
    the first and third arms alone already cover every possible row (`closed_at` is always
    either null or not null), so the middle arm never mattered and nothing was ever actually
    rejected by it. Both cases below would have been silently accepted by the old constraint.
    """

    def test_cancelled_without_closed_at_is_rejected(self, requester_ctx):
        req = _make_request(requester_ctx)
        req.status = RequestStatus.CANCELLED.value
        req.closed_at = None
        with pytest.raises(IntegrityError), transaction.atomic():
            req.save(update_fields=["status", "closed_at"])

    def test_open_status_with_closed_at_set_is_rejected(self, requester_ctx):
        req = _make_request(requester_ctx)
        req.status = RequestStatus.AWAITING_APPROVAL.value
        req.closed_at = timezone.now()
        with pytest.raises(IntegrityError), transaction.atomic():
            req.save(update_fields=["status", "closed_at"])

    def test_final_rejected_with_closed_at_set_is_allowed(self, requester_ctx):
        # REJECTED is the one status allowed either way (Q-116: still-reconsiderable vs.
        # final) -- the fixed constraint must not over-correct into refusing this.
        req = _make_request(requester_ctx)
        req.status = RequestStatus.REJECTED.value
        req.closed_at = timezone.now()
        req.save(update_fields=["status", "closed_at"])
        req.refresh_from_db()
        assert req.closed_at is not None

    def test_open_rejected_without_closed_at_is_allowed(self, requester_ctx):
        req = _make_request(requester_ctx)
        req.status = RequestStatus.REJECTED.value
        req.closed_at = None
        req.save(update_fields=["status", "closed_at"])
        req.refresh_from_db()
        assert req.closed_at is None


class TestIsRequestOpenUsesClosedAt:
    """The old `is_request_open` used `not is_terminal(status)`, and `TERMINAL_STATUSES` only
    ever named `CANCELLED` -- so a *final* REJECTED request (Q-116: `closed_at` set once the
    reconsideration window passed with no reconsideration filed) read as "open", even though
    it can never again accept requester media."""

    def test_final_rejection_is_not_open(self, requester_ctx):
        req = _make_request(requester_ctx)
        AssistanceRequest.objects.filter(pk=req.pk).update(
            status=RequestStatus.REJECTED.value, closed_at=timezone.now()
        )
        assert is_request_open(req.id) is False

    def test_reconsiderable_rejection_is_still_open(self, requester_ctx):
        req = _make_request(requester_ctx)
        AssistanceRequest.objects.filter(pk=req.pk).update(
            status=RequestStatus.REJECTED.value, closed_at=None
        )
        assert is_request_open(req.id) is True

    def test_awaiting_approval_is_open(self, requester_ctx):
        req = _make_request(requester_ctx)
        assert is_request_open(req.id) is True

    def test_unknown_request_is_not_open(self):
        assert is_request_open(uuid.uuid4()) is False
