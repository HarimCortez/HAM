"""S3.0: `ham.requests.services_questions.close_open_questions` -- the one real (non-stub)
function in the S3.3 seam (approvals-contracts.md §2), since S3.2's decision commands call it
inside their own transaction. Everything else in `services_decisions`/`services_questions` is
a `NotImplementedError` stub, exercised by `tests/requests/test_step3_service_stubs.py`.
"""

from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from ham.requests.models import QuestionCloseReason, RequestQuestion
from ham.requests.services import submit_request
from ham.requests.services_questions import close_open_questions

from .conftest import make_payload

pytestmark = pytest.mark.django_db


def _make_request(requester_ctx):
    return submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(),
    )


def _make_question(request, **overrides):
    defaults = dict(
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=timezone.now(),
        question="What color is the roof?",
    )
    defaults.update(overrides)
    return RequestQuestion.objects.create(**defaults)


class TestCloseOpenQuestions:
    def test_closes_every_open_question(self, requester_ctx):
        req = _make_request(requester_ctx)
        q1 = _make_question(req)
        q2 = _make_question(req, question="Anything else?")

        closed = close_open_questions(req.id, reason="request_closed")

        assert closed == 2
        q1.refresh_from_db()
        q2.refresh_from_db()
        assert q1.closed_at is not None
        assert q1.close_reason == QuestionCloseReason.REQUEST_CLOSED.value
        assert q2.closed_at is not None

    def test_leaves_answered_questions_alone(self, requester_ctx):
        req = _make_request(requester_ctx)
        answered = _make_question(req)
        answered.answer = "Blue"
        answered.answered_at = timezone.now()
        answered.answered_via = "secure_page"
        answered.save(update_fields=["answer", "answered_at", "answered_via"])

        closed = close_open_questions(req.id, reason="request_closed")

        assert closed == 0
        answered.refresh_from_db()
        assert answered.closed_at is None

    def test_leaves_already_closed_questions_alone(self, requester_ctx):
        req = _make_request(requester_ctx)
        question = _make_question(req)
        first_close = timezone.now()
        question.closed_at = first_close
        question.close_reason = QuestionCloseReason.WITHDRAWN.value
        question.save(update_fields=["closed_at", "close_reason"])

        closed = close_open_questions(req.id, reason="request_closed")

        assert closed == 0
        question.refresh_from_db()
        assert question.close_reason == QuestionCloseReason.WITHDRAWN.value

    def test_no_open_questions_is_a_no_op(self, requester_ctx):
        req = _make_request(requester_ctx)
        assert close_open_questions(req.id, reason="request_closed") == 0

    def test_never_touches_another_requests_questions(self, requester_ctx):
        req1 = _make_request(requester_ctx)
        req2 = _make_request(requester_ctx)
        other_question = _make_question(req2)

        close_open_questions(req1.id, reason="request_closed")

        other_question.refresh_from_db()
        assert other_question.closed_at is None
