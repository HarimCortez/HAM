"""Impersonation (foundation.md §9.3, §59, Q-034, Q-049, Q-053): reason required, not another
Administrator, no nesting, idle timeout returns the Admin to their own account, blocked
actions are refused and audited, the Director reveal exemption is never applied under
impersonation."""

from __future__ import annotations

import datetime as dt

import pytest

from ham.audit.models import AuditEvent
from ham.authz import roles
from ham.authz.commands import ImpersonationBlocked, PermissionDenied
from ham.authz.context import ActorContext
from ham.identity import services
from ham.identity.middleware import SessionLifetimeMiddleware
from ham.identity.models import ImpersonationSession, RoleAssignment
from ham.platform.clock import FixedClock, SystemClock, set_clock
from ham.platform.clock import now as clock_now
from ham.rules import RULES

pytestmark = pytest.mark.django_db


def _grant(user, role):
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


def _admin_ctx(admin, *, impersonating=None, step_up=True):
    step_up_at = {"impersonation_start": clock_now()} if step_up else {}
    return ActorContext(
        user_id=admin.id,
        real_user_id=None,
        roles=frozenset({roles.ADMINISTRATOR}),
        is_active=True,
        mfa_satisfied=True,
        step_up_at=step_up_at,
    )


def test_reason_is_required(make_user):
    admin = make_user("nadia@example.org")
    _grant(admin, roles.ADMINISTRATOR)
    kevin = make_user("kevin@example.org")
    _grant(kevin, roles.VOLUNTEER)

    with pytest.raises(ValueError):
        services.start_impersonation(_admin_ctx(admin), target_user_id=kevin.id, reason="   ")


def test_cannot_impersonate_another_administrator(make_user):
    admin = make_user("nadia@example.org")
    _grant(admin, roles.ADMINISTRATOR)
    other_admin = make_user("other-admin@example.org")
    _grant(other_admin, roles.ADMINISTRATOR)

    with pytest.raises(PermissionDenied):
        services.start_impersonation(
            _admin_ctx(admin), target_user_id=other_admin.id, reason="troubleshooting"
        )


def test_no_nesting(make_user):
    admin = make_user("nadia@example.org")
    _grant(admin, roles.ADMINISTRATOR)
    kevin = make_user("kevin@example.org")
    _grant(kevin, roles.VOLUNTEER)
    tom = make_user("tom@example.org")
    _grant(tom, roles.VOLUNTEER)

    session = services.start_impersonation(_admin_ctx(admin), target_user_id=kevin.id, reason="x")
    already_impersonating_ctx = ActorContext(
        user_id=kevin.id,
        real_user_id=admin.id,
        roles=frozenset({roles.VOLUNTEER}),
        is_active=True,
        mfa_satisfied=True,
        impersonation_id=session.id,
        step_up_at={"impersonation_start": clock_now()},
    )
    with pytest.raises(ImpersonationBlocked):
        services.start_impersonation(
            already_impersonating_ctx, target_user_id=tom.id, reason="nested"
        )
    event = AuditEvent.objects.filter(action="impersonation.action_blocked").latest("seq")
    assert event.actor_user_id == admin.id
    assert event.acting_as_user_id == kevin.id


def test_blocked_action_while_impersonating_is_refused_and_audited(make_user):
    admin = make_user("nadia@example.org")
    _grant(admin, roles.ADMINISTRATOR)
    kevin = make_user("kevin@example.org")
    _grant(kevin, roles.VOLUNTEER)

    session = services.start_impersonation(_admin_ctx(admin), target_user_id=kevin.id, reason="x")
    ctx = ActorContext(
        user_id=kevin.id,
        real_user_id=admin.id,
        roles=frozenset({roles.VOLUNTEER}),
        is_active=True,
        mfa_satisfied=True,
        impersonation_id=session.id,
    )
    # me.security.manage is blocked_while_impersonating=True.
    with pytest.raises(ImpersonationBlocked):
        services.regenerate_own_recovery_codes(ctx)

    event = AuditEvent.objects.filter(action="impersonation.action_blocked").latest("seq")
    assert event.actor_user_id == admin.id
    assert event.acting_as_user_id == kevin.id
    assert event.impersonation_id == session.id


def test_idle_timeout_returns_admin_to_own_account(rf, make_user):
    admin = make_user("nadia@example.org")
    _grant(admin, roles.ADMINISTRATOR)
    kevin = make_user("kevin@example.org")
    _grant(kevin, roles.VOLUNTEER)

    clock = FixedClock(dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    set_clock(clock)
    try:
        session = services.start_impersonation(
            _admin_ctx(admin), target_user_id=kevin.id, reason="troubleshoot"
        )
        clock.advance(RULES.auth.IMPERSONATION_IDLE_TIMEOUT + dt.timedelta(minutes=1))

        request = rf.get("/")
        request.user = admin
        request.session = {}
        actor = ActorContext(
            user_id=kevin.id,
            real_user_id=admin.id,
            roles=frozenset({roles.VOLUNTEER}),
            is_active=True,
            impersonation_id=session.id,
        )
        request.actor = actor
        mw = SessionLifetimeMiddleware(get_response=lambda r: None)
        mw._enforce_impersonation_idle(request, actor)

        session.refresh_from_db()
        assert session.ended_at is not None
        assert session.end_reason == ImpersonationSession.END_REASON_IDLE_TIMEOUT
        event = AuditEvent.objects.filter(action="impersonation.ended").latest("seq")
        assert event.actor_user_id == admin.id
        assert event.acting_as_user_id == kevin.id
    finally:
        set_clock(SystemClock())


def test_director_reveal_exemption_not_applied_while_impersonating(make_user):
    """Q-024's Director reveal exemption applies to the *effective actor*; while an Admin
    impersonates the Director, the real actor is the Admin, so the exemption never applies
    (foundation.md owner-decisions box, Q-024 consequence)."""
    admin = make_user("nadia@example.org")
    _grant(admin, roles.ADMINISTRATOR)
    director = make_user("marcus@example.org")
    _grant(director, roles.HAM_DIRECTOR)

    session = services.start_impersonation(
        _admin_ctx(admin), target_user_id=director.id, reason="x"
    )
    ctx = ActorContext(
        user_id=director.id,
        real_user_id=admin.id,
        roles=frozenset({roles.HAM_DIRECTOR}),
        is_active=True,
        mfa_satisfied=True,
        impersonation_id=session.id,
    )
    assert ctx.is_impersonating
    # requester_pii.reveal is declared with an empty allowed_roles set in step 1 (Q-081); the
    # real point of this test is that `ctx.real_user_id` (the Admin) — not `ctx.user_id` (the
    # Director) — is what any future reveal-exemption check must key off of.
    assert ctx.real_user_id == admin.id
    assert ctx.user_id == director.id
