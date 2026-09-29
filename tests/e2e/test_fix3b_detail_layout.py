"""FIX-3B B4/M1: the Decision card is only ever `position: sticky` once the request-detail
container is genuinely two columns (>=42em container), never in a one-column layout, and it
must never overlap the "Earlier request found" alert (step3-ui-visual-qa.md B4/M1).
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def _session_cookie(live_server, django_user):
    from django.conf import settings
    from django.test import Client

    client = Client()
    client.force_login(django_user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return {
        "name": settings.SESSION_COOKIE_NAME,
        "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
        "url": live_server.url,
    }


def _make_awaiting_request_and_pastor():
    from ham.authz import roles
    from ham.authz.context import RequesterContext, SystemContext
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now
    from ham.requests.services import complete_intake_checks, submit_request
    from tests.requests.conftest import make_payload

    pastor = User.objects.create_user(email=f"pastor-{uuid.uuid4().hex[:6]}@example.org")
    SharedIdentityProfile.objects.create(user=pastor, full_name="Ruth Alvarez")
    RoleAssignment.objects.create(user=pastor, role=roles.PASTOR, granted_at=clock_now())

    req = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(
            full_name="Fictional Requester",
            description="Water comes through the bedroom ceiling when it rains "
            "(fictional test data).",
        ),
    )
    complete_intake_checks(SystemContext(), request_id=req.id)
    return pastor, req


def test_decision_card_never_overlaps_earlier_request_alert(live_server):
    """B4: with an "Earlier request found" alert present (a real duplicate match), the
    Decision card -- sticky or not -- must never visually overlap it, in the split-view pane
    at 1280 (the exact scenario the QA report measured: the alert's own chevron showed through
    the Rejected chip)."""
    from playwright.sync_api import sync_playwright

    from ham.platform.clock import now as clock_now
    from ham.requests.models import RequestMatch

    pastor, req = _make_awaiting_request_and_pastor()
    _, prior = _make_awaiting_request_and_pastor()
    RequestMatch.objects.create(
        request=req, prior_request=prior, reasons=["same_address"], detected_at=clock_now()
    )
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests?tab=awaiting&id={req.id}")
            page.wait_for_load_state("networkidle")
            # The pane scrolls independently (M12) -- the sticky-card bug only shows once the
            # pane is scrolled past the card's own natural position.
            page.eval_on_selector(".split-detail", "el => { el.scrollTop = 400; }")

            card_box = page.eval_on_selector(
                ".split-detail .decision-card",
                "el => { const r = el.getBoundingClientRect(); return {top: r.top, bottom: r.bottom, left: r.left, right: r.right}; }",
            )
            alert_box = page.eval_on_selector(
                ".split-detail .inline-alert--info",
                "el => { const r = el.getBoundingClientRect(); return {top: r.top, bottom: r.bottom, left: r.left, right: r.right}; }",
            )
            overlaps = (
                card_box["left"] < alert_box["right"]
                and card_box["right"] > alert_box["left"]
                and card_box["top"] < alert_box["bottom"]
                and card_box["bottom"] > alert_box["top"]
            )
            assert not overlaps, f"card {card_box} overlaps alert {alert_box}"
        finally:
            browser.close()


def test_decision_card_sticky_at_1440_two_column(live_server):
    """B4: at 1440 the standalone detail page is genuinely two columns, so the card is
    allowed (expected) to be sticky there."""
    from playwright.sync_api import sync_playwright

    pastor, req = _make_awaiting_request_and_pastor()
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests/{req.id}")
            page.wait_for_load_state("networkidle")

            position = page.eval_on_selector(
                ".decision-card", "el => getComputedStyle(el).position"
            )
            assert position == "sticky"

            grid_columns = page.eval_on_selector(
                ".request-detail__grid", "el => getComputedStyle(el).gridTemplateColumns"
            )
            assert "," not in grid_columns or len(grid_columns.split()) >= 2
        finally:
            browser.close()
