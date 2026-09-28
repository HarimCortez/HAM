"""``nav_for`` per seeded persona (foundation.md §9.1: "`nav_for` per seeded persona matches
the navigation.md §3.1 table for built destinations").

Step 1 only builds Home, Inbox, Me and the Admin group (Users & roles, Church settings,
Integrations, Rules) plus Audit log (navigation.md §3.3's full sidebar; foundation.md §2.10
"step 1 renders only built destinations"). This test uses the exact personas from
``manage.py seed_dev`` (not a hand-picked subset) so a new persona or role change there is
caught here too.
"""

from __future__ import annotations

import uuid

from ham.authz.context import ActorContext
from ham.authz.nav import nav_for
from ham.identity.management.commands.seed_dev import PERSONAS

# Expected *built* nav keys per role, independently derived from ham/authz/matrix.py's step-1
# action table cross-referenced with navigation.md §3.1/§3.3 (only Home/Inbox/Me/Admin
# group/Audit log exist yet): a role's item shows only if the matrix grants that item's action.
_BASE = {"home", "inbox", "me"}
# S2.0/S2.8 (intake.md §5, §7 "Nav"): `request.list` (Director, Assistant Director, Pastor,
# Board representative, plus the Administrator per Q-124's view-only access) puts `nav_for`'s
# `requests` item in the *full* nav_for() result — `built=True` since S2.8, so it now also
# shows up in `test_nav_mobile.py`'s built-destination checks.
_EXPECTED_BY_ROLE: dict[str, set[str]] = {
    "ADMINISTRATOR": _BASE
    | {"admin_users", "admin_church", "admin_integrations", "admin_rules", "audit_log"}
    | {"requests"},
    "HAM_DIRECTOR": _BASE | {"admin_users", "admin_rules", "audit_log"} | {"requests"},
    "ASSISTANT_DIRECTOR": set(_BASE) | {"requests"},
    "PASTOR": set(_BASE) | {"requests"},
    "BOARD_REPRESENTATIVE": set(_BASE) | {"requests"},
    "SOCIAL_MEDIA_SPECIALIST": set(_BASE),
    "VOLUNTEER": set(_BASE),
    "CONTRACTOR": set(_BASE),
}


def _expected_for(role_list: tuple[str, ...]) -> set[str]:
    expected: set[str] = set()
    for role in role_list:
        expected |= _EXPECTED_BY_ROLE[role]
    return expected


def _ctx(role_list: tuple[str, ...]) -> ActorContext:
    return ActorContext(
        user_id=uuid.UUID("00000000-0000-7000-8000-000000000099"),
        real_user_id=None,
        roles=frozenset(role_list),
        is_active=True,
        mfa_satisfied=True,
    )


def test_every_seed_dev_persona_matches_expected_nav():
    mismatches = []
    for email, _full_name, role_list in PERSONAS:
        keys = {item.key for item in nav_for(_ctx(role_list))}
        expected = _expected_for(role_list)
        if keys != expected:
            mismatches.append(f"{email} (roles={role_list}): expected {expected}, got {keys}")
    assert not mismatches, "\n".join(mismatches)


def test_marcus_director_plus_volunteer_gets_union_not_switch():
    # navigation.md §3.4.1 "Union, not switching": Director+Volunteer gets the Director nav.
    marcus = next(p for p in PERSONAS if p[0] == "marcus@example.org")
    keys = {item.key for item in nav_for(_ctx(marcus[2]))}
    assert keys == _EXPECTED_BY_ROLE["HAM_DIRECTOR"]
