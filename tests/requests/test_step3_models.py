"""S3.0: the three new step-3 models (approvals.md §2.1, §66) -- append-only guards, the
`(request, stage)` and `Reconsideration` uniqueness, and the CHECK constraints. Pure model
tests; the real decision/reconsideration/question write paths are S3.2/S3.3's `services.py`.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from ham.requests.models import (
    AppendOnlyError,
    Approval,
    ApprovalOutcome,
    ApprovalRoute,
    ApprovalStage,
    Reconsideration,
    RejectionReason,
    RequesterChannel,
    RequestQuestion,
)
from ham.requests.services import submit_request

from .conftest import make_payload

pytestmark = pytest.mark.django_db


def _make_request(requester_ctx):
    return submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(),
    )


def _make_approval(request, **overrides):
    now = timezone.now()
    defaults = dict(
        request=request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        route=ApprovalRoute.PASTORAL.value,
        decided_by_user_id=uuid.uuid4(),
        decided_at=now,
        effective_at=now,
    )
    defaults.update(overrides)
    return Approval.objects.create(**defaults)


class TestApprovalAppendOnly:
    def test_ordinary_field_update_is_refused(self, requester_ctx):
        req = _make_request(requester_ctx)
        approval = _make_approval(req)
        approval.outcome = ApprovalOutcome.REJECTED.value
        with pytest.raises(AppendOnlyError):
            approval.save(update_fields=["outcome"])

    def test_delete_is_refused(self, requester_ctx):
        req = _make_request(requester_ctx)
        approval = _make_approval(req)
        with pytest.raises(AppendOnlyError):
            approval.delete()

    def test_requester_phoned_may_be_set_once(self, requester_ctx):
        req = _make_request(requester_ctx)
        approval = _make_approval(req)
        approval.requester_phoned_at = timezone.now()
        approval.requester_phoned_by_user_id = uuid.uuid4()
        approval.save(update_fields=["requester_phoned_at", "requester_phoned_by_user_id"])

        approval.requester_phoned_at = timezone.now()
        with pytest.raises(AppendOnlyError):
            approval.save(update_fields=["requester_phoned_at"])

    def test_undo_fields_may_be_set_once(self, requester_ctx):
        req = _make_request(requester_ctx)
        approval = _make_approval(req)
        approval.undone_at = timezone.now()
        approval.undone_by_user_id = approval.decided_by_user_id
        approval.save(update_fields=["undone_at", "undone_by_user_id"])

        with pytest.raises(AppendOnlyError):
            approval.save(update_fields=["undone_at", "undone_by_user_id"])

    def test_effects_ran_at_may_be_set_once(self, requester_ctx):
        req = _make_request(requester_ctx)
        approval = _make_approval(req)
        approval.effects_ran_at = timezone.now()
        approval.save(update_fields=["effects_ran_at"])
        with pytest.raises(AppendOnlyError):
            approval.save(update_fields=["effects_ran_at"])


class TestApprovalConstraints:
    def test_two_live_decisions_for_one_stage_are_refused(self, requester_ctx):
        req = _make_request(requester_ctx)
        _make_approval(req)
        with pytest.raises(IntegrityError), transaction.atomic():
            _make_approval(req)

    def test_a_second_decision_is_allowed_once_the_first_is_undone(self, requester_ctx):
        # Coordinator correction (Q-156/Q-176): undo's whole point is that a fresh decision
        # for the same stage becomes possible again -- a *plain* `UNIQUE(request, stage)`
        # would keep refusing this forever once the first row had ever been undone. The fix
        # is `approval_unique_live_stage`, a *partial* unique index
        # (`condition=Q(undone_at__isnull=True)`) that only constrains not-yet-undone rows.
        req = _make_request(requester_ctx)
        first = _make_approval(req)
        first.undone_at = timezone.now()
        first.undone_by_user_id = first.decided_by_user_id
        first.save(update_fields=["undone_at", "undone_by_user_id"])

        second = _make_approval(req)  # would have raised IntegrityError before the fix

        assert Approval.objects.filter(request=req, stage=ApprovalStage.INITIAL.value).count() == 2
        assert second.undone_at is None

    def test_second_stage_is_allowed(self, requester_ctx):
        req = _make_request(requester_ctx)
        _make_approval(
            req,
            stage=ApprovalStage.INITIAL.value,
            outcome=ApprovalOutcome.REJECTED.value,
            reason_code=RejectionReason.ANOTHER_REASON.value,
            reason="Sorry",
        )
        _make_approval(req, stage=ApprovalStage.RECONSIDERATION.value, reason="We looked again")
        assert Approval.objects.filter(request=req).count() == 2

    def test_rejected_requires_reason_code_and_message(self, requester_ctx):
        req = _make_request(requester_ctx)
        with pytest.raises(IntegrityError), transaction.atomic():
            _make_approval(req, outcome=ApprovalOutcome.REJECTED.value)

    def test_reconsideration_stage_requires_reason(self, requester_ctx):
        req = _make_request(requester_ctx)
        with pytest.raises(IntegrityError), transaction.atomic():
            _make_approval(req, stage=ApprovalStage.RECONSIDERATION.value)

    def test_urgent_approval_requires_approved_outcome(self, requester_ctx):
        req = _make_request(requester_ctx)
        with pytest.raises(IntegrityError), transaction.atomic():
            _make_approval(
                req,
                outcome=ApprovalOutcome.REJECTED.value,
                urgent_approval=True,
                reason_code=RejectionReason.ANOTHER_REASON.value,
                reason="Sorry",
            )

    def test_board_route_requires_board_decided_on(self, requester_ctx):
        req = _make_request(requester_ctx)
        with pytest.raises(IntegrityError), transaction.atomic():
            _make_approval(req, route=ApprovalRoute.BOARD.value)

    def test_takeover_requires_unavailable_confirmed(self, requester_ctx):
        req = _make_request(requester_ctx)
        # Fix 3A / Q-183: a take-over always needs `took_over_basis`, whether or not it also
        # carries the tick.
        with pytest.raises(IntegrityError), transaction.atomic():
            _make_approval(
                req,
                stage=ApprovalStage.RECONSIDERATION.value,
                reason="We looked again",
                took_over_from_user_id=uuid.uuid4(),
            )
        # With the tick and a matching basis, it's fine.
        _make_approval(
            req,
            stage=ApprovalStage.RECONSIDERATION.value,
            reason="We looked again",
            took_over_from_user_id=uuid.uuid4(),
            unavailable_confirmed=True,
            took_over_basis="unavailable_ticked",
        )

    def test_takeover_role_ended_needs_no_tick(self, requester_ctx):
        """Fix 3A / Q-183: `basis="role_ended"` never carries `unavailable_confirmed`."""
        req = _make_request(requester_ctx)
        _make_approval(
            req,
            stage=ApprovalStage.RECONSIDERATION.value,
            reason="We looked again",
            took_over_from_user_id=uuid.uuid4(),
            took_over_basis="role_ended",
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            _make_approval(
                req,
                stage=ApprovalStage.RECONSIDERATION.value,
                reason="We looked again",
                took_over_from_user_id=uuid.uuid4(),
                unavailable_confirmed=True,
                took_over_basis="role_ended",
            )


class TestReconsiderationImmutable:
    def test_immutable_after_insert(self, requester_ctx):
        req = _make_request(requester_ctx)
        recon = Reconsideration.objects.create(
            request=req,
            requested_at=timezone.now(),
            requested_via=RequesterChannel.SECURE_PAGE.value,
            route=ApprovalRoute.PASTORAL.value,
            original_decider_user_id=uuid.uuid4(),
        )
        recon.requester_note = "changed my mind"
        with pytest.raises(AppendOnlyError):
            recon.save(update_fields=["requester_note"])

    def test_delete_is_refused(self, requester_ctx):
        req = _make_request(requester_ctx)
        recon = Reconsideration.objects.create(
            request=req,
            requested_at=timezone.now(),
            requested_via=RequesterChannel.SECURE_PAGE.value,
            route=ApprovalRoute.PASTORAL.value,
            original_decider_user_id=uuid.uuid4(),
        )
        with pytest.raises(AppendOnlyError):
            recon.delete()

    def test_one_reconsideration_per_request(self, requester_ctx):
        req = _make_request(requester_ctx)
        Reconsideration.objects.create(
            request=req,
            requested_at=timezone.now(),
            requested_via=RequesterChannel.SECURE_PAGE.value,
            route=ApprovalRoute.PASTORAL.value,
            original_decider_user_id=uuid.uuid4(),
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            Reconsideration.objects.create(
                request=req,
                requested_at=timezone.now(),
                requested_via=RequesterChannel.SECURE_PAGE.value,
                route=ApprovalRoute.PASTORAL.value,
                original_decider_user_id=uuid.uuid4(),
            )

    def test_phone_requires_recorder(self, requester_ctx):
        req = _make_request(requester_ctx)
        with pytest.raises(IntegrityError), transaction.atomic():
            Reconsideration.objects.create(
                request=req,
                requested_at=timezone.now(),
                requested_via=RequesterChannel.PHONE.value,
                route=ApprovalRoute.PASTORAL.value,
                original_decider_user_id=uuid.uuid4(),
            )


class TestRequestQuestion:
    def test_question_text_is_never_edited(self, requester_ctx):
        req = _make_request(requester_ctx)
        question = RequestQuestion.objects.create(
            request=req,
            asked_by_user_id=uuid.uuid4(),
            asked_at=timezone.now(),
            question="What color is the roof?",
        )
        question.question = "Edited"
        with pytest.raises(AppendOnlyError):
            question.save(update_fields=["question"])

    def test_answer_written_once(self, requester_ctx):
        req = _make_request(requester_ctx)
        question = RequestQuestion.objects.create(
            request=req,
            asked_by_user_id=uuid.uuid4(),
            asked_at=timezone.now(),
            question="What color is the roof?",
        )
        question.answer = "Blue"
        question.answered_at = timezone.now()
        question.answered_via = RequesterChannel.SECURE_PAGE.value
        question.save(update_fields=["answer", "answered_at", "answered_via"])

        question.answer = "Changed my mind"
        with pytest.raises(AppendOnlyError):
            question.save(update_fields=["answer"])

    def test_answer_requires_answered_at(self, requester_ctx):
        req = _make_request(requester_ctx)
        with pytest.raises(IntegrityError), transaction.atomic():
            RequestQuestion.objects.create(
                request=req,
                asked_by_user_id=uuid.uuid4(),
                asked_at=timezone.now(),
                question="What color is the roof?",
                answer="Blue",
            )

    def test_cannot_be_answered_and_closed(self, requester_ctx):
        req = _make_request(requester_ctx)
        with pytest.raises(IntegrityError), transaction.atomic():
            RequestQuestion.objects.create(
                request=req,
                asked_by_user_id=uuid.uuid4(),
                asked_at=timezone.now(),
                question="What color is the roof?",
                answer="Blue",
                answered_at=timezone.now(),
                closed_at=timezone.now(),
            )

    def test_delete_is_refused(self, requester_ctx):
        req = _make_request(requester_ctx)
        question = RequestQuestion.objects.create(
            request=req,
            asked_by_user_id=uuid.uuid4(),
            asked_at=timezone.now(),
            question="What color is the roof?",
        )
        with pytest.raises(AppendOnlyError):
            question.delete()
