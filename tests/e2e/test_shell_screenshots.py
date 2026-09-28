"""Visual QA screenshots for the S5 screens (build-order step 1 task list item 9).

Not part of the normal CI suite (skipped unless `HAM_SCREENSHOTS=1`): it needs the
Playwright Python package and the Chromium build preinstalled at `/opt/pw-browsers`, and
takes noticeably longer than the rest of the unit/integration suite. Run with:

    HAM_SCREENSHOTS=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
        DATABASE_URL=... DJANGO_SETTINGS_MODULE=config.settings.test \
        pytest tests/e2e/test_shell_screenshots.py -p no:randomly

Logs in with `django.test.Client.force_login`'s session cookie injected into a real
Chromium page (no sign-in screens exist in this worktree yet — S3b builds those).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HAM_SCREENSHOTS") != "1",
    reason="opt-in visual QA pass; set HAM_SCREENSHOTS=1 to run (see module docstring)",
)

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "ux" / "screenshots" / "step1-screens"
VIEWPORTS = {"390": (390, 844), "768": (768, 1024), "1280": (1280, 900)}


def _login_cookie(live_server, django_user):
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
def test_screenshots(live_server):
    from playwright.sync_api import sync_playwright

    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    admin = User.objects.create_user(email="nadia@example.org")
    SharedIdentityProfile.objects.create(user=admin, full_name="Nadia Pierre")
    RoleAssignment.objects.create(user=admin, role="ADMINISTRATOR", granted_at=now())

    volunteer = User.objects.create_user(email="kevin@example.org")
    SharedIdentityProfile.objects.create(user=volunteer, full_name="Kevin Thompson")
    RoleAssignment.objects.create(user=volunteer, role="VOLUNTEER", granted_at=now())

    cookie = _login_cookie(live_server, admin)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def new_page(width, height):
            context = browser.new_context(viewport={"width": width, "height": height})
            context.add_cookies(
                [
                    {
                        "name": cookie["name"],
                        "value": cookie["value"],
                        "url": cookie["url"],
                    }
                ]
            )
            return context.new_page()

        shots = [
            ("home", "/"),
            ("me", "/me"),
            ("users-list", "/admin/users"),
            ("user-detail", f"/admin/users/{volunteer.id}"),
            ("audit-log", "/audit"),
        ]
        for width_label, (width, height) in VIEWPORTS.items():
            for name, path in shots:
                if width_label == "768" and name not in ("home",):
                    continue  # task list: "plus 768 for Home" only.
                page = new_page(width, height)
                page.goto(f"{live_server.url}{path}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(OUT_DIR / f"{name}-{width_label}.png"), full_page=True)
                page.context.close()

        browser.close()

    assert (OUT_DIR / "home-390.png").exists()
