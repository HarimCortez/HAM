from __future__ import annotations

from ham.authz.roles import MFA_REQUIRED_ROLES
from ham.rules import RULES


def test_mfa_required_roles_matches_rules_module():
    assert MFA_REQUIRED_ROLES == frozenset(RULES.auth.MFA_REQUIRED_ROLES)


def test_step_up_actions_kinds_cover_every_step_up_flagged_action():
    from ham.authz.matrix import MATRIX

    kinds_by_action = dict(RULES.auth.STEP_UP_ACTIONS)
    for action, rule in MATRIX.items():
        if rule.step_up:
            assert action in kinds_by_action, f"{action} has no ham.rules STEP_UP_ACTIONS kind"
