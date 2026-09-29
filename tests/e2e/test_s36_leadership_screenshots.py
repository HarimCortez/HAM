"""S3.6 visual QA screenshots (opt-in, `HAM_SCREENSHOTS=1`), mirroring
`tests/e2e/test_step2_leadership_screenshots.py`. Seeded fake data only.

    HAM_SCREENSHOTS=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \\
        DATABASE_URL=... DJANGO_SETTINGS_MODULE=config.settings.test \\
        pytest tests/e2e/test_s36_leadership_screenshots.py -p no:randomly
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HAM_SCREENSHOTS") != "1",
    reason="opt-in visual QA pass; set HAM_SCREENSHOTS=1 to run (see module docstring)",
)
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "ux" / "screenshots" / "step3"


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


@pytest.mark.django_db(transaction=True)
def test_leadership_approvals_screenshots(live_server):
    from playwright.sync_api import sync_playwright

    from ham.authz import roles
    from ham.authz.context import RequesterContext, SystemContext
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now
    from ham.requests.services import complete_intake_checks, submit_request
    from ham.requests.services_decisions import approve_request
    from tests.requests.conftest import make_payload

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pastor = User.objects.create_user(email="ruth-shots@example.org")
    SharedIdentityProfile.objects.create(user=pastor, full_name="Ruth Alvarez")
    RoleAssignment.objects.create(user=pastor, role=roles.PASTOR, granted_at=clock_now())

    def _awaiting(**overrides):
        req = submit_request(
            RequesterContext(request_id=None),
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(
                full_name=f"Fictional Requester {uuid.uuid4().hex[:6]}",
                description="Water comes through the bedroom ceiling when it rains "
                "(fictional seed data).",
                **overrides,
            ),
        )
        complete_intake_checks(SystemContext(), request_id=req.id)
        req.refresh_from_db()
        return req

    req = _awaiting()
    for _ in range(3):
        _awaiting()

    from ham.authz.context import ActorContext

    pastor_ctx = ActorContext(
        user_id=pastor.id,
        real_user_id=None,
        roles=frozenset({roles.PASTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    undo_req = _awaiting()
    approve_request(pastor_ctx, request_id=undo_req.id, route="pastoral")

    cookie = _session_cookie(live_server, pastor)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for width, name in ((390, "390"), (1280, "1280")):
                context = browser.new_context(viewport={"width": width, "height": 900})
                context.add_cookies(
                    [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
                )
                page = context.new_page()

                page.goto(f"{live_server.url}/requests/{req.id}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(OUT_DIR / f"leader-decision-{name}.png"), full_page=True)

                page.goto(f"{live_server.url}/requests/{req.id}/reject")
                page.wait_for_load_state("networkidle")
                page.check("input[name=reason_code][value=family_or_others_can_help]")
                page.screenshot(
                    path=str(OUT_DIR / f"leader-decline-sheet-{name}.png"), full_page=True
                )
                context.close()

            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()

            page.goto(f"{live_server.url}/requests/{undo_req.id}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT_DIR / "leader-undo-window-1280.png"), full_page=True)

            page.goto(f"{live_server.url}/requests")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT_DIR / "leader-requests-tabs-1280.png"), full_page=True)

            page.goto(f"{live_server.url}/")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT_DIR / "leader-home-cards-1280.png"), full_page=True)
            context.close()
        finally:
            browser.close()
