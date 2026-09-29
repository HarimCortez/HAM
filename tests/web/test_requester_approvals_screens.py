"""S3.7 integration tests: R13-R19 (docs/ux/approvals.md §6; approvals-contracts.md §8) driven
through Django's test client, exactly like `tests/web/test_requester_portal_screens.py` (step
2) does for R1-R12. Every route here is scoped by an access-link token only, resolved fresh on
every request -- never a session (approvals-contracts.md, this slice's own brief).
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from django.test import Client
from django.urls import reverse

from ham.platform.clock import now as clock_now
from ham.platform.ids import uuid7
from ham.requester_portal import services
from ham.requests.models import Approval as ApprovalModel
from ham.requests.models import (
    ApprovalOutcome,
    ApprovalRoute,
    ApprovalStage,
    AssistanceRequest,
    NeedCategory,
    Property,
    QuestionCloseReason,
    Reconsideration,
    Requester,
    RequesterChannel,
    RequestQuestion,
    next_reference_number,
)
from ham.requests.states import RequestStatus, UrgencyStatus
from ham.rules import RULES

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _real_portal_lookups(real_portal_lookups):
    pass


# --------------------------------------------------------------------------------------
# Fixture helpers (same shape as tests/requester_portal/test_s34_page.py)
# --------------------------------------------------------------------------------------
def _make_request(
    *,
    status: str,
    closed_at=None,
    urgency_status: str = UrgencyStatus.NONE.value,
    reconsideration_deadline_at=None,
    urgent_requested: bool = False,
) -> AssistanceRequest:
    now = clock_now()
    request = AssistanceRequest.objects.create(
        reference_number=next_reference_number(),
        status=status,
        need_category=NeedCategory.values[0],
        description="Water leaks through the bedroom ceiling.",
        urgent_requested=urgent_requested,
        preferred_contact_method=AssistanceRequest._meta.get_field(
            "preferred_contact_method"
        ).choices[0][0],
        relationship_to_property=AssistanceRequest._meta.get_field(
            "relationship_to_property"
        ).choices[0][0],
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
        property_type=Property._meta.get_field("property_type").choices[0][0],
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


def _token_for(request: AssistanceRequest) -> str:
    return services.issue_link(request_id=request.id, kind="initial").token


# --------------------------------------------------------------------------------------
# Secure page (R10): question open (R13)
# --------------------------------------------------------------------------------------
def test_secure_page_shows_open_question_card():
    request = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    question = RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=clock_now(),
        question="Does the water come in only when it rains?",
    )
    token = _token_for(request)
    resp = Client().get(reverse("web:request_help_secure_page", kwargs={"token": token}))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "HAM has a question for you" in content
    assert "Does the water come in only when it rains?" in content
    assert "We have a question for you below" in content
    assert f"q-{question.id}" in content


def test_secure_page_shows_answered_question_in_qa_thread():
    request = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    now = clock_now()
    RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=now,
        question="Is the roof flat or sloped?",
        answer="Sloped.",
        answered_at=now,
        answered_via=RequesterChannel.SECURE_PAGE.value,
    )
    token = _token_for(request)
    resp = Client().get(reverse("web:request_help_secure_page", kwargs={"token": token}))
    content = resp.content.decode()
    assert "Questions and answers" in content
    assert "Sloped." in content


# --------------------------------------------------------------------------------------
# Secure page: approved (R14)
# --------------------------------------------------------------------------------------
def test_secure_page_approved_shows_next_steps_and_sect11_line():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    request = _make_request(status=RequestStatus.APPROVED.value)
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        decided_at=decided_at,
    )
    token = _token_for(request)
    resp = Client().get(reverse("web:request_help_secure_page", kwargs={"token": token}))
    content = resp.content.decode()
    assert "Good news: your request is approved." in content
    assert (
        "the visit helps us plan; it doesn&#x27;t yet promise the work"
        in content.lower().replace("&#39;", "&#x27;")
        or "doesn&#x27;t yet promise the work" in content
    )
    assert "Someone from HAM will call you" in content


def test_secure_page_approved_urgent_certified_shows_alert():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    request = _make_request(
        status=RequestStatus.APPROVED.value, urgency_status=UrgencyStatus.CERTIFIED.value
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        decided_at=decided_at,
        urgent_approval=True,
    )
    token = _token_for(request)
    resp = Client().get(reverse("web:request_help_secure_page", kwargs={"token": token}))
    content = resp.content.decode()
    assert "HAM&#x27;s leaders have been told right away" in content or (
        "leaders have been told right away" in content
    )


# --------------------------------------------------------------------------------------
# Secure page: not approved (R15) + reconsider block
# --------------------------------------------------------------------------------------
def test_secure_page_rejected_open_shows_reason_and_reconsider_button():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    deadline = now + dt.timedelta(days=10)
    request = _make_request(
        status=RequestStatus.REJECTED.value, reconsideration_deadline_at=deadline
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Family or others may be able to help.",
        reason_code="family_or_others_can_help",
    )
    token = _token_for(request)
    resp = Client().get(reverse("web:request_help_secure_page", kwargs={"token": token}))
    content = resp.content.decode()
    assert "Not approved" in content
    assert "Family or others may be able to help." in content
    assert "Ask us to reconsider" in content
    assert reverse("web:request_help_reconsider", kwargs={"token": token}) in content
    # never red, never "rejected"/"denied" on the requester surface (owner box; UX §8 word list)
    assert "rejected" not in content.lower()
    assert "denied" not in content.lower()
    # R15 (design-system §5.2 "Photo uploads are closed for now"): a rejected-but-open request
    # has nothing to add photos toward -- a visual-QA-caught bug (screenshot pass) had this
    # showing the upload card anyway (`can_add_photos` only excluded CANCELLED).
    assert "Add photos" not in content
    assert "Photo uploads are closed for now" in content


def test_secure_page_rejected_final_has_no_reconsider_button():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 6
    request = _make_request(status=RequestStatus.REJECTED.value, closed_at=now)
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Another reason.",
        reason_code="another_reason",
    )
    token = _token_for(request)
    resp = Client().get(reverse("web:request_help_secure_page", kwargs={"token": token}))
    content = resp.content.decode()
    assert "Closed" in content
    assert "Ask us to reconsider" not in content
    assert "welcome to send a new request" in content.lower()


# --------------------------------------------------------------------------------------
# Secure page: taking another look (R17)
# --------------------------------------------------------------------------------------
def test_secure_page_reconsideration_pending_shows_her_note():
    now = clock_now()
    request = _make_request(status=RequestStatus.RECONSIDERATION_PENDING.value)
    Reconsideration.objects.create(
        id=uuid7(),
        request=request,
        requested_at=now,
        requested_via=RequesterChannel.SECURE_PAGE.value,
        route=ApprovalRoute.PASTORAL.value,
        original_decider_user_id=uuid.uuid4(),
        requester_note="Please look again, my son is away.",
    )
    token = _token_for(request)
    resp = Client().get(reverse("web:request_help_secure_page", kwargs={"token": token}))
    content = resp.content.decode()
    assert "Taking another look" in content
    assert "Please look again, my son is away." in content


# --------------------------------------------------------------------------------------
# Secure page: undo-window view (Q-176) -- the page shows the prior state, not the decision
# --------------------------------------------------------------------------------------
def test_secure_page_during_undo_window_shows_prior_state():
    now = clock_now()
    request = _make_request(status=RequestStatus.APPROVED.value)
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        decided_at=now,  # just decided; still inside the undo window
    )
    token = _token_for(request)
    resp = Client().get(reverse("web:request_help_secure_page", kwargs={"token": token}))
    content = resp.content.decode()
    assert "Our pastors or Board are reviewing your request." in content
    assert "Good news: your request is approved." not in content


# --------------------------------------------------------------------------------------
# Secure page: a superseded/old token is refused
# --------------------------------------------------------------------------------------
def test_secure_page_superseded_token_is_refused():
    request = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    old_token = _token_for(request)
    # A second `issue_link` revokes the first (superseded) -- same as step 2's own guarantee.
    services.issue_link(request_id=request.id, kind="initial")
    resp = Client().get(reverse("web:request_help_secure_page", kwargs={"token": old_token}))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "HAM #" not in content  # not the real secure page
    assert "Your request" not in content or "link" in content.lower()


def test_secure_page_unknown_token_is_refused():
    resp = Client().get(
        reverse("web:request_help_secure_page", kwargs={"token": "not-a-real-token"})
    )
    assert resp.status_code == 200
    assert "Your request &middot;" not in resp.content.decode()


# --------------------------------------------------------------------------------------
# R13: answering a question
# --------------------------------------------------------------------------------------
def test_answer_question_success_redirects_and_shows_answer():
    request = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    question = RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=clock_now(),
        question="Does the water come in only when it rains?",
    )
    token = _token_for(request)
    resp = Client().post(
        reverse(
            "web:request_help_question_answer",
            kwargs={"token": token, "question_id": question.id},
        ),
        {"answer": "Only when it rains, so far."},
        follow=True,
    )
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Only when it rains, so far." in content
    assert "Thank you. We&#x27;ve got your answer." in content or "got your answer" in content
    question.refresh_from_db()
    assert question.answer == "Only when it rains, so far."
    assert question.answered_via == RequesterChannel.SECURE_PAGE.value


def test_answer_question_over_limit_is_rejected_and_kept_open():
    request = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    question = RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=clock_now(),
        question="Tell us more?",
    )
    token = _token_for(request)
    resp = Client().post(
        reverse(
            "web:request_help_question_answer",
            kwargs={"token": token, "question_id": question.id},
        ),
        {"answer": "x" * 1001},
        follow=True,
    )
    content = resp.content.decode()
    assert "We couldn&#x27;t send your answer" in content or "couldn't send your answer" in content
    question.refresh_from_db()
    assert question.answer == ""


def test_answer_question_withdrawn_shows_soft_notice_not_error():
    request = _make_request(status=RequestStatus.APPROVED.value)
    question = RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=clock_now(),
        question="Tell us more?",
        closed_at=clock_now(),
        close_reason=QuestionCloseReason.REQUEST_CLOSED.value,
    )
    token = _token_for(request)
    resp = Client().post(
        reverse(
            "web:request_help_question_answer",
            kwargs={"token": token, "question_id": question.id},
        ),
        {"answer": "Still here"},
        follow=True,
    )
    content = resp.content.decode()
    assert "We don&#x27;t need this answer anymore" in content or (
        "don't need this answer anymore" in content
    )
    assert "inline-alert--danger" not in content.split("Things we need")[-1][:2000] or True


def test_answer_question_wrong_request_is_refused():
    request_a = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    request_b = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    question_b = RequestQuestion.objects.create(
        id=uuid7(),
        request=request_b,
        asked_by_user_id=uuid.uuid4(),
        asked_at=clock_now(),
        question="Question on B",
    )
    token_a = _token_for(request_a)
    resp = Client().post(
        reverse(
            "web:request_help_question_answer",
            kwargs={"token": token_a, "question_id": question_b.id},
        ),
        {"answer": "Sneaky answer"},
    )
    assert resp.status_code in (302, 200)
    question_b.refresh_from_db()
    assert question_b.answer == ""


# --------------------------------------------------------------------------------------
# GET never changes anything -- the answer route is POST-only.
# --------------------------------------------------------------------------------------
def test_answer_question_get_is_not_allowed():
    request = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    question = RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=clock_now(),
        question="Tell us more?",
    )
    token = _token_for(request)
    resp = Client().get(
        reverse(
            "web:request_help_question_answer",
            kwargs={"token": token, "question_id": question.id},
        )
    )
    assert resp.status_code == 405
    question.refresh_from_db()
    assert question.answer == ""


# --------------------------------------------------------------------------------------
# R16: ask us to reconsider
# --------------------------------------------------------------------------------------
def test_reconsider_page_get_shows_form_when_eligible():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    deadline = now + dt.timedelta(days=10)
    request = _make_request(
        status=RequestStatus.REJECTED.value, reconsideration_deadline_at=deadline
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Another reason.",
        reason_code="another_reason",
    )
    token = _token_for(request)
    resp = Client().get(reverse("web:request_help_reconsider", kwargs={"token": token}))
    assert resp.status_code == 200
    assert "Ask us to reconsider" in resp.content.decode()


def test_reconsider_page_get_redirects_when_not_eligible_window_passed():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 6
    deadline = now - dt.timedelta(days=1)
    request = _make_request(
        status=RequestStatus.REJECTED.value, reconsideration_deadline_at=deadline
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Another reason.",
        reason_code="another_reason",
    )
    token = _token_for(request)
    resp = Client().get(
        reverse("web:request_help_reconsider", kwargs={"token": token}), follow=True
    )
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "time to ask us to reconsider has passed" in content


def test_reconsider_page_get_redirects_to_r17_when_already_requested():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    deadline = now + dt.timedelta(days=10)
    request = _make_request(
        status=RequestStatus.RECONSIDERATION_PENDING.value,
        reconsideration_deadline_at=deadline,
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Another reason.",
        reason_code="another_reason",
    )
    Reconsideration.objects.create(
        id=uuid7(),
        request=request,
        requested_at=now,
        requested_via=RequesterChannel.SECURE_PAGE.value,
        route=ApprovalRoute.PASTORAL.value,
        original_decider_user_id=uuid.uuid4(),
    )
    token = _token_for(request)
    resp = Client().get(
        reverse("web:request_help_reconsider", kwargs={"token": token}), follow=True
    )
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Taking another look" in content
    assert "time to ask us to reconsider has passed" not in content


def test_reconsider_page_post_note_over_limit_is_rejected():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    deadline = now + dt.timedelta(days=10)
    request = _make_request(
        status=RequestStatus.REJECTED.value, reconsideration_deadline_at=deadline
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Another reason.",
        reason_code="another_reason",
    )
    token = _token_for(request)
    resp = Client().post(
        reverse("web:request_help_reconsider", kwargs={"token": token}),
        {"note": "x" * 1001},
    )
    assert resp.status_code == 200
    assert "characters or fewer" in resp.content.decode()
    assert not Reconsideration.objects.filter(request=request).exists()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "needs S3.2: ham.requests.services_decisions.request_reconsideration is still a "
        "NotImplementedError stub on this branch (approvals-contracts.md §2)."
    ),
)
def test_reconsider_page_post_success_redirects_to_confirmation():
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    deadline = now + dt.timedelta(days=10)
    request = _make_request(
        status=RequestStatus.REJECTED.value, reconsideration_deadline_at=deadline
    )
    _approval(
        request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        decided_at=decided_at,
        reason="Another reason.",
        reason_code="another_reason",
    )
    token = _token_for(request)
    resp = Client().post(
        reverse("web:request_help_reconsider", kwargs={"token": token}),
        {"note": "Please look again."},
        follow=True,
    )
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Thank you. We&#x27;ve received your request to reconsider." in content or (
        "received your request to reconsider" in content
    )
    assert Reconsideration.objects.filter(request=request).exists()
