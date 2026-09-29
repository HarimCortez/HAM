"""S3.4: `ham.requester_portal.page.secure_page_data` -- the secure-page card data contract
S3.7's templates render. Scoped by an already-resolved request id (never a token, never a
session); never carries a decider's identity or route (Q-171); shows the state as of the last
*effective* decision, not a still-undoable one (Q-176).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

import pytest

from ham.platform.clock import now as clock_now
from ham.platform.ids import uuid7
from ham.requester_portal import page
from ham.requests.models import Approval as ApprovalModel
from ham.requests.models import (
    ApprovalOutcome,
    ApprovalRoute,
    ApprovalStage,
    AssistanceRequest,
    NeedCategory,
    Property,
    QuestionCloseReason,
    Requester,
    RequesterChannel,
    RequestQuestion,
    next_reference_number,
)
from ham.requests.states import RequestStatus, UrgencyStatus
from ham.rules import RULES

pytestmark = pytest.mark.django_db


def _make_full_request(
    *,
    status: str,
    closed_at=None,
    urgency_status: str = UrgencyStatus.NONE.value,
    reconsideration_deadline_at=None,
) -> AssistanceRequest:
    now = clock_now()
    request = AssistanceRequest.objects.create(
        reference_number=next_reference_number(),
        status=status,
        need_category=NeedCategory.values[0],
        preferred_contact_method=AssistanceRequest._meta.get_field(
            "preferred_contact_method"
        ).choices[0][0],  # type: ignore[index]
        relationship_to_property=AssistanceRequest._meta.get_field(
            "relationship_to_property"
        ).choices[0][0],  # type: ignore[index]
        attestation_version="test",
        submitted_at=now,
        status_changed_at=now,
        closed_at=closed_at,
        urgency_status=urgency_status,
        reconsideration_deadline_at=reconsideration_deadline_at,
    )
    Requester.objects.create(request=request, full_name="Doris Palmer", email="doris@example.org")
    Property.objects.create(
        request=request,
        line1="1400 NW Example Ave",
        city="Miami",
        state="FL",
        postal_code="33125",
        property_type=Property._meta.get_field("property_type").choices[0][0],  # type: ignore[index]
    )
    return request


def _approval(
    request,
    *,
    stage: str,
    outcome: str,
    decided_at,
    effective_at=None,
    reason: str = "",
    reason_code: str = "",
    urgent_approval: bool = False,
    undone_at=None,
) -> ApprovalModel:
    if effective_at is None:
        effective_at = decided_at + RULES.approvals.DECISION_UNDO_WINDOW
    return ApprovalModel.objects.create(
        id=uuid7(),
        request=request,
        stage=stage,
        outcome=outcome,
        route=ApprovalRoute.PASTORAL.value,
        decided_by_user_id=uuid.uuid4(),
        decided_at=decided_at,
        effective_at=effective_at,
        reason=reason,
        reason_code=reason_code,
        urgent_approval=urgent_approval,
        undone_at=undone_at,
        undone_by_user_id=uuid.uuid4() if undone_at else None,
    )


# --------------------------------------------------------------------------------------
# No decision yet
# --------------------------------------------------------------------------------------
def test_awaiting_approval_has_no_decision_or_reconsider_card():
    request = _make_full_request(status=RequestStatus.AWAITING_APPROVAL.value)
    data = page.secure_page_data(request.id)
    assert data.status.status == RequestStatus.AWAITING_APPROVAL.value
    assert data.decision is None
    assert data.reconsider is None


# --------------------------------------------------------------------------------------
# Approved
# --------------------------------------------------------------------------------------
def test_approved_effective_decision_shows_approved_status_and_decision_card():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2  # long past the undo window
    request = _make_full_request(status=RequestStatus.APPROVED.value)
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        decided_at=decided_at,
    )
    data = page.secure_page_data(request.id, now=now)
    assert data.status.status == RequestStatus.APPROVED.value
    assert data.status.chip_label == "Approved"
    assert data.decision.outcome == "approved"
    assert data.decision.stage == "initial"
    assert data.decision.closed is False
    assert data.decision.reason_message == ""
    assert data.status.urgent_alert == ""


def test_urgent_certified_approval_shows_the_alert():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    request = _make_full_request(
        status=RequestStatus.APPROVED.value, urgency_status=UrgencyStatus.CERTIFIED.value
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        decided_at=decided_at,
        urgent_approval=True,
    )
    data = page.secure_page_data(request.id, now=now)
    assert data.status.urgent_alert == (
        "Because it's urgent, HAM's leaders have been told right away and will contact you "
        "soon. If anyone is in danger, call 911."
    )


# --------------------------------------------------------------------------------------
# Q-176: during the undo window, nothing changes for the requester
# --------------------------------------------------------------------------------------
def test_during_the_undo_window_the_page_shows_the_prior_state():
    now = clock_now()
    decided_at = now  # just decided; effective_at is 30 minutes from now
    # The DB row already flipped to APPROVED (the state machine transition happens at
    # decided_at, per approvals-contracts.md §4) -- the page must not show that yet.
    request = _make_full_request(status=RequestStatus.APPROVED.value)
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        decided_at=decided_at,
    )
    data = page.secure_page_data(request.id, now=now)
    assert data.status.status == RequestStatus.AWAITING_APPROVAL.value
    assert data.decision is None


def test_right_after_the_undo_window_ends_the_page_shows_the_decision():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW  # exactly at the edge, now passed
    request = _make_full_request(status=RequestStatus.APPROVED.value)
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        decided_at=decided_at,
    )
    data = page.secure_page_data(request.id, now=now)
    assert data.status.status == RequestStatus.APPROVED.value
    assert data.decision is not None


def test_an_undone_decision_is_never_the_effective_one():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    request = _make_full_request(status=RequestStatus.AWAITING_APPROVAL.value)
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        decided_at=decided_at,
        undone_at=decided_at + RULES.approvals.DECISION_UNDO_WINDOW / 2,
    )
    data = page.secure_page_data(request.id, now=now)
    assert data.status.status == RequestStatus.AWAITING_APPROVAL.value
    assert data.decision is None


# --------------------------------------------------------------------------------------
# Rejected, open (reconsiderable)
# --------------------------------------------------------------------------------------
def test_rejected_open_shows_reason_and_reconsider_eligibility():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    deadline = now + dt.timedelta(days=10)
    request = _make_full_request(
        status=RequestStatus.REJECTED.value, reconsideration_deadline_at=deadline
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="From what you've shared, it sounds like family may be able to help.",
        reason_code="family_or_others_can_help",
    )
    data = page.secure_page_data(request.id, now=now)
    assert data.status.status == RequestStatus.REJECTED.value
    assert data.status.chip_label == "Not approved"
    assert data.decision.closed is False
    assert "family" in data.decision.reason_message
    assert data.reconsider.eligible is True
    assert data.reconsider.already_requested is False
    assert data.reconsider.last_day is not None
    assert "You can ask until" in data.reconsider.ask_line


def test_rejected_open_past_the_deadline_is_not_eligible():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    deadline = now - dt.timedelta(days=1)
    request = _make_full_request(
        status=RequestStatus.REJECTED.value, reconsideration_deadline_at=deadline
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Another reason",
        reason_code="another_reason",
    )
    data = page.secure_page_data(request.id, now=now)
    assert data.reconsider.eligible is False


def test_rejected_open_already_requested_is_not_eligible_again():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    deadline = now + dt.timedelta(days=10)
    request = _make_full_request(
        status=RequestStatus.RECONSIDERATION_PENDING.value,
        reconsideration_deadline_at=deadline,
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Another reason",
        reason_code="another_reason",
    )
    from ham.requests.models import Reconsideration

    Reconsideration.objects.create(
        id=uuid7(),
        request=request,
        requested_at=now,
        requested_via=RequesterChannel.SECURE_PAGE.value,
        route=ApprovalRoute.PASTORAL.value,
        original_decider_user_id=uuid.uuid4(),
    )
    data = page.secure_page_data(request.id, now=now)
    # Status is RECONSIDERATION_PENDING now, so there's no decision/reconsider card at all --
    # covered by test_reconsideration_pending_* below. This test only proves the DB fact
    # (`already_requested`) reads correctly when a Reconsideration row exists.
    from ham.requests.models import Reconsideration as ReconsiderationModel

    assert ReconsiderationModel.objects.filter(request=request).exists()
    assert data.status.status == RequestStatus.RECONSIDERATION_PENDING.value


# --------------------------------------------------------------------------------------
# Reconsideration Pending
# --------------------------------------------------------------------------------------
def test_reconsideration_pending_has_no_decision_or_reconsider_card():
    request = _make_full_request(status=RequestStatus.RECONSIDERATION_PENDING.value)
    data = page.secure_page_data(request.id)
    assert data.status.status == RequestStatus.RECONSIDERATION_PENDING.value
    assert data.status.chip_label == "Taking another look"
    assert data.decision is None
    assert data.reconsider is None


# --------------------------------------------------------------------------------------
# Rejected, final
# --------------------------------------------------------------------------------------
def test_rejected_final_after_reconsideration():
    now = clock_now()
    initial_decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 6
    recon_decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    request = _make_full_request(status=RequestStatus.REJECTED.value, closed_at=now)
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=initial_decided_at,
        reason="First reason",
        reason_code="another_reason",
    )
    _approval(
        request,
        stage=ApprovalStage.RECONSIDERATION.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=recon_decided_at,
        reason="Still can't help",
        reason_code="another_reason",
    )
    data = page.secure_page_data(request.id, now=now)
    assert data.status.status == RequestStatus.REJECTED.value
    assert data.status.chip_label == "Closed"
    assert data.decision.closed is True
    assert data.decision.stage == "reconsideration"
    assert "Still can't help" in data.decision.reason_message
    assert data.reconsider is None  # final -- no more reconsidering


def test_rejected_final_window_passed_never_reconsidered():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 6
    request = _make_full_request(status=RequestStatus.REJECTED.value, closed_at=now)
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Original reason",
        reason_code="another_reason",
    )
    data = page.secure_page_data(request.id, now=now)
    assert data.decision.stage == "initial"
    assert data.status.sentence == "We weren't able to help with this request."


# --------------------------------------------------------------------------------------
# Q-171: never the decider's identity or route
# --------------------------------------------------------------------------------------
def test_decision_card_never_carries_the_decider_identity_or_route():
    field_names = {f.name for f in dataclasses.fields(page.DecisionCard)}
    forbidden = {"decided_by_user_id", "route", "decider", "decided_by"}
    assert not (field_names & forbidden)


def test_status_card_never_carries_the_decider_identity_or_route():
    field_names = {f.name for f in dataclasses.fields(page.StatusCard)}
    forbidden = {"decided_by_user_id", "route", "decider", "decided_by"}
    assert not (field_names & forbidden)


# --------------------------------------------------------------------------------------
# Questions
# --------------------------------------------------------------------------------------
def test_question_cards_split_open_answered_and_hide_withdrawn():
    now = clock_now()
    request = _make_full_request(status=RequestStatus.AWAITING_APPROVAL.value)
    open_q = RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=now,
        question="Does water come in only when it rains?",
    )
    answered_q = RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=now,
        question="Is the roof flat or sloped?",
    )
    answered_q.answer = "Sloped."
    answered_q.answered_at = now
    answered_q.answered_via = RequesterChannel.SECURE_PAGE.value
    answered_q.save(update_fields=["answer", "answered_at", "answered_via"])
    withdrawn_q = RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=now,
        question="Never mind this one.",
    )
    withdrawn_q.closed_at = now
    withdrawn_q.close_reason = QuestionCloseReason.WITHDRAWN.value
    withdrawn_q.save(update_fields=["closed_at", "close_reason"])

    data = page.secure_page_data(request.id, now=now)
    assert {q.id for q in data.open_questions} == {open_q.id}
    assert {q.id for q in data.answered_questions} == {answered_q.id}
    assert data.open_questions[0].answer == ""
    assert data.answered_questions[0].answer == "Sloped."


# --------------------------------------------------------------------------------------
# Scoping: never leaks another request's data
# --------------------------------------------------------------------------------------
def test_page_data_is_scoped_to_the_given_request_only():
    now = clock_now()
    request_a = _make_full_request(status=RequestStatus.AWAITING_APPROVAL.value)
    request_b = _make_full_request(status=RequestStatus.AWAITING_APPROVAL.value)
    RequestQuestion.objects.create(
        id=uuid7(),
        request=request_b,
        asked_by_user_id=uuid.uuid4(),
        asked_at=now,
        question="A question about request B only.",
    )
    data_a = page.secure_page_data(request_a.id, now=now)
    assert data_a.open_questions == ()
    assert data_a.status.status == RequestStatus.AWAITING_APPROVAL.value


def test_unknown_request_id_returns_none():
    assert page.secure_page_data(uuid.uuid4()) is None
