"""FIX-F1 leadership-screen regressions:

* N4: the `/requests` split-view detail pane is a scrollable `role="region"` with no
  focusable content of its own (axe `scrollable-region-focusable`, serious). It already has an
  accessible name (`aria-label`); this proves it can now actually receive keyboard focus.
* N-M2/M10: the L9 phone-check sheet's sticky "Verified by phone call" primary button must not
  be covered by the fixed bottom nav at <1024 -- `elementFromPoint` at the button's center must
  resolve to the button itself, not to the nav sitting on top of it.
"""

from __future__ import annotations

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


def _make_director():
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now

    user = User.objects.create_user(email="marcus-fixf1-lead@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=user, role=roles.HAM_DIRECTOR, granted_at=clock_now())
    return user


def _make_awaiting_request():
    import uuid

    from ham.authz.context import RequesterContext, SystemContext
    from ham.requests.services import complete_intake_checks, submit_request
    from tests.requests.conftest import make_payload

    req = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(),
    )
    complete_intake_checks(SystemContext(), request_id=req.id)
    return req


def _make_no_email_request():
    import uuid

    from ham.authz.context import RequesterContext
    from ham.requests.services import submit_request
    from tests.requests.conftest import no_email_payload

    return submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=None,
        payload=no_email_payload(full_name="Ruth Hall", phone="+13055550177"),
    )


def test_urgent_banner_wraps_instead_of_squeezing_text_at_390(live_server):
    """FIX-F1 N5: `.urgent-banner__text { flex: 1; min-width: var(--ham-size-target-min) }`
    used to let the text column shrink to ~80px at 390, wrapping a long title to many lines
    beside the buttons and making the sticky banner roughly 22% of the viewport. The banner
    should stay reasonably short even with a long title."""
    import uuid

    from ham.notifications.models import Notification

    director = _make_director()
    cookie = _session_cookie(live_server, director)
    Notification.objects.create(
        recipient_user_id=director.id,
        kind="request_urgent",
        subject_type="request",
        subject_id=uuid.uuid4(),
        title="Urgent request needs a pastor · HAM #027 Roof or ceiling",
        urgent=True,
        requires_ack=True,
    )

    from playwright.sync_api import sync_playwright

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

            text_box = page.locator(".urgent-banner__text").bounding_box()
            assert text_box is not None
            # N5: `min-width: var(--ham-size-target-min)` resolves to 48px (the tap-target
            # token, not a readable-text minimum), so the old rule let the text column shrink
            # to ~170px at 390 -- barely wider than a couple of words. `flex: 1 1 16em` keeps
            # it comfortably wide instead of squeezing down toward the buttons' footprint.
            assert text_box["width"] > 250, (
                f"urgent banner text is only {text_box['width']}px wide at 390"
            )
            context.close()
        finally:
            browser.close()


def test_director_home_phone_check_card_has_phone_icon(live_server):
    """FIX-F1 M17 remainder: the Director's "N requests need a phone check" Home card carries
    a phone-call icon (design-system/screens/intake.md "Director/AD Home")."""
    from playwright.sync_api import sync_playwright

    director = _make_director()
    cookie = _session_cookie(live_server, director)
    _make_no_email_request()

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

            card = page.locator(".attention-card", has_text="phone check")
            icon = card.locator("svg.attention-card__icon use")
            assert "icon-phone-call" in (icon.get_attribute("href") or "")
            context.close()
        finally:
            browser.close()


def test_split_detail_pane_is_focusable(live_server):
    from playwright.sync_api import sync_playwright

    director = _make_director()
    cookie = _session_cookie(live_server, director)
    req = _make_awaiting_request()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests?tab=all&id={req.id}")
            page.wait_for_load_state("networkidle")

            pane = page.locator(".split-detail")
            assert pane.get_attribute("tabindex") == "0"
            pane.focus()
            is_active = page.evaluate(
                "document.activeElement === document.querySelector('.split-detail')"
            )
            assert is_active, "split-detail pane didn't receive keyboard focus"
            context.close()
        finally:
            browser.close()


def test_phone_check_primary_button_not_covered_at_390(live_server):
    from playwright.sync_api import sync_playwright

    director = _make_director()
    cookie = _session_cookie(live_server, director)
    req = _make_no_email_request()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests/{req.id}/phone-check")
            page.wait_for_load_state("networkidle")

            button = page.get_by_role("button", name="Verified by phone call")
            box = button.bounding_box()
            assert box is not None
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            button_handle = button.element_handle()
            is_button = page.evaluate(
                "([btn, x, y]) => {"
                " const el = document.elementFromPoint(x, y);"
                " return el === btn || btn.contains(el);"
                "}",
                [button_handle, cx, cy],
            )
            assert is_button, (
                f"element at the primary button's center ({cx}, {cy}) isn't the button -- "
                "something (the bottom nav?) is covering it"
            )
            context.close()
        finally:
            browser.close()
