"""S2.8 Playwright e2e: the phone-check verify flow (L9) and the close-request flow (L10),
each at 390px and 1280px (wave brief "Playwright e2e for phone-check verify and close at 390
and 1280"). Uses a signed-in session cookie (like `tests/e2e/test_step1_final_screenshots.py`)
rather than a live sign-in, since the sign-in flow itself is covered by `test_smoke.py`.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

pytestmark = pytest.mark.django_db(transaction=True)

VIEWPORTS = {"mobile": (390, 844), "desktop": (1280, 900)}


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


def _make_director():
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now

    user = User.objects.create_user(email="marcus-e2e@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=user, role=roles.HAM_DIRECTOR, granted_at=clock_now())
    return user


def _make_no_email_request():
    import uuid

    from ham.authz.context import RequesterContext
    from ham.requests.services import submit_request
    from tests.requests.conftest import no_email_payload

    return submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=None,
        payload=no_email_payload(full_name="Ruth Hall", phone="+13055550177"),
    )


def _make_awaiting_request():
    import uuid

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


def test_phone_check_verify_and_close_flows(live_server):
    from playwright.sync_api import sync_playwright

    from ham.requests.states import RequestStatus

    director = _make_director()
    cookie = _session_cookie(live_server, director)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for width_label, (width, height) in VIEWPORTS.items():
                # --- L9: phone check verify -----------------------------------------------
                phone_req = _make_no_email_request()
                context = browser.new_context(viewport={"width": width, "height": height})
                context.add_cookies(
                    [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
                )
                page = context.new_page()
                page.goto(f"{live_server.url}/requests/{phone_req.id}/phone-check")
                page.wait_for_load_state("networkidle")
                assert "Record a phone check" in page.content()
                page.get_by_label("I spoke with").click()
                page.get_by_role("button", name="Verified by phone call").click()
                page.wait_for_load_state("networkidle")
                phone_req.refresh_from_db()
                assert phone_req.status == RequestStatus.SUBMITTED.value, (
                    f"{width_label}: phone check didn't verify"
                )
                context.close()

                # --- L10: close as spam -----------------------------------------------------
                close_req = _make_awaiting_request()
                context = browser.new_context(viewport={"width": width, "height": height})
                context.add_cookies(
                    [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
                )
                page = context.new_page()
                page.goto(f"{live_server.url}/requests/{close_req.id}/close")
                page.wait_for_load_state("networkidle")
                assert "Why are you closing" in page.content()
                page.get_by_label("This is spam or a test").check()
                page.get_by_role("button", name="Close request").click()
                page.wait_for_load_state("networkidle")
                close_req.refresh_from_db()
                assert close_req.status == RequestStatus.CANCELLED.value, (
                    f"{width_label}: close didn't cancel"
                )
                assert close_req.cancel_reason_code == "spam"
                context.close()
        finally:
            browser.close()

    # Both flows defer a `system.request.complete_intake_checks` job (verify_by_phone for the
    # phone-check request; submit_request for `_make_awaiting_request`'s fixture, which calls
    # `complete_intake_checks` itself rather than waiting for the deferred job). This test
    # commits real rows (`live_server`, `transaction=True`, no per-test rollback), so an
    # undrained "todo" job would otherwise sit in the shared queue for the rest of the run and
    # get picked up by the next test that calls `run_due_jobs_now()`, refusing on a request
    # that has already moved on (states.py's `WRONG_STATE`) and failing an unrelated test. A
    # raw sweep (not `run_due_jobs_now()`, which would try to *execute* them, including any
    # already-stale from an earlier interrupted run) is the safe cleanup here.
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM procrastinate_jobs WHERE status = 'todo'")
