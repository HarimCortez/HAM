"""FIX-3D (step3-ui-visual-qa.md "Re-check at 089473e"): N2 (chip mid-word breaks), N3 (the
urgent banner's actions are content-sized once there's real room), and the "Got it" / count
copy on the urgent banner (M12, `ham.notifications`, not `ham/requests`)."""

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


def _make_pastor_with_urgent_banners(count=1):
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.notifications.models import Notification
    from ham.platform.clock import now as clock_now

    pastor = User.objects.create_user(email=f"pastor-{uuid.uuid4().hex[:6]}@example.org")
    SharedIdentityProfile.objects.create(user=pastor, full_name="Ruth Alvarez")
    RoleAssignment.objects.create(user=pastor, role=roles.PASTOR, granted_at=clock_now())
    for i in range(count):
        Notification.objects.create(
            recipient_user_id=pastor.id,
            kind="request_awaiting_approval",
            subject_type="request",
            subject_id=uuid.uuid4(),
            title=f"Urgent request needs a pastor · HAM #{100 + i}",
            urgent=True,
            requires_ack=True,
        )
    return pastor


def test_chip_no_mid_word_break_at_large_text(live_server):
    """N2: a status chip's label ("Approved") must never break mid-word at 200% text -- the
    `.chip` change that let it wrap onto two lines (M11) inherited `.request-detail p/li`'s
    `overflow-wrap: anywhere` from an ancestor."""
    from playwright.sync_api import sync_playwright

    from ham.authz import roles
    from ham.authz.context import ActorContext
    from ham.requests.services_decisions import approve_request

    pastor, req = _make_awaiting_request_and_pastor()
    ctx = ActorContext(
        user_id=pastor.id,
        real_user_id=None,
        roles=frozenset({roles.PASTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    approve_request(ctx, request_id=req.id, route="pastoral")

    cookie = _session_cookie(live_server, pastor)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 195, "height": 422})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests/{req.id}")
            page.wait_for_load_state("networkidle")

            chip = page.locator(".decision-card .chip").first
            assert chip.count() >= 1
            rects = chip.evaluate(
                """el => {
                    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                    let node;
                    let count = 0;
                    while ((node = walker.nextNode())) {
                        const idx = node.textContent.indexOf('Approved');
                        if (idx === -1) continue;
                        const range = document.createRange();
                        range.setStart(node, idx);
                        range.setEnd(node, idx + 'Approved'.length);
                        count += range.getClientRects().length;
                    }
                    return count;
                }"""
            )
            assert rects == 1, f"'Approved' painted across {rects} line(s)"
        finally:
            browser.close()


def test_urgent_banner_actions_content_sized_at_desktop(live_server):
    """N3: at >=40em (real room beside the banner text), the Open/Got it actions must be
    content-sized, not stretched to fill the row -- at 1280 the QA report measured "Open"
    stretched to 1100-1260px wide."""
    from playwright.sync_api import sync_playwright

    pastor = _make_pastor_with_urgent_banners()
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/")
            page.wait_for_load_state("networkidle")

            open_button = page.locator('.urgent-banner__actions a:has-text("Open")')
            assert open_button.is_visible()
            box = open_button.bounding_box()
            assert box is not None
            assert box["width"] <= 240, f"Open button is {box['width']}px wide, expected <= 240"
        finally:
            browser.close()


def test_urgent_banner_shows_count_and_got_it(live_server):
    """M12: with more than one unacknowledged urgent item, the banner leads with a count
    ("2 urgent requests need you"), and the acknowledge button reads "Got it"."""
    from playwright.sync_api import sync_playwright

    pastor = _make_pastor_with_urgent_banners(count=2)
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/")
            page.wait_for_load_state("networkidle")

            text = page.locator(".urgent-banner__text").text_content() or ""
            assert "2 urgent requests" in text, text
            assert page.locator('.urgent-banner button:has-text("Got it")').is_visible()
        finally:
            browser.close()


def test_urgent_banner_single_item_has_no_count_and_says_got_it(live_server):
    """M12: with exactly one unacknowledged urgent item, no count prefix is shown, but the
    button still reads "Got it" (not the old "I've seen this")."""
    from playwright.sync_api import sync_playwright

    pastor = _make_pastor_with_urgent_banners(count=1)
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/")
            page.wait_for_load_state("networkidle")

            text = page.locator(".urgent-banner__text").text_content() or ""
            assert "urgent requests" not in text, text
            assert page.locator('.urgent-banner button:has-text("Got it")').is_visible()
        finally:
            browser.close()
