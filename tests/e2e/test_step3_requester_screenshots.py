"""Visual QA screenshots for S3.7 (requester screens R13-R19). Opt-in (`HAM_SCREENSHOTS=1`),
same technique as `tests/e2e/test_step2_requester_screenshots.py`. Seeded fake data only (no
real people), per the S3.7 handoff brief.

    HAM_SCREENSHOTS=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \\
        DATABASE_URL=... DJANGO_SETTINGS_MODULE=config.settings.test \\
        pytest tests/e2e/test_step3_requester_screenshots.py -p no:randomly
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HAM_SCREENSHOTS") != "1",
    reason="opt-in visual QA pass; set HAM_SCREENSHOTS=1 to run (see module docstring)",
)
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "ux" / "screenshots" / "step3"
VIEWPORTS = {"390": (390, 844), "1280": (1280, 900)}


def _make_request(*, status, closed_at=None, reconsideration_deadline_at=None):
    from ham.platform.clock import now as clock_now
    from ham.requests.models import AssistanceRequest, NeedCategory, Property, Requester, next_reference_number

    now = clock_now()
    request = AssistanceRequest.objects.create(
        reference_number=next_reference_number(),
        status=status,
        need_category=NeedCategory.values[0],
        description="Water leaks through the bedroom ceiling when it rains (visual QA seed data).",
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
    Requester.objects.create(
        request=request, full_name="Visual QA Requester", email="qa-step3@example.org"
    )
    Property.objects.create(
        request=request,
        line1="1400 NW Example Ave",
        city="Miami",
        state="FL",
        postal_code="33125",
        property_type=Property._meta.get_field("property_type").choices[0][0],
    )
    return request


def _approval(request, *, outcome, decided_at, reason="", reason_code="", urgent_approval=False):
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
        urgent_approval=urgent_approval,
    )


def _token_for(request) -> str:
    from ham.requester_portal import services

    return services.issue_link(request_id=request.id, kind="initial").token


@pytest.mark.django_db(transaction=True)
def test_requester_step3_screens(live_server):
    from ham.platform.clock import now as clock_now
    from ham.platform.ids import uuid7
    from ham.requests.models import RequestQuestion
    from ham.requests.states import RequestStatus
    from ham.rules import RULES
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = clock_now()
    decided_at = now - RULES.approvals.DECISION_UNDO_WINDOW * 2

    question_request = _make_request(status=RequestStatus.AWAITING_APPROVAL.value)
    RequestQuestion.objects.create(
        id=uuid7(),
        request=question_request,
        asked_by_user_id=uuid.uuid4(),
        asked_at=now,
        question="Does the water come in only when it rains, or also on dry days?",
    )
    question_token = _token_for(question_request)

    approved_request = _make_request(status=RequestStatus.APPROVED.value)
    _approval(approved_request, outcome="approved", decided_at=decided_at)
    approved_token = _token_for(approved_request)

    rejected_request = _make_request(
        status=RequestStatus.REJECTED.value,
        reconsideration_deadline_at=now + dt.timedelta(days=10),
    )
    _approval(
        rejected_request,
        outcome="rejected",
        decided_at=decided_at,
        reason="From what you've shared, it sounds like family or others may be able to help.",
        reason_code="family_or_others_can_help",
    )
    rejected_token = _token_for(rejected_request)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, (width, height) in VIEWPORTS.items():
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()

            page.goto(f"{live_server.url}/request-help/r/{question_token}")
            page.wait_for_selector("text=HAM has a question for you")
            page.screenshot(path=str(OUT_DIR / f"requester-question-{label}.png"), full_page=True)

            page.goto(f"{live_server.url}/request-help/r/{approved_token}")
            page.wait_for_selector("text=Approved")
            page.screenshot(path=str(OUT_DIR / f"requester-approved-{label}.png"), full_page=True)

            page.goto(f"{live_server.url}/request-help/r/{rejected_token}")
            page.wait_for_selector("text=Not approved")
            page.screenshot(
                path=str(OUT_DIR / f"requester-not-approved-{label}.png"), full_page=True
            )

            context.close()

        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.goto(f"{live_server.url}/request-help/r/{rejected_token}/reconsider")
        page.wait_for_selector("text=Ask us to reconsider")
        page.screenshot(path=str(OUT_DIR / "requester-reconsider-390.png"), full_page=True)
        context.close()

        browser.close()
