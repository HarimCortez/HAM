"""S3.7 always-on Playwright coverage (task brief "An always-on Playwright test at 390+200%
text and at 1280 for: answer a question, a not-approved page, and reconsider. Assert no
sideways scroll and that the primary button is reachable."). Same shape/rationale as
`tests/e2e/test_smoke.py` (no opt-in marker -- runs in the normal `pytest` sweep) and
`tests/e2e/test_fix_h_n6_action_bar_height.py` (200%-text technique: force
`document.documentElement.style.fontSize` after DOMContentLoaded, since Playwright can't drive
real browser *zoom*).
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

VIEWPORTS = {
    "390-200pct-text": {"width": 390, "height": 844, "force_200pct_text": True},
    "1280": {"width": 1280, "height": 900, "force_200pct_text": False},
}


def _make_request(*, status, closed_at=None, reconsideration_deadline_at=None):
    from ham.platform.clock import now as clock_now
    from ham.requests.models import AssistanceRequest, NeedCategory, Property, Requester, next_reference_number

    now = clock_now()
    request = AssistanceRequest.objects.create(
        reference_number=next_reference_number(),
        status=status,
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
        closed_at=closed_at,
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


def _approval(request, *, outcome, decided_at, reason="", reason_code=""):
    from ham.platform.ids import uuid7
    from ham.requests.models import Approval as ApprovalModel
    from ham.requests.models import ApprovalOutcome, ApprovalRoute, ApprovalStage
    from ham.rules import RULES

    return ApprovalModel.objects.create(
        id=uuid7(),
        request=request,
        stage=ApprovalStage.INITIAL.value,
        outcome=outcome,
        route=ApprovalRoute.PASTORAL.value,
        decided_by_user_id=uuid.uuid4(),
        decided_at=decided_at,
        effective_at=decided_at + RULES.approvals.DECISION_UNDO_WINDOW,
        reason=reason,
        reason_code=reason_code,
    )


def _token_for(request) -> str:
    from ham.requester_portal import services

    return services.issue_link(request_id=request.id, kind="initial").token


def _apply_200pct(page):
    page.add_init_script(
        "document.addEventListener('DOMContentLoaded', () => {"
        " document.documentElement.style.fontSize = '200%';"
        "});"
    )


def _assert_no_sideways_scroll(page):
    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    inner_width = page.evaluate("window.innerWidth")
    assert scroll_width <= inner_width, (
        f"page scrolls sideways: scrollWidth={scroll_width} > innerWidth={inner_width}"
    )


def _assert_reachable(page, selector: str):
    el = page.query_selector(selector)
    assert el is not None, f"{selector!r} not found on the page"
    assert el.is_visible(), f"{selector!r} is not visible"
    box = el.bounding_box()
    assert box is not None and box["y"] >= 0, f"{selector!r} is off-screen"


@pytest.mark.parametrize("label", list(VIEWPORTS))
def test_answer_a_question_screen(live_server, label):
    from ham.platform.clock import now as clock_now
    from ham.platform.ids import uuid7
    from ham.requests.models import RequestQuestion
    from ham.requests.states import RequestStatus
    from playwright.sync_api import sync_playwright

    request = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    RequestQuestion.objects.create(
        id=uuid7(),
        request=request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=clock_now(),
        question="Does the water come in only when it rains, or also on dry days?",
    )
    token = _token_for(request)
    condition = VIEWPORTS[label]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": condition["width"], "height": condition["height"]}
        )
        page = context.new_page()
        if condition["force_200pct_text"]:
            _apply_200pct(page)

        page.goto(f"{live_server.url}/request-help/r/{token}")
        page.wait_for_selector("text=HAM has a question for you")

        _assert_no_sideways_scroll(page)
        _assert_reachable(page, ".question-answer-form button[type=submit]")

        # Regression (visual QA): `.form-field__offline-reason`'s own `display: flex` used to
        # beat the browser's native `[hidden] { display: none }` (author beats UA at equal
        # specificity), showing "You're offline..." on every normal, online load. Give the
        # deferred script (and any font/asset settling) a moment before asserting the default
        # state is actually hidden -- `wait_for_selector` above only proves the *server-
        # rendered* text exists, not that client JS has finished running yet.
        page.wait_for_timeout(200)
        offline_reason = page.query_selector(".form-field__offline-reason")
        assert offline_reason is not None
        assert not offline_reason.is_visible(), (
            "the offline reason line is visible while actually online"
        )

        page.fill(".question-answer-form textarea[name=answer]", "Only when it rains, so far.")
        page.click(".question-answer-form button[type=submit]")
        page.wait_for_selector("text=got your answer")
        _assert_no_sideways_scroll(page)

        context.close()
        browser.close()


@pytest.mark.parametrize("label", list(VIEWPORTS))
def test_not_approved_screen(live_server, label):
    from ham.platform.clock import now as clock_now
    from ham.requests.states import RequestStatus
    from ham.rules import RULES
    from playwright.sync_api import sync_playwright

    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    request = _make_request(
        status=RequestStatus.REJECTED.value,
        reconsideration_deadline_at=now + dt.timedelta(days=10),
    )
    _approval(
        request,
        outcome="rejected",
        decided_at=decided_at,
        reason="From what you've shared, it sounds like family or others may be able to help.",
        reason_code="family_or_others_can_help",
    )
    token = _token_for(request)
    condition = VIEWPORTS[label]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": condition["width"], "height": condition["height"]}
        )
        page = context.new_page()
        if condition["force_200pct_text"]:
            _apply_200pct(page)

        page.goto(f"{live_server.url}/request-help/r/{token}")
        page.wait_for_selector("text=Not approved")

        _assert_no_sideways_scroll(page)
        _assert_reachable(page, "a.btn:has-text('Ask us to reconsider')")

        context.close()
        browser.close()


@pytest.mark.parametrize("label", list(VIEWPORTS))
def test_reconsider_screen(live_server, label):
    from ham.platform.clock import now as clock_now
    from ham.requests.states import RequestStatus
    from ham.rules import RULES
    from playwright.sync_api import sync_playwright

    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2
    request = _make_request(
        status=RequestStatus.REJECTED.value,
        reconsideration_deadline_at=now + dt.timedelta(days=10),
    )
    _approval(
        request, outcome="rejected", decided_at=decided_at,
        reason="Another reason.", reason_code="another_reason",
    )
    token = _token_for(request)
    condition = VIEWPORTS[label]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": condition["width"], "height": condition["height"]}
        )
        page = context.new_page()
        if condition["force_200pct_text"]:
            _apply_200pct(page)

        page.goto(f"{live_server.url}/request-help/r/{token}/reconsider")
        page.wait_for_selector("text=Ask us to reconsider")

        _assert_no_sideways_scroll(page)
        _assert_reachable(page, "button:has-text('Send my request to reconsider')")

        context.close()
        browser.close()
