from __future__ import annotations

import datetime as dt

from ham.authz import roles
from ham.authz.context import ActorContext


def test_anonymous_defaults():
    ctx = ActorContext.anonymous()
    assert ctx.is_authenticated is False
    assert ctx.is_impersonating is False
    assert ctx.effective_roles == frozenset()


def test_effective_roles_filters_mfa_roles_until_satisfied():
    ctx = ActorContext(
        user_id="u1",
        real_user_id=None,
        roles=frozenset({roles.HAM_DIRECTOR, roles.VOLUNTEER}),
        is_active=True,
        mfa_satisfied=False,
    )
    assert ctx.effective_roles == frozenset({roles.VOLUNTEER})


def test_effective_roles_includes_mfa_roles_once_satisfied():
    ctx = ActorContext(
        user_id="u1",
        real_user_id=None,
        roles=frozenset({roles.HAM_DIRECTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    assert ctx.effective_roles == frozenset({roles.HAM_DIRECTOR})


def test_has_fresh_step_up():
    now = dt.datetime(2026, 10, 6, tzinfo=dt.UTC)
    ctx = ActorContext(
        user_id="u1",
        real_user_id=None,
        roles=frozenset(),
        is_active=True,
        step_up_at={"role_change": now - dt.timedelta(minutes=3)},
    )
    assert ctx.has_fresh_step_up("role_change", now=now, freshness=dt.timedelta(minutes=5))
    assert not ctx.has_fresh_step_up("role_change", now=now, freshness=dt.timedelta(minutes=2))
    assert not ctx.has_fresh_step_up("audit_export", now=now, freshness=dt.timedelta(minutes=5))
