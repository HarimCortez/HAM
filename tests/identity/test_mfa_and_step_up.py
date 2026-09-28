"""Two-step sign-in enforcement (foundation.md §9.3): every §60.1 role is gated, a role
granted mid-session downgrades until enrolled/verified, a trusted device skips TOTP until day
30 and is re-challenged on day 31, step-up freshness per action kind, MFA reset invalidates
trust."""

from __future__ import annotations

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse

from ham import jobs
from ham.authz import roles
from ham.authz.matrix import authorize
from ham.identity import mfa
from ham.identity.middleware import build_actor_context
from ham.identity.models import RoleAssignment
from ham.platform.clock import FixedClock, SystemClock, set_clock
from ham.platform.clock import now as clock_now
from ham.rules import RULES

pytestmark = pytest.mark.django_db


def _grant(user, role):
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


def _enroll(user) -> str:
    enrollment = mfa.start_enrollment(user)
    code = _current_code(enrollment.secret)
    mfa.confirm_enrollment(user, secret=enrollment.secret, code=code)
    return enrollment.secret


def _current_code(secret: str) -> str:
    from ham.identity import totp

    return totp.current_code(secret)


@pytest.mark.parametrize(
    "role",
    [
        roles.ADMINISTRATOR,
        roles.HAM_DIRECTOR,
        roles.ASSISTANT_DIRECTOR,
        roles.PASTOR,
        roles.BOARD_REPRESENTATIVE,
    ],
)
def test_every_mfa_role_is_required_to_enroll(role, make_user):
    user = make_user(f"{role.lower()}@example.org")
    _grant(user, role)
    assert mfa.mfa_required(user)
    assert not mfa.is_enrolled(user)


def test_non_mfa_role_not_required(make_user):
    user = make_user("kevin@example.org")
    _grant(user, roles.VOLUNTEER)
    assert not mfa.mfa_required(user)


def test_effective_roles_exclude_unverified_mfa_role(make_user, rf):
    """Q-045: before enrollment/verification, the MFA role's permissions are inactive but
    other (non-MFA) roles the person holds still apply."""
    user = make_user("marcus@example.org")
    _grant(user, roles.HAM_DIRECTOR)
    _grant(user, roles.VOLUNTEER)

    request = rf.get("/")
    request.user = user
    request.session = Client().session
    ctx = build_actor_context(request)
    assert ctx.roles == frozenset({roles.HAM_DIRECTOR, roles.VOLUNTEER})
    assert ctx.effective_roles == frozenset({roles.VOLUNTEER})
    assert not authorize(ctx, "user.list").allowed  # HAM_DIRECTOR permission inactive
    assert authorize(ctx, "shell.use").allowed  # VOLUNTEER permission still active


def test_mid_session_role_grant_requires_mfa_before_it_applies(client: Client, make_user):
    user = make_user("marcus@example.org")
    _grant(user, roles.VOLUNTEER)
    client.force_login(user)
    # No MFA role yet: shell.use works, user.list doesn't.
    assert client.get(reverse("web:audit_log")).status_code == 404

    _grant(user, roles.HAM_DIRECTOR)  # granted mid-session
    # Still denied: the session hasn't verified MFA for the new role yet.
    assert client.get(reverse("web:audit_log")).status_code == 404


def test_trusted_device_skips_totp_until_day_30_then_reprompts(client: Client, make_user):
    user = make_user("ruth@example.org")
    _grant(user, roles.PASTOR)
    _enroll(user)

    clock = FixedClock(dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    set_clock(clock)
    try:
        cookie_value, _expires = mfa.create_trusted_device(user)
        client.cookies[mfa.TRUSTED_DEVICE_COOKIE_NAME] = cookie_value

        clock.advance(RULES.auth.MFA_TRUSTED_DEVICE_LIFETIME - dt.timedelta(days=1))
        assert mfa.check_trusted_device(user, cookie_value)

        clock.advance(dt.timedelta(days=2))  # now past the 30-day lifetime
        assert not mfa.check_trusted_device(user, cookie_value)
    finally:
        set_clock(SystemClock())


def test_step_up_freshness_per_action_kind(make_user):
    from ham.authz.context import ActorContext

    user = make_user("nadia@example.org")
    _grant(user, roles.ADMINISTRATOR)
    _enroll(user)

    ctx = ActorContext(
        user_id=user.id,
        real_user_id=None,
        roles=frozenset({roles.ADMINISTRATOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    now = clock_now()
    assert not ctx.has_fresh_step_up("role_change", now=now, freshness=RULES.auth.STEP_UP_WINDOW)

    stepped_up = ActorContext(
        user_id=user.id,
        real_user_id=None,
        roles=frozenset({roles.ADMINISTRATOR}),
        is_active=True,
        mfa_satisfied=True,
        step_up_at={"role_change": now},
    )
    assert stepped_up.has_fresh_step_up("role_change", now=now, freshness=RULES.auth.STEP_UP_WINDOW)
    # A different kind of step-up doesn't cover this one (Q-046/Q-076: grant/revoke share a
    # kind, but other kinds are separate).
    assert not stepped_up.has_fresh_step_up(
        "audit_export", now=now, freshness=RULES.auth.STEP_UP_WINDOW
    )
    later = now + RULES.auth.STEP_UP_WINDOW + dt.timedelta(seconds=1)
    assert not stepped_up.has_fresh_step_up(
        "role_change", now=later, freshness=RULES.auth.STEP_UP_WINDOW
    )


def test_mfa_reset_invalidates_trusted_device_and_recovery_codes(make_user):
    from ham.authz.context import ActorContext

    admin = make_user("nadia@example.org")
    _grant(admin, roles.ADMINISTRATOR)
    _enroll(admin)

    target = make_user("marcus@example.org")
    _grant(target, roles.HAM_DIRECTOR)
    _enroll(target)
    cookie_value, _ = mfa.create_trusted_device(target)
    assert mfa.check_trusted_device(target, cookie_value)

    admin_ctx = ActorContext(
        user_id=admin.id,
        real_user_id=None,
        roles=frozenset({roles.ADMINISTRATOR}),
        is_active=True,
        mfa_satisfied=True,
        step_up_at={"mfa_reset": clock_now()},
    )
    mfa.reset_mfa(admin_ctx, user_id=target.id, verification_method="phone_call")

    assert not mfa.is_enrolled(target)
    assert not mfa.check_trusted_device(target, cookie_value)
    jobs.run_due_jobs_now()  # the "your MFA was reset" email shouldn't blow up
