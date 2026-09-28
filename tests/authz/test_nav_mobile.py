"""``bottom_nav_for``/``admin_group_items``/``more_items`` (navigation.md §3.1, Q-091,
visual QA C2, usability C2): the mobile bottom nav never exceeds 5 items, matches the
navigation.md table's Admin/More grouping, and every destination (plus Sign out) is still
reachable somewhere on a phone.
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz.context import ActorContext
from ham.authz.nav import admin_group_items, bottom_nav_for, more_items, nav_for
from ham.identity.management.commands.seed_dev import PERSONAS


def _ctx(role_list: tuple[str, ...]) -> ActorContext:
    return ActorContext(
        user_id=uuid.UUID("00000000-0000-7000-8000-000000000099"),
        real_user_id=None,
        roles=frozenset(role_list),
        is_active=True,
        mfa_satisfied=True,
    )


@pytest.mark.parametrize("email, _full_name, role_list", PERSONAS)
def test_bottom_nav_never_exceeds_five_items(email, _full_name, role_list):
    ctx = _ctx(role_list)
    tabs = bottom_nav_for(ctx)
    assert len(tabs) <= 5, f"{email} ({role_list}): {[t.key for t in tabs]}"


def test_administrator_bottom_nav_is_home_admin_inbox_more():
    ctx = _ctx(("ADMINISTRATOR",))
    keys = [item.key for item in bottom_nav_for(ctx)]
    assert keys == ["home", "admin", "inbox", "more"]


def test_director_bottom_nav_ends_in_more_not_a_direct_me_tab():
    ctx = _ctx(("HAM_DIRECTOR",))
    keys = [item.key for item in bottom_nav_for(ctx)]
    assert keys == ["home", "inbox", "more"]
    assert "me" not in keys


def test_volunteer_bottom_nav_ends_in_me_directly():
    ctx = _ctx(("VOLUNTEER",))
    keys = [item.key for item in bottom_nav_for(ctx)]
    assert keys == ["home", "inbox", "me"]
    assert "more" not in keys


def test_admin_index_lists_every_admin_group_destination_for_an_administrator():
    ctx = _ctx(("ADMINISTRATOR",))
    keys = {item.key for item in admin_group_items(ctx)}
    assert keys == {"admin_users", "admin_church", "admin_integrations", "admin_rules", "audit_log"}


def test_more_page_for_administrator_is_just_me_admin_items_live_on_their_own_tab():
    ctx = _ctx(("ADMINISTRATOR",))
    keys = [item.key for item in more_items(ctx)]
    assert keys == ["me"]


def test_more_page_for_director_carries_the_admin_group_items_plus_me():
    ctx = _ctx(("HAM_DIRECTOR",))
    keys = {item.key for item in more_items(ctx)}
    assert keys == {"admin_users", "admin_rules", "audit_log", "me"}


@pytest.mark.parametrize("email, _full_name, role_list", PERSONAS)
def test_every_full_nav_destination_is_reachable_from_the_mobile_set(email, _full_name, role_list):
    """Every destination that would show on the sidebar is either a direct bottom-nav tab, or
    listed on the Admin index / More page reached from a tab — nothing simply disappears on a
    phone (usability C2: "an Administrator on a phone cannot sign out ... Audit log and Me are
    off-screen")."""
    ctx = _ctx(role_list)
    full_keys = {item.key for item in nav_for(ctx)}
    bottom_keys = {item.key for item in bottom_nav_for(ctx)}
    admin_keys = {item.key for item in admin_group_items(ctx)}
    more_keys = {item.key for item in more_items(ctx)}
    reachable = bottom_keys | admin_keys | more_keys
    assert full_keys <= reachable, f"{email}: missing {full_keys - reachable}"
