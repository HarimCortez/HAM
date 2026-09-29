"""Fix 3E item 3 / UX M5 minor: after a 422 re-render, the pastor's own typed message is not
treated as "the last suggested prefill" -- the next reason change must still ask before
overwriting it.
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
    # Dual-role (Pastor + Board rep): the route radios are shown (never preselected, PRD
    # guardian M1/Q-164) instead of a hidden auto-filled field -- a plain PASTOR-only viewer's
    # route is always auto-filled, so a 422 with NO route missing is unreachable for them.
    RoleAssignment.objects.create(
        user=pastor, role=roles.BOARD_REPRESENTATIVE, granted_at=clock_now()
    )

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


def test_posted_own_text_after_422_is_not_treated_as_last_prefill(live_server):
    from playwright.sync_api import sync_playwright

    pastor, req = _make_awaiting_request_and_pastor()
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

            # Pick a reason (applies its suggested prefill), then EDIT the message, and
            # submit without a route -- this 422s and re-renders with her edited text posted
            # back verbatim (UX M7), not the suggested prefill.
            page.check("#decline-reasons input[value=couldnt_confirm]")
            page.fill("#id_message", "MY OWN CAREFULLY WRITTEN WORDS.")
            # Bypass the browser's own native "pick a route" validation (the radios are
            # `required`) so the click actually reaches the server -- the point here is the
            # server-side 422 re-render, not the client-side HTML5 validation UX.
            page.eval_on_selector("#decline-form", "form => { form.noValidate = true; }")
            page.click("button[type=submit]")
            page.wait_for_selector("text=Choose whether this is your decision or the Board's.")
            assert page.input_value("#id_message") == "MY OWN CAREFULLY WRITTEN WORDS."

            # Changing the reason again must ask before overwriting her words -- it must NOT
            # silently replace them (which would happen if the reload treated her own posted
            # text as if it were already the reason's own suggested prefill).
            page.check("#decline-reasons input[value=another_reason]")
            replace_row = page.locator("#reason-replace-row")
            assert replace_row.is_visible(), (
                "expected the 'Replace your message?' prompt, not a silent overwrite"
            )
            assert page.input_value("#id_message") == "MY OWN CAREFULLY WRITTEN WORDS."
        finally:
            browser.close()
