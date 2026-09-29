"""FIX-3B B1: the urgent banner must not force sideways scroll or stay sticky at large text
(step3-ui-visual-qa.md B1), and must never render on a full-screen sheet (a decision is
already in progress there, and the sticky banner used to stack with the sheet's own pinned
action bar and could cover the whole viewport at 195px).
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


def _make_pastor_with_urgent_banner():
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.notifications.models import Notification
    from ham.platform.clock import now as clock_now

    pastor = User.objects.create_user(email=f"pastor-{uuid.uuid4().hex[:6]}@example.org")
    SharedIdentityProfile.objects.create(user=pastor, full_name="Ruth Alvarez")
    RoleAssignment.objects.create(user=pastor, role=roles.PASTOR, granted_at=clock_now())
    Notification.objects.create(
        recipient_user_id=pastor.id,
        kind="request_awaiting_approval",
        subject_type="request",
        subject_id=uuid.uuid4(),
        title="Urgent request needs a pastor · HAM #048",
        urgent=True,
        requires_ack=True,
    )
    return pastor


def test_urgent_banner_no_sideways_scroll_at_large_text(live_server):
    """B1: at 390 CSS px + 200% text (measured as 195 real px, per the QA method), the banner
    must not force the page wider than the viewport, and "I've seen this" must not be clipped
    off the right edge."""
    from playwright.sync_api import sync_playwright

    pastor = _make_pastor_with_urgent_banner()
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 195, "height": 422})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/")
            page.wait_for_load_state("networkidle")

            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            inner_width = page.evaluate("window.innerWidth")
            assert scroll_width <= inner_width, (
                f"banner forces sideways scroll: scrollWidth={scroll_width} "
                f"> innerWidth={inner_width}"
            )

            # M12 (FIX-3D) renamed the button "Got it" -- was "I've seen this".
            seen_button = page.locator('button:has-text("Got it")')
            assert seen_button.is_visible()
            box = seen_button.bounding_box()
            assert box is not None
            assert box["x"] + box["width"] <= inner_width + 1
        finally:
            browser.close()


def test_urgent_banner_is_static_under_22em(live_server):
    """B1: below the 22em container-query threshold the banner must not be `position: sticky`
    -- otherwise it (plus a sheet's own pinned bar) can exceed the viewport height and cover
    every control on the page."""
    from playwright.sync_api import sync_playwright

    pastor = _make_pastor_with_urgent_banner()
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 195, "height": 422})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/")
            page.wait_for_load_state("networkidle")

            position = page.eval_on_selector(
                ".urgent-banner", "el => getComputedStyle(el).position"
            )
            assert position == "static", f"banner is {position} under 22em, expected static"
        finally:
            browser.close()


def test_urgent_banner_absent_on_fullscreen_sheet(live_server):
    """B1: a full-screen sheet (a decision already in progress) must not render the banner at
    all -- it used to stack with the sheet's own sticky action bar and could cover the whole
    viewport at large text."""
    from playwright.sync_api import sync_playwright

    from ham.authz.context import RequesterContext, SystemContext
    from ham.identity.models import SharedIdentityProfile
    from ham.requests.services import complete_intake_checks, submit_request
    from tests.requests.conftest import make_payload

    pastor = _make_pastor_with_urgent_banner()
    SharedIdentityProfile.objects.filter(user=pastor).update(full_name="Ruth Alvarez")

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

    cookie = _session_cookie(live_server, pastor)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests/{req.id}/reject")
            page.wait_for_load_state("networkidle")
            assert page.locator(".urgent-banner").count() == 0
        finally:
            browser.close()
