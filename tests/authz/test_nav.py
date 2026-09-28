from __future__ import annotations

from ham.authz import roles
from ham.authz.context import ActorContext
from ham.authz.nav import nav_for


def _ctx(role_set):
    return ActorContext(
        user_id="00000000-0000-7000-8000-000000000001",
        real_user_id=None,
        roles=frozenset(role_set),
        is_active=True,
        mfa_satisfied=True,
    )


def test_administrator_sees_admin_and_audit():
    keys = {item.key for item in nav_for(_ctx({roles.ADMINISTRATOR}))}
    assert {"home", "inbox", "me", "admin_users", "audit_log"} <= keys


def test_volunteer_sees_only_shell_and_me():
    keys = {item.key for item in nav_for(_ctx({roles.VOLUNTEER}))}
    assert keys == {"home", "inbox", "me"}


def test_director_sees_users_and_audit_but_not_church_settings():
    keys = {item.key for item in nav_for(_ctx({roles.HAM_DIRECTOR}))}
    assert "admin_users" in keys
    assert "audit_log" in keys
    assert "admin_church" not in keys  # Administrator-only (church_profile.update)


def test_anonymous_sees_nothing():
    assert nav_for(ActorContext.anonymous()) == []


def test_all_items_declare_a_known_action():
    from ham.authz.matrix import MATRIX
    from ham.authz.nav import _ITEMS

    for item in _ITEMS:
        assert item.action in MATRIX
