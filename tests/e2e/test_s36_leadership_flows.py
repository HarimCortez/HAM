"""S3.6 always-on Playwright proof (wave brief "S3.6 (leadership screens)"): approve, decline
with the preview, undo and ask a question, at 390 CSS px + 200% text and at 1280. Asserts no
sideways scroll, the primary button is reachable and not covered, and the sticky Decision card
is visible at 1280 (design-system/screens/approvals.md §0.2/§0.3, C§33).
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


def _make_pastor(email="ruth-s36@example.org"):
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now

    user = User.objects.create_user(email=email)
    SharedIdentityProfile.objects.create(user=user, full_name="Ruth Alvarez")
    RoleAssignment.objects.create(user=user, role=roles.PASTOR, granted_at=clock_now())
    return user


def _make_awaiting_request():
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


def _new_page(browser, live_server, cookie, *, width, height, force_200pct_text=False):
    context = browser.new_context(viewport={"width": width, "height": height})
    context.add_cookies([{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}])
    page = context.new_page()
    if force_200pct_text:
        page.add_init_script(
            "document.addEventListener('DOMContentLoaded', () => {"
            " document.documentElement.style.fontSize = '200%';"
            "});"
        )
    return context, page


def _assert_no_sideways_scroll(page):
    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    inner_width = page.evaluate("window.innerWidth")
    assert scroll_width <= inner_width + 1, f"sideways scroll: {scroll_width} > {inner_width}"


def _assert_primary_reachable(page, selector="button.btn--primary, a.btn--primary"):
    box = page.locator(selector).first.bounding_box()
    assert box is not None
    inner_width = page.evaluate("window.innerWidth")
    inner_height = page.evaluate("window.innerHeight")
    assert box["x"] + box["width"] <= inner_width + 1
    center_x, center_y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    if 0 <= center_y <= inner_height:
        el_tag = page.evaluate(
            "([x, y]) => { const el = document.elementFromPoint(x, y);"
            " return el ? el.closest('.btn--primary') !== null : false; }",
            [center_x, center_y],
        )
        assert el_tag, "the primary button is covered at its own center point"


@pytest.mark.parametrize(
    "condition",
    [
        pytest.param({"width": 390, "height": 844, "force_200pct_text": True}, id="390-200pct"),
        pytest.param({"width": 1280, "height": 900, "force_200pct_text": False}, id="1280"),
    ],
)
def test_approve_decline_undo_and_ask_question(live_server, condition):
    from playwright.sync_api import sync_playwright

    pastor = _make_pastor()
    cookie = _session_cookie(live_server, pastor)
    req = _make_awaiting_request()
    # Created up front, not mid-test: a Django DB call from inside the `sync_playwright()`
    # block trips Django's "SynchronousOnlyOperation" async-context guard (playwright's sync
    # API runs its own event loop on this thread).
    req2 = _make_awaiting_request()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context, page = _new_page(
                browser,
                live_server,
                cookie,
                width=condition["width"],
                height=condition["height"],
                force_200pct_text=condition["force_200pct_text"],
            )
            page.goto(f"{live_server.url}/requests/{req.id}")
            page.wait_for_load_state("networkidle")
            _assert_no_sideways_scroll(page)

            if condition["width"] >= 1280:
                # C§33: the Decision card is sticky and visible at >=1024 two-column.
                card = page.locator(".decision-card")
                assert card.is_visible()

            # -------- Approve --------
            page.click("text=Approve…")
            page.wait_for_url("**/approve")
            _assert_no_sideways_scroll(page)
            _assert_primary_reachable(page)
            page.click("button.btn--primary")
            page.wait_for_url(f"**/requests/{req.id}")
            assert "Approved" in page.content()

            # -------- Undo --------
            page.click("text=Undo decision…")
            page.wait_for_url("**/decision/undo*")
            _assert_no_sideways_scroll(page)
            page.click("button.btn--primary")
            page.wait_for_url(f"**/requests/{req.id}")
            assert "Awaiting approval" in page.content()

            # -------- Ask a question --------
            page.click("text=Ask a question")
            page.wait_for_url("**/questions/ask")
            page.fill("#id_question", "Does the water come in only when it rains?")
            _assert_no_sideways_scroll(page)
            _assert_primary_reachable(page)
            page.click("button.btn--primary")
            page.wait_for_url(f"**/requests/{req.id}")
            assert "Does the water come in only when it rains?" in page.content()

            # -------- Decline (a second, already-prepared request) --------
            page.goto(f"{live_server.url}/requests/{req2.id}")
            page.click("text=Decline…")
            page.wait_for_url("**/reject")
            page.check("input[name=reason_code][value=family_or_others_can_help]")
            _assert_no_sideways_scroll(page)
            preview_text = page.locator("#decline-preview-message").inner_text()
            assert "family" in preview_text.lower()
            _assert_primary_reachable(page)
            page.click("button.btn--primary")
            page.wait_for_url(f"**/requests/{req2.id}")
            assert "Rejected" in page.content()

            context.close()
        finally:
            browser.close()
