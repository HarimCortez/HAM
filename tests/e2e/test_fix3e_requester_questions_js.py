"""Fix 3E item 4 (security L7, UX M8): always-on Playwright coverage for
`requester-questions.js`'s draft lifecycle -- a draft survives a failed submit (kept in
`sessionStorage`) and is cleared only once the server confirms the answer via `?answered=`.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")


def _make_request():
    from ham.platform.clock import now as clock_now
    from ham.requests.models import (
        AssistanceRequest,
        NeedCategory,
        Property,
        Requester,
        next_reference_number,
    )
    from ham.requests.states import RequestStatus

    now = clock_now()
    request = AssistanceRequest.objects.create(
        reference_number=next_reference_number(),
        status=RequestStatus.AWAITING_APPROVAL.value,
        need_category=NeedCategory.values[0],
        description="Water leaks through the bedroom ceiling when it rains.",
        preferred_contact_method=AssistanceRequest._meta.get_field(
            "preferred_contact_method"
        ).choices[0][0],
        relationship_to_property=AssistanceRequest._meta.get_field(
            "relationship_to_property"
        ).choices[0][0],
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
        property_type=Property._meta.get_field("property_type").choices[0][0],
    )
    return request


def _token_for(request) -> str:
    from ham.requester_portal import services

    return services.issue_link(request_id=request.id, kind="initial").token


def test_draft_survives_a_failed_submit_and_clears_only_once_answered(live_server):
    from playwright.sync_api import sync_playwright

    from ham.platform.clock import now as clock_now
    from ham.platform.ids import uuid7
    from ham.requests.models import RequestQuestion

    request = _make_request()
    question = RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=clock_now(),
        question="Does the water come in only when it rains, or also on dry days?",
    )
    token = _token_for(request)
    storage_key = f"ham-question-answer-{question.id}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{live_server.url}/request-help/r/{token}")
        page.wait_for_selector("text=HAM has a question for you")

        # Type a too-long answer and submit it -- the server refuses it
        # (`answer_failed_reason=too_long`), but she never cleared the box herself, so the
        # draft that's already in `sessionStorage` must survive this, unlike the old
        # "clear on every submit" behavior.
        too_long = "x" * 1001
        page.fill(".question-answer-form textarea[name=answer]", too_long)
        assert page.evaluate(f"sessionStorage.getItem('{storage_key}')") == too_long
        page.click(".question-answer-form button[type=submit]")
        page.wait_for_selector("text=too long to send")
        assert "answer_failed_reason=too_long" in page.url
        # The draft is still there after a failed submit (security L7 / UX M8).
        assert page.evaluate(f"sessionStorage.getItem('{storage_key}')") == too_long

        # Now actually send it -- the server confirms via `?answered=<id>`, and only THAT
        # clears the draft.
        page.fill(".question-answer-form textarea[name=answer]", "Only when it rains, so far.")
        page.click(".question-answer-form button[type=submit]")
        page.wait_for_selector("text=got your answer")
        assert f"answered={question.id}" in page.url
        assert page.evaluate(f"sessionStorage.getItem('{storage_key}')") is None

        browser.close()
