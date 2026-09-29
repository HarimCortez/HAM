"""Coordinator fix round (post S3.2/S3.3 merge): three gaps found in review.

1. Undo must restore urgency too, not just status (Q-176/Q-178).
2. A standalone urgency review (not bundled with an approval) is itself undoable (Q-176).
3. `RequestApproved` must never be double-delivered -- the immediate urgent-approval alert
   is a distinct event, `RequestUrgentApproval`; `RequestApproved` is the held copy only.

Each test in this file is written to fail against the pre-fix code and pass after.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from ham.audit.models import AuditEvent
from ham.authz import roles
from ham.authz.commands import ImpersonationBlocked
from ham.outbox.models import OutboxEvent
from ham.platform.clock import FixedClock, set_clock
from ham.requests.models import ApprovalOutcome
from ham.requests.services import complete_intake_checks, submit_request
from ham.requests.services_decisions import (
    approve_request,
    decide_reconsideration,
    review_urgency,
    undo_decision,
)
from ham.requests.states import RequestStatus, UrgencyStatus
from ham.rules import RULES

from .conftest import actor_ctx, make_payload

pytestmark = pytest.mark.django_db


def _urgent_awaiting(requester_ctx, system_ctx, **overrides):
    overrides.setdefault("urgency_reason", "someone_could_get_hurt")
    req = submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(urgent_requested=True, **overrides),
    )
    complete_intake_checks(system_ctx, request_id=req.id)
    req.refresh_from_db()
    return req


def _awaiting(requester_ctx, system_ctx, **overrides):
    req = submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**overrides),
    )
    complete_intake_checks(system_ctx, request_id=req.id)
    req.refresh_from_db()
    return req


# ------------------------------------------------------------------------------------------
# Gap 1: undo restores urgency bundled with an approval (Q-176/Q-178)
# ------------------------------------------------------------------------------------------
class TestGap1UndoRestoresUrgency:
    def test_undo_after_certify_urgent_restores_urgency(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        assert req.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True
        )
        req.refresh_from_db()
        assert req.urgency_status == UrgencyStatus.CERTIFIED.value

        undo_decision(pastor_ctx, approval_id=approval.id)
        req.refresh_from_db()
        assert req.status == RequestStatus.AWAITING_APPROVAL.value
        assert req.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value
        assert req.urgency_reviewed_at is None
        assert req.urgency_reviewed_by_user_id is None

    def test_undo_after_decline_urgency_restores_urgency(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", decline_urgency=True
        )
        req.refresh_from_db()
        assert req.urgency_status == UrgencyStatus.NOT_CERTIFIED.value

        undo_decision(pastor_ctx, approval_id=approval.id)
        req.refresh_from_db()
        assert req.status == RequestStatus.AWAITING_APPROVAL.value
        assert req.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value


# ------------------------------------------------------------------------------------------
# Gap 2: a standalone urgency review is itself undoable (Q-176)
# ------------------------------------------------------------------------------------------
class TestGap2UrgencyReviewIsUndoable:
    def test_certify_then_undo_within_the_window(self, requester_ctx, system_ctx, pastor_ctx):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        req.refresh_from_db()
        assert req.urgency_status == UrgencyStatus.CERTIFIED.value

        from ham.requests.models import UrgencyReview

        review = UrgencyReview.objects.get(request_id=req.id)
        undo_decision(pastor_ctx, review_id=review.id)
        req.refresh_from_db()
        assert req.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value
        review.refresh_from_db()
        assert review.undone_at is not None
        assert review.undone_by_user_id == pastor_ctx.user_id
        assert AuditEvent.objects.filter(action="request.urgency_review_undone").count() == 1
        assert OutboxEvent.objects.filter(event_type="RequestUrgencyReviewUndone").count() == 1

    def test_decline_then_undo_within_the_window(self, requester_ctx, system_ctx, pastor_ctx):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=False)
        req.refresh_from_db()
        assert req.urgency_status == UrgencyStatus.NOT_CERTIFIED.value

        from ham.requests.models import UrgencyReview

        review = UrgencyReview.objects.get(request_id=req.id)
        undo_decision(pastor_ctx, review_id=review.id)
        req.refresh_from_db()
        assert req.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value

    def test_only_the_same_pastor_may_undo(self, requester_ctx, system_ctx, pastor_ctx):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        from ham.requests.models import UrgencyReview

        review = UrgencyReview.objects.get(request_id=req.id)
        other_pastor = actor_ctx(roles=frozenset({roles.PASTOR}))
        with pytest.raises(ValueError, match="not_the_decider"):
            undo_decision(other_pastor, review_id=review.id)

    def test_blocked_while_impersonating(self, requester_ctx, system_ctx, pastor_ctx):
        import dataclasses

        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        from ham.requests.models import UrgencyReview

        review = UrgencyReview.objects.get(request_id=req.id)
        impersonating = dataclasses.replace(
            pastor_ctx, impersonation_id=uuid.uuid4(), real_user_id=uuid.uuid4()
        )
        with pytest.raises(ImpersonationBlocked):
            undo_decision(impersonating, review_id=review.id)

    def test_undo_after_the_window_is_refused(self, requester_ctx, system_ctx, pastor_ctx):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        from ham.requests.models import UrgencyReview

        review = UrgencyReview.objects.get(request_id=req.id)
        set_clock(
            FixedClock(
                review.decided_at + RULES.approvals.DECISION_UNDO_WINDOW + timedelta(seconds=1)
            )
        )
        with pytest.raises(ValueError, match="undo_window_passed"):
            undo_decision(pastor_ctx, review_id=review.id)

    def test_exactly_one_of_approval_id_or_review_id_is_required(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        with pytest.raises(ValueError):
            undo_decision(pastor_ctx, approval_id=approval.id, review_id=uuid.uuid4())
        with pytest.raises(ValueError):
            undo_decision(pastor_ctx)


# ------------------------------------------------------------------------------------------
# Gap 3: no double delivery of `RequestApproved`
# ------------------------------------------------------------------------------------------
class TestGap3NoDoubleDeliveryOfRequestApproved:
    def test_approving_an_already_certified_request_never_emits_requestapproved_immediately(
        self, requester_ctx, system_ctx, pastor_ctx, board_rep_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        approval = approve_request(board_rep_ctx, request_id=req.id, route="board")

        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()
        urgent = OutboxEvent.objects.get(event_type="RequestUrgentApproval")
        assert urgent.payload == {"request_id": str(req.id), "approval_id": str(approval.id)}

    def test_certify_urgent_bundle_also_emits_the_dedicated_event_not_requestapproved(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True
        )
        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()
        urgent = OutboxEvent.objects.get(event_type="RequestUrgentApproval")
        assert urgent.payload == {"request_id": str(req.id), "approval_id": str(approval.id)}

    def test_reconsider_approve_of_an_already_certified_request_uses_the_dedicated_event(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        from ham.requests.services_decisions import reject_request

        # Reject then reconsider-approve, so we get a stage=reconsideration Approval to check.
        req.refresh_from_db()
        assert req.urgency_status == UrgencyStatus.CERTIFIED.value
        # Certified urgency survives a rejection/reconsideration cycle untouched by the
        # decision machinery, so approving on reconsideration alone tips it urgent again.
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        assert approval.outcome == ApprovalOutcome.REJECTED.value
        from ham.authz.context import RequesterContext
        from ham.requests.services_decisions import request_reconsideration

        request_reconsideration(RequesterContext(request_id=req.id))
        recon_approval = decide_reconsideration(
            pastor_ctx, request_id=req.id, approve=True, reason="Second look, approved"
        )
        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()
        urgent = OutboxEvent.objects.get(event_type="RequestUrgentApproval")
        assert urgent.payload == {
            "request_id": str(req.id),
            "approval_id": str(recon_approval.id),
        }

    def test_requestapproved_is_emitted_exactly_once_by_the_held_effects_job(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        from ham.requests.services_decisions import run_held_decision_effects

        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True
        )
        run_held_decision_effects(approval.id)
        assert OutboxEvent.objects.filter(event_type="RequestApproved").count() == 1
