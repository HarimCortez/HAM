"""FIX-3D (step3-ui-visual-qa.md "Re-check at 089473e"): sheet h1 reflow (N1), the pending/
undo notice inside the Decision card (B3 residue), a short sheet's bar actually pinning at
large text once its `<form>` wraps the whole sheet body (B2 residue), and A9's decline prefill
+ preview (M7).
"""

from __future__ import annotations

import datetime as dt
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


def _make_reconsideration_pending():
    """A request declined, then (after the undo window) the requester asked to reconsider --
    lands the original pastor on A9 (`request_reconsideration_decide`)."""
    from ham.authz import roles
    from ham.authz.context import ActorContext, RequesterContext
    from ham.platform.clock import FixedClock, SystemClock, set_clock
    from ham.platform.clock import now as clock_now
    from ham.requests.services_decisions import reject_request, request_reconsideration
    from ham.rules import RULES

    pastor, req = _make_awaiting_request_and_pastor()
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
    req.refresh_from_db()
    return pastor, req


def test_a9_h1_no_sideways_scroll_at_large_text(live_server):
    """N1: a single long word at h1 size ("reconsideration?") must not force horizontal
    scroll at 200% text (390 CSS px measured as 195 real px) or at a real 195px viewport."""
    from playwright.sync_api import sync_playwright

    pastor, req = _make_reconsideration_pending()
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # 195x422 alone already *is* 200% zoom (QA method); a 390 viewport needs the root
            # font bumped separately to simulate 200% text -- doing both at once double-applies
            # the zoom.
            for width, height, big_text in [(195, 422, False), (390, 844, True)]:
                context = browser.new_context(viewport={"width": width, "height": height})
                context.add_cookies(
                    [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
                )
                page = context.new_page()
                if big_text:
                    page.add_init_script(
                        "document.addEventListener('DOMContentLoaded', () => {"
                        "document.documentElement.style.fontSize = '32px'; })"
                    )
                page.goto(f"{live_server.url}/requests/{req.id}/reconsideration/decide?outcome=approve")
                page.wait_for_load_state("networkidle")

                scroll_width = page.evaluate("document.documentElement.scrollWidth")
                inner_width = page.evaluate("window.innerWidth")
                assert scroll_width <= inner_width, (
                    f"at {width}px: h1 forces sideways scroll: scrollWidth={scroll_width} "
                    f"> innerWidth={inner_width}"
                )
                context.close()
        finally:
            browser.close()


def test_pending_notice_button_stays_inside_its_border(live_server):
    """B3 residue: "Undo decision..." must never spill outside its own button border at
    195/200% text -- proven geometrically (the button's own border box must fully contain
    every text-node rect inside it), not just "the label appears intact"."""
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
            overflow = button.evaluate(
                """el => {
                    const btnRect = el.getBoundingClientRect();
                    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                    let node;
                    let maxOverflow = 0;
                    while ((node = walker.nextNode())) {
                        const range = document.createRange();
                        range.selectNodeContents(node);
                        for (const rect of range.getClientRects()) {
                            maxOverflow = Math.max(
                                maxOverflow,
                                btnRect.left - rect.left,
                                rect.right - btnRect.right
                            );
                        }
                    }
                    return maxOverflow;
                }"""
            )
            assert overflow <= 1, f"button text spills {overflow}px outside its own border"
        finally:
            browser.close()


def test_pending_notice_icon_dropped_under_22em(live_server):
    """B3: under 22em the pending/undo notice's leading icon must be hidden, so the text and
    the Undo button get the alert's full width instead of competing with a 20px icon column."""
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

            icon = page.locator(".decision-card .inline-alert__icon")
            assert icon.count() >= 1
            assert not icon.first.is_visible(), "the alert icon should be hidden under 22em"
        finally:
            browser.close()


def test_a9_decline_prefills_message_and_shows_preview(live_server):
    """M7: picking a decline reason on A9 fills the message from
    `REJECTION_REASON_PREFILLS` (same Replace/Keep behaviour as A3), and a "What the
    requester will read" preview renders the final (R18b) wording."""
    from playwright.sync_api import sync_playwright

    pastor, req = _make_reconsideration_pending()
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests/{req.id}/reconsideration/decide?outcome=decline")
            page.wait_for_load_state("networkidle")

            message_field = page.locator("#id_reason_decline")
            assert message_field.input_value() == ""

            page.locator(
                '#recon-decline-reasons input[value="not_help_ham_offers"]'
            ).check(force=True)
            page.wait_for_timeout(50)
            filled = message_field.input_value()
            assert filled != "", "message should be prefilled once a reason is picked"

            preview = page.locator("#recon-decline-preview-message")
            assert preview.is_visible()
            assert filled in (preview.text_content() or "")

            heading = page.locator("#recon-decline-preview-heading")
            assert "What the requester will read" in (heading.text_content() or "")
        finally:
            browser.close()


def test_a9_decline_replace_keep_row_appears_on_dirty_edit(live_server):
    """M7/M8: editing the message, then changing the reason, must ask Replace/Keep instead of
    silently discarding the decider's own words -- same as A3."""
    from playwright.sync_api import sync_playwright

    pastor, req = _make_reconsideration_pending()
    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}/requests/{req.id}/reconsideration/decide?outcome=decline")
            page.wait_for_load_state("networkidle")

            page.locator(
                '#recon-decline-reasons input[value="not_help_ham_offers"]'
            ).check(force=True)
            page.wait_for_timeout(50)
            message_field = page.locator("#id_reason_decline")
            message_field.fill("My own carefully written note.")

            page.locator(
                '#recon-decline-reasons input[value="couldnt_confirm"]'
            ).check(force=True)
            page.wait_for_timeout(50)

            assert message_field.input_value() == "My own carefully written note."
            replace_row = page.locator("#recon-reason-replace-row")
            assert replace_row.is_visible()
        finally:
            browser.close()
