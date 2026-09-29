"""Fix 3E item 4 (security L7, UX M8): empty and too-long answers get distinct messages,
server-side, and the redirect carries `answer_failed_reason` for the template/JS to key on.
"""

from __future__ import annotations

import uuid

import pytest
from django.test import Client
from django.urls import reverse

from ham.platform.clock import now as clock_now
from ham.platform.ids import uuid7
from ham.requester_portal import services
from ham.requests.models import (
    AssistanceRequest,
    NeedCategory,
    Property,
    Requester,
    RequestQuestion,
    next_reference_number,
)
from ham.requests.states import RequestStatus

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _real_portal_lookups(real_portal_lookups):
    pass


def _make_request() -> AssistanceRequest:
    now = clock_now()
    request = AssistanceRequest.objects.create(
        reference_number=next_reference_number(),
        status=RequestStatus.AWAITING_APPROVAL.value,
        need_category=NeedCategory.values[0],
        description="Water leaks through the bedroom ceiling.",
        preferred_contact_method=AssistanceRequest._meta.get_field(
            "preferred_contact_method"
        ).choices[0][0],  # type: ignore[index]
        relationship_to_property=AssistanceRequest._meta.get_field(
            "relationship_to_property"
        ).choices[0][0],  # type: ignore[index]
        attestation_version="test",
        submitted_at=now,
        status_changed_at=now,
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


def _question(request):
    return RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=clock_now(),
        question="Does the water come in only when it rains?",
    )


def _token_for(request) -> str:
    return services.issue_link(request_id=request.id, kind="initial").token


class TestDistinctFailureMessages:
    def test_empty_answer_message(self):
        request = _make_request()
        question = _question(request)
        token = _token_for(request)
        resp = Client().post(
            reverse(
                "web:request_help_question_answer",
                kwargs={"token": token, "question_id": question.id},
            ),
            {"answer": "   "},
            follow=True,
        )
        content = resp.content.decode()
        assert "write an answer before sending" in content
        assert "too long to send" not in content
        assert "answer_failed_reason=empty" in resp.redirect_chain[0][0]

    def test_too_long_answer_message(self):
        request = _make_request()
        question = _question(request)
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
        assert "too long to send" in content
        assert "write an answer before sending" not in content
        assert "answer_failed_reason=too_long" in resp.redirect_chain[0][0]

    def test_success_redirect_carries_answered_not_answer_failed(self):
        request = _make_request()
        question = _question(request)
        token = _token_for(request)
        resp = Client().post(
            reverse(
                "web:request_help_question_answer",
                kwargs={"token": token, "question_id": question.id},
            ),
            {"answer": "Only when it rains."},
        )
        assert resp.status_code == 302
        assert f"answered={question.id}" in resp.url
        assert "answer_failed" not in resp.url
