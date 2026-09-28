"""Playwright smoke suite (foundation.md §9.7, build-order step 1 task list item 2).

Runs in the normal `pytest` run (no opt-in marker): it needs the Playwright Python package
(already a `[dev]` extra) and the Chromium build preinstalled at `/opt/pw-browsers` (already on
this box; CI must install it the same way, e.g. `playwright install --with-deps chromium` or a
cached equivalent — do **not** run `playwright install` here, per the task instructions). A
single Chromium instance drives every scenario below sequentially (~15-30s total) to keep this
well under the ~60s budget; if it ever becomes flaky or slow in CI, move it back behind a
marker (e.g. `@pytest.mark.e2e`) and document the opt-in command here, mirroring
`tests/e2e/test_shell_screenshots.py`'s `HAM_SCREENSHOTS=1` pattern.

Standalone invocation:

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers DATABASE_URL=... \\
        pytest tests/e2e/test_smoke.py -p no:randomly

Covers (one persona/flow each, real HTTP through a browser -- no `force_login`):
  * a Volunteer (Kevin) signs in with the code read from the captured mailbox and sees the
    Volunteer nav (Home/Inbox/Me only);
  * the Director (Marcus) signs in with a seeded TOTP secret and sees the Audit log destination;
  * audit export requires step-up (redirects to `/step-up`, then succeeds after a TOTP code);
  * the Administrator (Nadia) impersonates Kevin: the impersonation banner appears, and a
    blocked action (regenerating recovery codes while impersonating, §59) is refused;
  * the offline page renders.
Each at both 390px and 1280px (foundation.md §9.7 "Viewports 390/768/1280" — 768 is covered by
the opt-in screenshot pass; this smoke suite exercises the two extremes that matter for
layout-breaking regressions).
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

# Playwright's sync API runs the test body inside a greenlet on a thread that also drives an
# asyncio event loop internally; Django's ORM sees "a loop is running in this thread" and
# refuses DB access unless this is set (a documented Playwright/Django interaction, not a
# workaround for a HAM bug -- see Playwright's own Django integration notes).
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

VIEWPORTS = {"mobile": (390, 844), "desktop": (1280, 900)}

# Same fixed dev-only secret `manage.py seed_dev` uses for marcus@example.org (HAM Director +
# Volunteer), so this test doesn't have to shell out to `seed_dev` (which also refuses non-dev
# environments) just to get one TOTP-enrolled persona.
DIRECTOR_TOTP_SECRET = "MZXW6YTBOI5FCTLTMZXW6YTBOI5FCTLT"
ADMIN_TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def _make_personas():
    from ham.authz import roles
    from ham.identity.crypto import encrypt
    from ham.identity.mfa import regenerate_recovery_codes
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, TOTPDevice, User
    from ham.platform.clock import now as clock_now

    now = clock_now()

    kevin = User.objects.create_user(email="kevin@example.org")
    kevin.first_sign_in_at = now
    kevin.save()
    SharedIdentityProfile.objects.create(user=kevin, full_name="Kevin Thompson")
    RoleAssignment.objects.create(user=kevin, role=roles.VOLUNTEER, granted_at=now)

    marcus = User.objects.create_user(email="marcus@example.org")
    marcus.first_sign_in_at = now
    marcus.save()
    SharedIdentityProfile.objects.create(user=marcus, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=marcus, role=roles.HAM_DIRECTOR, granted_at=now)
    RoleAssignment.objects.create(user=marcus, role=roles.VOLUNTEER, granted_at=now)
    TOTPDevice.objects.create(
        user=marcus,
        secret_encrypted=encrypt(DIRECTOR_TOTP_SECRET),
        created_at=now,
        confirmed_at=now,
    )
    regenerate_recovery_codes(marcus)

    nadia = User.objects.create_user(email="nadia@example.org")
    nadia.first_sign_in_at = now
    nadia.save()
    SharedIdentityProfile.objects.create(user=nadia, full_name="Nadia Pierre")
    RoleAssignment.objects.create(user=nadia, role=roles.ADMINISTRATOR, granted_at=now)
    TOTPDevice.objects.create(
        user=nadia, secret_encrypted=encrypt(ADMIN_TOTP_SECRET), created_at=now, confirmed_at=now
    )
    regenerate_recovery_codes(nadia)

    return kevin, marcus, nadia


def _latest_code_for(email: str) -> str:
    """Reads the just-sent 6-digit sign-in code out of the captured mailbox (locmem backend),
    after running the deferred `send_transactional_email` job (it doesn't send synchronously —
    `ham.jobs.run_due_jobs_now` per foundation.md §9.8's job-runner fixture)."""
    from django.core import mail

    from ham.jobs import run_due_jobs_now

    run_due_jobs_now()
    matches = [m for m in mail.outbox if m.to == [email]]
    assert matches, f"no email sent to {email!r}; outbox={[m.to for m in mail.outbox]}"
    body = str(matches[-1].body)
    match = re.search(r"(\d{3})\D?(\d{3})", body)
    assert match, f"couldn't find a 6-digit code in: {body!r}"
    return match.group(1) + match.group(2)


def _sign_in_with_code(page, live_server, *, email: str) -> None:
    page.goto(f"{live_server.url}/sign-in")
    page.fill("#id_email", email)
    page.click("button[type=submit]")
    assert page.url.endswith("/sign-in/code"), page.url
    code = _latest_code_for(email)
    page.fill("#id_code", code)
    page.click("button[type=submit]")


def _totp_code(secret: str) -> str:
    from ham.identity.totp import current_code

    return current_code(secret)


def _wait_for_a_fresh_totp_step() -> None:
    """Security review H2 (TOTP replay protection): a code is only ever accepted once per
    device. This smoke test authenticates with the *same* seeded secret twice in quick
    succession (sign-in MFA, then the audit-export step-up) -- exactly what a real person
    might also do, entering whatever their app currently shows for two different actions a
    few seconds apart. A real authenticator app would have moved on to a new code by the time
    they get to the second screen; this test has to wait for the same 30-second boundary
    instead of pretending time passed."""
    import time

    from ham.identity.totp import current_step

    step = current_step()
    while current_step() == step:
        time.sleep(1)


def _visible_nav_labels(page, *, container: str) -> set[str]:
    links = page.locator(f"{container} .nav__link")
    return {links.nth(i).inner_text().strip() for i in range(links.count())}


@pytest.mark.parametrize("viewport_name", ["mobile", "desktop"])
def test_smoke_suite(live_server, viewport_name):
    from playwright.sync_api import sync_playwright

    kevin, marcus, nadia = _make_personas()
    width, height = VIEWPORTS[viewport_name]
    nav_container = ".nav--bottom" if viewport_name == "mobile" else ".nav--sidebar"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()

            # --- 1. Volunteer signs in with the emailed code, sees the Volunteer nav --------
            _sign_in_with_code(page, live_server, email="kevin@example.org")
            assert page.url == f"{live_server.url}/", page.url
            nav_labels = _visible_nav_labels(page, container=nav_container)
            assert nav_labels == {"Home", "Inbox", "Me"}, nav_labels
            context.close()

            # --- 2. Director signs in with a seeded TOTP, sees Audit log -------------------
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            _sign_in_with_code(page, live_server, email="marcus@example.org")
            assert "/sign-in/mfa" in page.url, page.url
            page.fill("#id_code", _totp_code(DIRECTOR_TOTP_SECRET))
            page.click("button[type=submit]")
            assert page.url == f"{live_server.url}/", page.url
            nav_labels = _visible_nav_labels(page, container=nav_container)
            if viewport_name == "mobile":
                # navigation.md §3.1/Q-091: the Director's bottom nav is capped at 5 items and
                # ends in **More** (not a direct Audit log tab) — Audit log lives on the More
                # page (tests/web/test_admin_index_and_more.py covers that page's contents).
                # S2.8: "Requests" is now a direct tab too (tests/authz/test_nav_mobile.py).
                assert nav_labels == {"Home", "Requests", "Inbox", "More"}, nav_labels
            else:
                assert "Audit log" in nav_labels, nav_labels

            # --- 3. Audit export requires step-up -------------------------------------------
            page.goto(f"{live_server.url}/audit")
            page.click("button:has-text('Export')")
            assert "/step-up" in page.url, page.url
            _wait_for_a_fresh_totp_step()
            page.fill("#id_code", _totp_code(DIRECTOR_TOTP_SECRET))
            # FIXED (security review UX C1 continuation, tests/web/test_audit_export_stepup_
            # redirect_bug.py): `views_audit.audit_export`'s `StepUpRequired` handler now
            # redirects to a GET-only `audit_export_download` view (the stashed filters are
            # replayed there) instead of the POST-only `/audit/export` URL itself, so
            # submitting the step-up form completes the download directly -- no second click
            # on "Export" needed.
            with page.expect_download():
                page.click("button[type=submit]")
            context.close()

            # --- 4. Admin impersonates Kevin: banner shows; a blocked action is refused -----
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            _sign_in_with_code(page, live_server, email="nadia@example.org")
            assert "/sign-in/mfa" in page.url, page.url
            page.fill("#id_code", _totp_code(ADMIN_TOTP_SECRET))
            page.click("button[type=submit]")
            assert page.url == f"{live_server.url}/", page.url

            page.goto(f"{live_server.url}/admin/users/{kevin.id}")
            page.click("text=Troubleshoot as")
            page.fill("#id_reason", "smoke test troubleshooting")
            page.click("button:has-text('Start troubleshooting')")
            # Step-up required (first time this session) -> TOTP -> completes directly.
            # FIXED (security review UX C1 continuation): `admin_impersonate` stashes the
            # reason across the step-up round trip (`ham.identity.web.handle_command_errors`),
            # so entering the code finishes starting the session immediately -- no need to
            # retype the reason and click "Start troubleshooting" a second time.
            if "/step-up" in page.url:
                _wait_for_a_fresh_totp_step()
                page.fill("#id_code", _totp_code(ADMIN_TOTP_SECRET))
                page.click("button[type=submit]")
            assert page.url == f"{live_server.url}/", page.url
            assert page.locator(".impersonation-banner").is_visible()

            # A blocked-while-impersonating action (§59, `me.security.manage`): even the GET
            # screen for it is refused with the neutral "not available" page (navigation.md
            # §6) rather than a 500 or a silent no-op, because the route guard denies any
            # `blocked_while_impersonating` action outright (`ham/authz/guard.py`), before the
            # view (and its own `ImpersonationBlocked` handling) ever runs.
            page.goto(f"{live_server.url}/me/security")
            assert "isn't available to your account" in page.content()
            context.close()

            # --- 5. Offline page renders -----------------------------------------------------
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            page.goto(f"{live_server.url}/offline")
            assert "You're offline" in page.content()
            context.close()
        finally:
            browser.close()
