"""FIX-3D M10: residual mid-word breaks at 200% text / 195px -- A9's "available" statement
card, A12's "reconsider", and A6's "Something" category label."""

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


def _make_awaiting_request_and_pastor(full_name="Ruth Alvarez"):
    from ham.authz import roles
    from ham.authz.context import RequesterContext, SystemContext
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now
    from ham.requests.services import complete_intake_checks, submit_request
    from tests.requests.conftest import make_payload

    pastor = User.objects.create_user(email=f"pastor-{uuid.uuid4().hex[:6]}@example.org")
    SharedIdentityProfile.objects.create(user=pastor, full_name=full_name)
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


def _make_director(full_name="Marcus Bell"):
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now

    director = User.objects.create_user(email=f"director-{uuid.uuid4().hex[:6]}@example.org")
    SharedIdentityProfile.objects.create(user=director, full_name=full_name)
    RoleAssignment.objects.create(user=director, role=roles.HAM_DIRECTOR, granted_at=clock_now())
    return director


def _word_line_count(locator, word):
    return locator.evaluate(
        """(el, word) => {
            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
            let node;
            let count = 0;
            while ((node = walker.nextNode())) {
                const idx = node.textContent.indexOf(word);
                if (idx === -1) continue;
                const range = document.createRange();
                range.setStart(node, idx);
                range.setEnd(node, idx + word.length);
                count += range.getClientRects().length;
            }
            return count;
        }""",
        word,
    )


@pytest.mark.parametrize("width,height", [(195, 422)])
def test_a12_reconsider_word_no_mid_word_break(live_server, width, height):
    """M10: "reconsider" (in "The requester asked us by phone to reconsider.") must not
    break mid-word at 195px."""
    from playwright.sync_api import sync_playwright

    pastor, req = _make_awaiting_request_and_pastor()

    from ham.authz import roles
    from ham.authz.context import ActorContext, RequesterContext
    from ham.platform.clock import FixedClock, SystemClock, set_clock
    from ham.platform.clock import now as clock_now
    from ham.requests.services_decisions import reject_request
    from ham.rules import RULES
    import datetime as dt

    ctx = ActorContext(
        user_id=pastor.id,
        real_user_id=None,
        roles=frozenset({roles.PASTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    reject_request(
        ctx,
        request_id=req.id,
        route="pastoral",
        reason_code="not_help_ham_offers",
        message="This isn't the kind of work our volunteer teams take on.",
    )

    director = _make_director()
    cookie = _session_cookie(live_server, director)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": width, "height": height})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests/{req.id}/reconsideration/phone")
            page.wait_for_load_state("networkidle")

            statement = page.locator(".choice-card--statement")
            assert statement.count() == 1
            rects = _word_line_count(statement, "reconsider")
            assert rects == 1, f"'reconsider' painted across {rects} line(s)"
        finally:
            browser.close()


def test_a6_something_word_no_mid_word_break(live_server):
    """M10: "Something" (in "Something else or not sure") must not break mid-word at 195px."""
    from playwright.sync_api import sync_playwright

    _, req = _make_awaiting_request_and_pastor()
    director = _make_director()
    cookie = _session_cookie(live_server, director)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 195, "height": 422})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests/{req.id}/category")
            page.wait_for_load_state("networkidle")

            card = page.locator(".choice-card:has-text('Something')").first
            assert card.count() >= 1
            rects = _word_line_count(card, "Something")
            assert rects == 1, f"'Something' painted across {rects} line(s)"
        finally:
            browser.close()


def test_a9_available_word_no_mid_word_break(live_server):
    """M10: "available" (in "Ruth Alvarez isn't available to decide this.") must not break
    mid-word at 195px, on the take-over statement card."""
    from playwright.sync_api import sync_playwright

    from ham.authz import roles
    from ham.authz.context import ActorContext, RequesterContext
    from ham.platform.clock import FixedClock, SystemClock, set_clock
    from ham.platform.clock import now as clock_now
    from ham.requests.services_decisions import reject_request, request_reconsideration
    from ham.rules import RULES
    import datetime as dt

    pastor, req = _make_awaiting_request_and_pastor(full_name="Ruth Alvarez")
    ctx = ActorContext(
        user_id=pastor.id,
        real_user_id=None,
        roles=frozenset({roles.PASTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    reject_request(
        ctx,
        request_id=req.id,
        route="pastoral",
        reason_code="not_help_ham_offers",
        message="This isn't the kind of work our volunteer teams take on.",
    )
    future = clock_now() + RULES.approvals.DECISION_UNDO_WINDOW + dt.timedelta(minutes=1)
    set_clock(FixedClock(future))
    try:
        request_reconsideration(RequesterContext(request_id=req.id), note="Please look again.")
    finally:
        set_clock(SystemClock())

    other_pastor, _ = _make_awaiting_request_and_pastor(full_name="David Kim")
    cookie = _session_cookie(live_server, other_pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 195, "height": 422})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(
                f"{live_server.url}/requests/{req.id}/reconsideration/decide"
                "?outcome=approve&take_over=1"
            )
            page.wait_for_load_state("networkidle")

            statement = page.locator(".choice-card--statement")
            assert statement.count() == 1
            rects = _word_line_count(statement, "available")
            assert rects == 1, f"'available' painted across {rects} line(s)"
        finally:
            browser.close()
