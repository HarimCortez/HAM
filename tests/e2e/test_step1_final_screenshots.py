"""Final visual QA screenshots for the Fix C pass (nav caps, Admin/More, audit filters,
impersonation banner partial, public layout). Opt-in (`HAM_SCREENSHOTS=1`), mirroring
`tests/e2e/test_shell_screenshots.py`; sign-in screens are captured live through the browser
(same technique as `tests/e2e/test_smoke.py`) since they must render signed-out.

    HAM_SCREENSHOTS=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \\
        DATABASE_URL=... DJANGO_SETTINGS_MODULE=config.settings.test \\
        pytest tests/e2e/test_step1_final_screenshots.py -p no:randomly
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HAM_SCREENSHOTS") != "1",
    reason="opt-in visual QA pass; set HAM_SCREENSHOTS=1 to run (see module docstring)",
)
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "ux" / "screenshots" / "step1-final"
VIEWPORTS = {"390": (390, 844), "768": (768, 1024), "1280": (1280, 900)}

DIRECTOR_TOTP_SECRET = "MZXW6YTBOI5FCTLTMZXW6YTBOI5FCTLT"


def _session_cookie(live_server, django_user, *, extra_session=None):
    from django.conf import settings
    from django.test import Client

    client = Client()
    client.force_login(django_user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    for key, value in (extra_session or {}).items():
        session[key] = value
    session.save()
    return {
        "name": settings.SESSION_COOKIE_NAME,
        "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
        "url": live_server.url,
    }


def _latest_code_for(email: str) -> str:
    from django.core import mail

    from ham.jobs import run_due_jobs_now

    run_due_jobs_now()
    matches = [m for m in mail.outbox if m.to == [email]]
    assert matches, f"no email sent to {email!r}"
    body = str(matches[-1].body)
    match = re.search(r"(\d{3})\D?(\d{3})", body)
    assert match, f"couldn't find a 6-digit code in: {body!r}"
    return match.group(1) + match.group(2)


@pytest.mark.django_db(transaction=True)
def test_final_screenshots(live_server):
    from playwright.sync_api import sync_playwright

    from ham.authz import roles
    from ham.identity.crypto import encrypt
    from ham.identity.mfa import regenerate_recovery_codes
    from ham.identity.models import (
        ImpersonationSession,
        RoleAssignment,
        SharedIdentityProfile,
        TOTPDevice,
        User,
    )
    from ham.platform.clock import now as clock_now

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = clock_now()

    admin = User.objects.create_user(email="nadia@example.org")
    SharedIdentityProfile.objects.create(user=admin, full_name="Nadia Pierre")
    RoleAssignment.objects.create(user=admin, role=roles.ADMINISTRATOR, granted_at=now)

    volunteer = User.objects.create_user(email="kevin@example.org")
    SharedIdentityProfile.objects.create(user=volunteer, full_name="Kevin Thompson")
    RoleAssignment.objects.create(user=volunteer, role=roles.VOLUNTEER, granted_at=now)

    # One Director-role user *per viewport*, so a same-email sign-in cooldown/challenge reuse
    # across widths (run back-to-back below) never collides with an already-used code.
    for width_label in VIEWPORTS:
        director = User.objects.create_user(email=f"marcus-{width_label}@example.org")
        SharedIdentityProfile.objects.create(user=director, full_name="Marcus Bell")
        RoleAssignment.objects.create(user=director, role=roles.HAM_DIRECTOR, granted_at=now)
        TOTPDevice.objects.create(
            user=director,
            secret_encrypted=encrypt(DIRECTOR_TOTP_SECRET),
            created_at=now,
            confirmed_at=now,
        )
        regenerate_recovery_codes(director)

    impersonation = ImpersonationSession.objects.create(
        admin_user_id=admin.id,
        target_user_id=volunteer.id,
        reason="visual QA screenshot",
        started_at=now,
        last_activity_at=now,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def new_page(width, height, *, cookie=None):
            context = browser.new_context(viewport={"width": width, "height": height})
            if cookie:
                context.add_cookies(
                    [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
                )
            return context.new_page()

        def shoot(name, width_label, dims, path, *, cookie=None):
            width, height = dims
            page = new_page(width, height, cookie=cookie)
            page.goto(f"{live_server.url}{path}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT_DIR / f"{name}-{width_label}.png"), full_page=True)
            page.context.close()

        # --- Signed-in shell screens (force_login cookie, all 3 widths) ---------------------
        signed_in_shots = [
            ("home-volunteer", "/", volunteer),
            ("home-admin", "/", admin),
            ("admin-index", "/admin", admin),
            ("more", "/more", admin),
            ("users-list", "/admin/users", admin),
            ("user-detail", f"/admin/users/{volunteer.id}", admin),
            ("audit-log", "/audit", admin),
        ]
        for width_label, dims in VIEWPORTS.items():
            for name, path, persona in signed_in_shots:
                cookie = _session_cookie(live_server, persona)
                shoot(name, width_label, dims, path, cookie=cookie)

        # --- Impersonation banner + not-found while signed in --------------------------------
        for width_label, dims in VIEWPORTS.items():
            imp_cookie = _session_cookie(
                live_server, admin, extra_session={"ham_impersonation_id": str(impersonation.id)}
            )
            shoot("impersonation-banner", width_label, dims, "/", cookie=imp_cookie)
            shoot(
                "not-found-signed-in",
                width_label,
                dims,
                "/this-route-does-not-exist",
                cookie=imp_cookie,
            )

        # --- Sign-in screens, driven live (signed out) ---------------------------------------
        for width_label, dims in VIEWPORTS.items():
            width, height = dims

            page = new_page(width, height)
            page.goto(f"{live_server.url}/sign-in")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT_DIR / f"sign-in-{width_label}.png"), full_page=True)
            page.fill("#id_email", "kevin@example.org")
            page.click("button[type=submit]")
            page.wait_for_load_state("networkidle")
            page.screenshot(
                path=str(OUT_DIR / f"check-your-email-{width_label}.png"), full_page=True
            )
            page.context.close()

            # Two-step challenge: Marcus (Director, TOTP-enrolled). A distinct email per
            # viewport avoids the sign-in cooldown reusing an already-consumed code.
            director_email = f"marcus-{width_label}@example.org"
            page = new_page(width, height)
            page.goto(f"{live_server.url}/sign-in")
            page.fill("#id_email", director_email)
            page.click("button[type=submit]")
            code = _latest_code_for(director_email)
            page.fill("#id_code", code)
            page.click("button[type=submit]")
            page.wait_for_load_state("networkidle")
            assert "/sign-in/mfa" in page.url, page.url
            page.screenshot(
                path=str(OUT_DIR / f"two-step-challenge-{width_label}.png"), full_page=True
            )

            from ham.identity.totp import current_code

            page.fill("#id_code", current_code(DIRECTOR_TOTP_SECRET))
            page.click("button[type=submit]")
            page.wait_for_load_state("networkidle")
            assert page.url == f"{live_server.url}/", page.url

            # Step-up: triggered by exporting the audit log (auth-and-access.md §2.7).
            page.goto(f"{live_server.url}/audit")
            page.click("button:has-text('Export')")
            page.wait_for_load_state("networkidle")
            if "/step-up" in page.url:
                page.screenshot(path=str(OUT_DIR / f"step-up-{width_label}.png"), full_page=True)
            page.context.close()

        browser.close()

    assert (OUT_DIR / "home-volunteer-390.png").exists()
    assert (OUT_DIR / "sign-in-390.png").exists()
