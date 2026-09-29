"""FIX-3B B2/B3: sheet action bars must hold only the primary under 22em (Cancel moves into
the flow), the bar must be pinned to the bottom on a short sheet, and no button inside the
sheet (e.g. "Decline HAM #...") must break mid-word (step3-ui-visual-qa.md B2/B3).
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


def test_decline_sheet_bar_holds_only_primary_under_22em(live_server):
    """B2: at 195px (== 200% text on a 390 viewport), only the primary button is inside
    `.action-bar` -- Cancel must have moved into the in-flow twin above it."""
    from playwright.sync_api import sync_playwright

    pastor, req = _make_awaiting_request_and_pastor()
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 195, "height": 422})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests/{req.id}/reject")
            page.wait_for_load_state("networkidle")

            bar_buttons = page.locator(".action-bar .btn:visible")
            assert bar_buttons.count() == 1, (
                f"expected only the primary in the bar under 22em, found {bar_buttons.count()}"
            )
            assert "Decline" in (bar_buttons.first.text_content() or "")

            # The in-flow twin (Cancel) must be reachable, above the bar.
            twin = page.locator(".wizard-back-link a")
            assert twin.is_visible()

            bar_height = page.eval_on_selector(
                ".action-bar", "el => el.getBoundingClientRect().height"
            )
            assert bar_height / 422 <= 0.18, f"bar is {bar_height / 422:.0%} of the viewport"
        finally:
            browser.close()


def test_undo_button_label_does_not_break_mid_word(live_server):
    """B3: "Undo decision..." inside the pending inline-alert must not break one letter per
    line at large text -- proven geometrically (a Range over the word "decision" must paint
    on a single line), not just "does the text appear intact"."""
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

            button = page.locator(".decision-card a.btn:has-text('Undo decision')")
            assert button.count() == 1
            rects = button.evaluate(
                """el => {
                    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                    let node;
                    let count = 0;
                    while ((node = walker.nextNode())) {
                        const idx = node.textContent.indexOf('decision');
                        if (idx === -1) continue;
                        const range = document.createRange();
                        range.setStart(node, idx);
                        range.setEnd(node, idx + 'decision'.length);
                        count += range.getClientRects().length;
                    }
                    return count;
                }"""
            )
            assert rects == 1, f"'decision' painted across {rects} line(s)"
        finally:
            browser.close()
