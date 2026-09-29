"""FIX-3A: the 30-minute undo window holds for EVERYONE, not just the decider (security
M1-M3, PRD guardian M6, Q-176/Q-181). One predicate (`ham.requests.queries.decision_undo_open`)
gates every action listed in the coordinator's brief.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from ham.platform.clock import FixedClock, set_clock
from ham.requests.models import RequestQuestion
from ham.requests.queries import decision_undo_open
from ham.requests.services_decisions import (
    approve_request,
    record_decision_phoned,
    record_reconsideration_by_phone,
    reject_request,
    request_reconsideration,
    review_urgency,
    run_held_decision_effects,
    undo_decision,
)
from ham.requests.services_questions import ask_question
from ham.requests.states import RequestStatus, UrgencyStatus

from .test_s32_decisions import _awaiting, _no_email_awaiting, _urgent_awaiting

pytestmark = pytest.mark.django_db


def _past_window(approval) -> None:
    set_clock(FixedClock(approval.effective_at + timedelta(seconds=1)))


class TestDecisionUndoOpenPredicate:
    def test_true_while_the_latest_approval_is_undoable_false_after(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        assert decision_undo_open(req.id) is True
        _past_window(approval)
        assert decision_undo_open(req.id) is False

    def test_true_while_a_standalone_urgency_review_is_undoable(
        self, requester_ctx, system_ctx, pastor_ctx, board_rep_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(board_rep_ctx, request_id=req.id, route="board")
        set_clock(FixedClock(approval.effective_at))
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        assert decision_undo_open(req.id) is True


class TestRequestReconsiderationRefusedDuringWindow:
    """Security M1: `request_reconsideration`/`record_reconsideration_by_phone` didn't pass
    `decision_undo_open` at all -- both were reachable the instant a decline was recorded."""

    def _rejected(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        req.refresh_from_db()
        return req, approval

    def test_requester_reconsideration_refused_during_window_then_allowed(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        from ham.authz.context import RequesterContext

        req, approval = self._rejected(requester_ctx, system_ctx, pastor_ctx)
        with pytest.raises(ValueError, match="decision_undo_window_open"):
            request_reconsideration(RequesterContext(request_id=req.id), note="please")
        _past_window(approval)
        request_reconsideration(RequesterContext(request_id=req.id), note="please")
        req.refresh_from_db()
        assert req.status == RequestStatus.RECONSIDERATION_PENDING.value

    def test_phone_reconsideration_refused_during_window_then_allowed(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req, approval = self._rejected(requester_ctx, system_ctx, pastor_ctx)
        with pytest.raises(ValueError, match="decision_undo_window_open"):
            record_reconsideration_by_phone(director_ctx, request_id=req.id, note="called")
        _past_window(approval)
        record_reconsideration_by_phone(director_ctx, request_id=req.id, note="called")
        req.refresh_from_db()
        assert req.status == RequestStatus.RECONSIDERATION_PENDING.value


class TestReviewUrgencyRefusedDuringWindow:
    """Security M2: `review_urgency` must refuse while the live approval it would certify/
    decline is still undoable."""

    def test_certify_refused_during_the_boards_own_undo_window_then_allowed(
        self, requester_ctx, system_ctx, pastor_ctx, board_rep_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(board_rep_ctx, request_id=req.id, route="board")
        with pytest.raises(ValueError, match="decision_undo_window_open"):
            review_urgency(pastor_ctx, request_id=req.id, certify=True)
        _past_window(approval)
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        req.refresh_from_db()
        assert req.urgency_status == UrgencyStatus.CERTIFIED.value


class TestRecordDecisionPhonedRefusedDuringWindow:
    """Security M3 / UX B2: the phone follow-up must wait for `effective_at`."""

    def test_refused_during_window_then_allowed(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _no_email_awaiting(requester_ctx, system_ctx, director_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        with pytest.raises(ValueError, match="can still be undone"):
            record_decision_phoned(director_ctx, request_id=req.id)
        _past_window(approval)
        record_decision_phoned(director_ctx, request_id=req.id)
        approval.refresh_from_db()
        assert approval.requester_phoned_at is not None

    def test_refused_for_an_email_requester_regardless_of_window(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        _past_window(approval)
        with pytest.raises(ValueError, match="has email"):
            record_decision_phoned(director_ctx, request_id=req.id)


class TestAskQuestionRefusedDuringWindow:
    """Security L9: a question asked while the decision is pending would be auto-withdrawn
    moments later when the held effects run."""

    def test_refused_while_pending_then_allowed(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        with pytest.raises(ValueError, match="can still be undone"):
            ask_question(director_ctx, request_id=req.id, question="What time works?")
        _past_window(approval)
        ask_question(director_ctx, request_id=req.id, question="What time works?")
        assert RequestQuestion.objects.filter(request_id=req.id).exists()


class TestHeldEffectsEarlyRunReDefers:
    """Security L1: a job invocation before `effective_at` must re-defer, never release the
    held effects early, and undo must be refused once `effects_ran_at` is set."""

    def test_run_before_effective_at_redefers_not_releases(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        from ham.outbox.models import OutboxEvent

        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        # Called immediately -- well before `effective_at` -- simulating a misfired early job.
        run_held_decision_effects(approval.id)
        approval.refresh_from_db()
        assert approval.effects_ran_at is None
        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()
        # Once the window has genuinely passed, it releases exactly once.
        set_clock(FixedClock(approval.effective_at))
        run_held_decision_effects(approval.id)
        approval.refresh_from_db()
        assert approval.effects_ran_at is not None
        assert OutboxEvent.objects.filter(event_type="RequestApproved").count() == 1

    def test_undo_refused_once_effects_have_run(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        set_clock(FixedClock(approval.effective_at))
        run_held_decision_effects(approval.id)
        # A retried/duplicate job run somehow reaching `undo_decision` afterwards refuses,
        # rather than reopening an already-effective decision.
        with pytest.raises(ValueError):
            undo_decision(pastor_ctx, approval_id=approval.id)
