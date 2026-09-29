"""FIX-3D Minors: `.urgent-banner-slot` (not `.urgent-banner`) is the sticky element, and the
request-detail side column stretches tall enough for the sticky Decision card to actually
stick."""

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


def test_urgent_banner_slot_is_the_sticky_element(live_server):
    """Minor: `.urgent-banner`'s own `position: sticky` never actually stuck, since its
    containing block (`.urgent-banner-slot`) wraps it exactly -- a box can't scroll past its
    own containing block. `.urgent-banner-slot` itself must be sticky at >=22em and >=30em
    tall."""
    from playwright.sync_api import sync_playwright

    pastor = _make_pastor_with_urgent_banner()
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

            position = page.eval_on_selector(
                ".urgent-banner-slot", "el => getComputedStyle(el).position"
            )
            assert position == "sticky", f"slot is {position}, expected sticky"
        finally:
            browser.close()


def test_side_column_is_tall_enough_for_sticky_card(live_server):
    """Minor: the grid's own `align-items: start` sized `.request-detail__side` to just its
    own content (the card), leaving it no taller than the card -- a sticky card inside a box
    exactly its own height has no room to travel and never visibly sticks. The side column
    must stretch to (at least close to) the main column's height."""
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

            main_height = page.eval_on_selector(
                ".request-detail__main", "el => el.getBoundingClientRect().height"
            )
            side_height = page.eval_on_selector(
                ".request-detail__side", "el => el.getBoundingClientRect().height"
            )
            card_height = page.eval_on_selector(
                ".decision-card", "el => el.getBoundingClientRect().height"
            )
            assert side_height > card_height + 20, (
                f"side column ({side_height}px) is barely taller than the card itself "
                f"({card_height}px) -- no room for it to stick; main is {main_height}px"
            )
        finally:
            browser.close()
