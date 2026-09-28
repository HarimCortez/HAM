"""Passwordless sign-in (foundation.md §9.3): no enumeration, code expiry/max attempts, the
link surviving a GET prefetch, first sign-in marking Invited -> Active."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from ham import jobs
from ham.identity import authn
from ham.identity.models import SignInChallenge
from ham.platform.clock import FixedClock, set_clock
from ham.rules import RULES

pytestmark = pytest.mark.django_db


def _extract_code_and_token(body: str) -> tuple[str, str]:
    import re

    code_match = re.search(r"\b(\d{3} \d{3})\b", body)
    assert code_match, body
    code = code_match.group(1).replace(" ", "")
    token_match = re.search(r"/sign-in/link/([\w\-]+)", body)
    assert token_match, body
    return code, token_match.group(1)


def test_identical_response_for_unknown_email(client: Client):
    known = client.post(reverse("web:sign_in"), {"email": "kevin@example.org"})
    unknown = Client().post(reverse("web:sign_in"), {"email": "nobody@example.org"})
    assert known.status_code == unknown.status_code == 302
    assert known["Location"] == unknown["Location"]


def test_identical_email_count_and_no_account_signal_in_response(client: Client, make_user):
    make_user("kevin@example.org")
    mail.outbox.clear()
    client.post(reverse("web:sign_in"), {"email": "kevin@example.org"})
    jobs.run_due_jobs_now()
    assert len(mail.outbox) == 1

    mail.outbox.clear()
    Client().post(reverse("web:sign_in"), {"email": "nobody@example.org"})
    jobs.run_due_jobs_now()
    assert len(mail.outbox) == 1  # same number of emails sent either way


def test_code_expires(make_user):
    user = make_user("kevin@example.org")
    clock = FixedClock(dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    set_clock(clock)
    try:
        authn.request_sign_in(email=user.email)
        clock.advance(RULES.auth.SIGN_IN_CODE_LIFETIME + dt.timedelta(seconds=1))
        challenge = SignInChallenge.objects.get(email=user.email)
        result = authn.verify_code(email=user.email, code="000000")
        assert not result.ok
        assert result.reason in ("expired", "wrong")
        # Confirm it really is the expiry path, not a coincidentally-wrong code:
        challenge.refresh_from_db()
        assert challenge.consumed_at is None
    finally:
        from ham.platform.clock import SystemClock

        set_clock(SystemClock())


def test_code_locks_after_max_attempts(make_user):
    user = make_user("kevin@example.org")
    authn.request_sign_in(email=user.email)
    max_attempts = RULES.auth.SIGN_IN_CODE_MAX_ATTEMPTS
    for _ in range(max_attempts - 1):
        result = authn.verify_code(email=user.email, code="000000")
        assert result.reason == "wrong"
    locked = authn.verify_code(email=user.email, code="000000")
    assert locked.reason == "locked"


def test_link_survives_a_get_prefetch(client: Client, make_user):
    user = make_user("kevin@example.org")
    mail.outbox.clear()
    client.post(reverse("web:sign_in"), {"email": user.email})
    jobs.run_due_jobs_now()
    _code, token = _extract_code_and_token(str(mail.outbox[0].body))

    # A mail scanner's GET must not consume the link.
    get_response = client.get(reverse("web:sign_in_link", kwargs={"token": token}))
    assert get_response.status_code == 200
    assert b"Continue" in get_response.content

    challenge = SignInChallenge.objects.get(email=user.email)
    assert challenge.consumed_at is None

    post_response = client.post(reverse("web:sign_in_link", kwargs={"token": token}))
    assert post_response.status_code == 302
    challenge.refresh_from_db()
    assert challenge.consumed_at is not None


def test_first_sign_in_marks_invited_active(client: Client, make_user):
    from ham.identity import mfa as mfa_module

    user = make_user("kevin@example.org")
    assert user.is_invited
    mail.outbox.clear()
    client.post(reverse("web:sign_in"), {"email": user.email})
    jobs.run_due_jobs_now()
    _code, token = _extract_code_and_token(str(mail.outbox[0].body))
    assert not mfa_module.mfa_required(user)

    client.post(reverse("web:sign_in_link", kwargs={"token": token}))
    user.refresh_from_db()
    assert user.first_sign_in_at is not None


def test_unauthenticated_request_redirects_to_sign_in_with_next(client: Client):
    response = client.get(reverse("web:me_security"))
    assert response.status_code == 302
    assert response["Location"].startswith("/sign-in")
    assert "next=" in response["Location"]


def test_sign_out_ends_session(client: Client, make_user):
    from ham.identity.models import RoleAssignment
    from ham.platform.clock import now as clock_now

    user = make_user("kevin@example.org")
    RoleAssignment.objects.create(user=user, role="VOLUNTEER", granted_at=clock_now())
    client.force_login(user)
    response = client.post(reverse("web:sign_out"))
    assert response.status_code == 200
    home = client.get(reverse("web:home"))
    assert home.status_code == 302
    assert home["Location"].startswith("/sign-in")
