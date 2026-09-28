"""S2.8 visual QA screenshots (opt-in, `HAM_SCREENSHOTS=1`), mirroring
`tests/e2e/test_step1_final_screenshots.py`. Seeded fake data only.

    HAM_SCREENSHOTS=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \\
        DATABASE_URL=... DJANGO_SETTINGS_MODULE=config.settings.test \\
        pytest tests/e2e/test_step2_leadership_screenshots.py -p no:randomly
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

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "ux" / "screenshots" / "step2"
VIEWPORTS = {"390": (390, 844), "1280": (1280, 900)}


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
def test_leadership_screenshots(live_server):
    from playwright.sync_api import sync_playwright

    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now
    from ham.requests.services import complete_intake_checks, submit_request
    from ham.requests.states import RequestStatus
    from tests.requests.conftest import make_payload, no_email_payload

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    director = User.objects.create_user(email="marcus-shots@example.org")
    SharedIdentityProfile.objects.create(user=director, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=director, role=roles.HAM_DIRECTOR, granted_at=clock_now())

    from ham.authz.context import RequesterContext, SystemContext

    for _ in range(3):
        req = submit_request(
            RequesterContext(request_id=None),
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(full_name=f"Fictional Requester {uuid.uuid4().hex[:6]}"),
        )
        complete_intake_checks(SystemContext(), request_id=req.id)
    phone_check_req = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=None,
        payload=no_email_payload(full_name="Ruth Hall", phone="+13055550177"),
    )
    selected = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(full_name="Doris Pennington", email="doris@example.org"),
    )
    selected = complete_intake_checks(SystemContext(), request_id=selected.id)
    assert selected.status == RequestStatus.AWAITING_APPROVAL.value

    cookie = _session_cookie(live_server, director)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def shoot(name, width_label, dims, path):
            width, height = dims
            context = browser.new_context(viewport={"width": width, "height": height})
            context.add_cookies(
                [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
            )
            page = context.new_page()
            page.goto(f"{live_server.url}{path}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT_DIR / f"{name}-{width_label}.png"), full_page=True)
            context.close()

        for width_label, dims in VIEWPORTS.items():
            shoot("leader-requests-list", width_label, dims, "/requests?tab=all")
        shoot(
            "leader-request-detail",
            "1280",
            VIEWPORTS["1280"],
            f"/requests/{selected.id}",
        )
        shoot(
            "leader-phone-check-sheet",
            "390",
            VIEWPORTS["390"],
            f"/requests/{phone_check_req.id}/phone-check",
        )
        shoot("leader-home-attention", "1280", VIEWPORTS["1280"], "/")

        browser.close()

    assert (OUT_DIR / "leader-requests-list-390.png").exists()
    assert (OUT_DIR / "leader-requests-list-1280.png").exists()
    assert (OUT_DIR / "leader-request-detail-1280.png").exists()
    assert (OUT_DIR / "leader-home-attention-1280.png").exists()

    # This test commits real rows (`transaction=True`, no per-test rollback) and calls
    # `complete_intake_checks` directly rather than letting `submit_request`'s deferred job
    # run. The shared `_sweep_leaked_procrastinate_todo_jobs` autouse fixture in
    # `tests/e2e/conftest.py` drains any leftover "todo" job after this test so it can't leak
    # into a later, unrelated test.
