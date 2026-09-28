"""Boundary tests for the sign-in limits that run on proposed defaults (owner, 2026-09-28):
Q-070 resend cooldown and per-address hourly limit, Q-072 wrong authenticator codes.

Values are read from ham.rules so the tests follow the rules module; the pinned numbers
themselves are asserted in tests/rules/test_rules_values.py.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse

from ham.authz import roles
from ham.identity import authn, mfa
from ham.identity.models import RoleAssignment
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now
from ham.rules import RULES
from ham.web.auth_views import SESSION_MFA_ATTEMPTS, SESSION_PENDING_MFA_USER_ID

pytestmark = pytest.mark.django_db

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)
SECOND = dt.timedelta(seconds=1)


@pytest.fixture
def clock() -> FixedClock:
    c = FixedClock(T0)
    set_clock(c)
    return c  # tests/conftest.py restores the system clock afterwards


# Q-070: resend cooldown (30 s proposed default).
@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (RULES.auth.SIGN_IN_RESEND_COOLDOWN - SECOND, "cooldown"),
        (RULES.auth.SIGN_IN_RESEND_COOLDOWN, "sent"),
        (RULES.auth.SIGN_IN_RESEND_COOLDOWN + SECOND, "sent"),
    ],
    ids=["one-second-early", "exactly-at-cooldown", "after-cooldown"],
)
def test_resend_cooldown_boundary(clock: FixedClock, after: dt.timedelta, expected: str):
    email = "kevin@example.org"
    assert authn.request_sign_in(email=email).status == "sent"
    clock.advance(after)
    result = authn.request_sign_in(email=email)
    assert result.status == expected
    if expected == "cooldown":
        assert result.retry_at == T0 + RULES.auth.SIGN_IN_RESEND_COOLDOWN


def _send_limit(clock: FixedClock, email: str) -> None:
    """Send exactly the hourly limit, each one just past the cooldown."""
    for i in range(RULES.auth.SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR):
        if i:
            clock.advance(RULES.auth.SIGN_IN_RESEND_COOLDOWN)
        assert authn.request_sign_in(email=email).status == "sent"


def test_hourly_limit_allows_exactly_the_limit_then_refuses(clock: FixedClock):
    email = "kevin@example.org"
    _send_limit(clock, email)
    clock.advance(RULES.auth.SIGN_IN_RESEND_COOLDOWN)
    result = authn.request_sign_in(email=email)
    assert result.status == "rate_limited"
    # Another address is unaffected: the limit is per address.
    assert authn.request_sign_in(email="ruth@example.org").status == "sent"


@pytest.mark.parametrize(
    ("since_first", "expected"),
    [
        (dt.timedelta(hours=1) - SECOND, "rate_limited"),
        (dt.timedelta(hours=1), "rate_limited"),  # first email is still inside the hour
        (dt.timedelta(hours=1) + SECOND, "sent"),  # first email has left the rolling hour
    ],
    ids=["59m59s", "exactly-1h", "1h+1s"],
)
def test_hourly_limit_is_a_rolling_hour(clock: FixedClock, since_first: dt.timedelta, expected):
    email = "kevin@example.org"
    _send_limit(clock, email)
    clock.set(T0 + since_first)
    assert authn.request_sign_in(email=email).status == expected


# Q-072: wrong authenticator/recovery codes before restarting from email (5 proposed default).
def _pending_mfa_client(make_user) -> Client:
    user = make_user("ruth@example.org")
    RoleAssignment.objects.create(user=user, role=roles.PASTOR, granted_at=clock_now())
    enrollment = mfa.start_enrollment(user)
    from ham.identity import totp

    mfa.confirm_enrollment(
        user, secret=enrollment.secret, code=totp.current_code(enrollment.secret)
    )
    client = Client()
    session = client.session
    session[SESSION_PENDING_MFA_USER_ID] = str(user.pk)
    session.save()
    return client


@pytest.mark.parametrize("use_recovery", [False, True], ids=["authenticator", "recovery"])
def test_wrong_mfa_codes_restart_sign_in_at_the_limit(make_user, use_recovery: bool):
    client = _pending_mfa_client(make_user)
    url = reverse("web:sign_in_mfa")
    data = {"code": "not-a-code"}
    if use_recovery:
        data["use_recovery"] = "1"
    for attempt in range(1, RULES.auth.MFA_CODE_MAX_ATTEMPTS):
        response = client.post(url, data)
        assert response.status_code == 200, attempt  # still on the challenge page
        assert client.session[SESSION_MFA_ATTEMPTS] == attempt
    response = client.post(url, data)  # the limit-th wrong code
    assert response.status_code == 302
    assert response["Location"] == reverse("web:sign_in")
    assert SESSION_PENDING_MFA_USER_ID not in client.session
    # The pending sign-in is gone: the challenge page now sends the person back to email.
    assert client.get(url)["Location"] == reverse("web:sign_in")
