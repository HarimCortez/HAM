from __future__ import annotations

import uuid
from typing import Any

import pytest

from ham.authz import roles
from ham.authz.context import ActorContext, ScopedRole
from ham.authz.matrix import MATRIX, Decision, authorize


def _ctx(role_set: frozenset[str] = frozenset(), **overrides: Any) -> ActorContext:
    defaults: dict[str, Any] = dict(
        user_id=uuid.uuid4(),
        real_user_id=None,
        roles=role_set,
        is_active=True,
        mfa_satisfied=True,
    )
    defaults.update(overrides)
    return ActorContext(**defaults)


class TestDenyByDefault:
    def test_unknown_action_denied(self):
        decision = authorize(_ctx(frozenset({roles.ADMINISTRATOR})), "not.a.real.action")
        assert decision == Decision(False, "unknown action")

    def test_anonymous_denied(self):
        ctx = ActorContext.anonymous()
        decision = authorize(ctx, "shell.use")
        assert decision.allowed is False

    def test_inactive_user_denied(self):
        ctx = _ctx(frozenset({roles.VOLUNTEER}), is_active=False)
        decision = authorize(ctx, "shell.use")
        assert decision.allowed is False

    def test_zero_role_user_denied(self):
        ctx = _ctx(frozenset())
        decision = authorize(ctx, "shell.use")
        assert decision.allowed is False

    def test_every_matrix_action_has_a_decision(self):
        ctx = _ctx(frozenset(roles.ALL_ROLES))
        for action in MATRIX:
            authorize(ctx, action)  # must not raise


class TestUnionOfRoles:
    def test_volunteer_and_director_gets_director_permissions(self):
        ctx = _ctx(frozenset({roles.VOLUNTEER, roles.HAM_DIRECTOR}))
        assert authorize(ctx, "user.list").allowed is True
        assert authorize(ctx, "audit.view").allowed is True

    def test_plain_volunteer_denied_admin_actions(self):
        ctx = _ctx(frozenset({roles.VOLUNTEER}))
        assert authorize(ctx, "user.list").allowed is False
        assert authorize(ctx, "role.grant_global").allowed is False


class TestQ054LeaderAssignment:
    @pytest.mark.parametrize("role", [roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR])
    def test_director_and_ad_may_assign_leaders(self, role):
        ctx = _ctx(frozenset({role}))
        assert authorize(ctx, "leader.project.assign").allowed is True

    def test_administrator_may_not_assign_leaders(self):
        ctx = _ctx(frozenset({roles.ADMINISTRATOR}))
        assert authorize(ctx, "leader.project.assign").allowed is False


class TestQ045MfaGating:
    def test_mfa_role_inactive_until_satisfied(self):
        ctx = _ctx(frozenset({roles.HAM_DIRECTOR}), mfa_satisfied=False)
        assert authorize(ctx, "user.list").allowed is False

    def test_mfa_role_active_once_satisfied(self):
        ctx = _ctx(frozenset({roles.HAM_DIRECTOR}), mfa_satisfied=True)
        assert authorize(ctx, "user.list").allowed is True

    def test_non_mfa_role_still_works_before_enrollment(self):
        ctx = _ctx(frozenset({roles.HAM_DIRECTOR, roles.VOLUNTEER}), mfa_satisfied=False)
        assert authorize(ctx, "shell.use").allowed is True
        assert authorize(ctx, "user.list").allowed is False


class TestImpersonationFlags:
    def test_blocked_action_reports_allowed_true_and_blocked_true(self):
        ctx = _ctx(frozenset({roles.ADMINISTRATOR}), impersonation_id=uuid.uuid4())
        decision = authorize(ctx, "role.grant_global")
        assert decision.allowed is True
        assert decision.blocked_by_impersonation is True

    def test_non_blocked_action_unaffected_by_impersonation(self):
        ctx = _ctx(frozenset({roles.ADMINISTRATOR}), impersonation_id=uuid.uuid4())
        decision = authorize(ctx, "user.list")
        assert decision.allowed is True
        assert decision.blocked_by_impersonation is False

    def test_no_nested_impersonation(self):
        ctx = _ctx(frozenset({roles.ADMINISTRATOR}), impersonation_id=uuid.uuid4())
        decision = authorize(ctx, "impersonation.start")
        assert decision.blocked_by_impersonation is True

    def test_impersonation_stop_only_while_impersonating(self):
        ctx = _ctx(frozenset({roles.VOLUNTEER}), impersonation_id=uuid.uuid4())
        assert authorize(ctx, "impersonation.stop").allowed is True
        ctx2 = _ctx(frozenset({roles.ADMINISTRATOR}))
        assert authorize(ctx2, "impersonation.stop").allowed is False


class TestScope:
    def test_self_scope_allows_own_record(self):
        user_id = uuid.uuid4()
        ctx = _ctx(frozenset({roles.VOLUNTEER}), user_id=user_id)
        decision = authorize(ctx, "me.update", resource=None)
        assert decision.allowed is True

    def test_self_scope_denies_other_users_record(self):
        ctx = _ctx(frozenset({roles.VOLUNTEER}))

        class _Resource:
            user_id = uuid.uuid4()

        decision = authorize(ctx, "me.update", resource=_Resource())
        assert decision.allowed is False

    def test_leads_project_scope(self):
        project_id = uuid.uuid4()
        ctx = _ctx(
            frozenset({roles.PROJECT_LEADER}),
            scoped_roles=(ScopedRole(roles.PROJECT_LEADER, "project", project_id),),
        )

        class _Resource:
            pass

        r = _Resource()
        r.project_id = project_id
        # No step-1 action currently uses LEADS_PROJECT; exercise via matrix internals.
        from ham.authz.matrix import Scope, _check_scope

        assert _check_scope(Scope.LEADS_PROJECT, ctx, r) is True
        r2 = _Resource()
        r2.project_id = uuid.uuid4()
        assert _check_scope(Scope.LEADS_PROJECT, ctx, r2) is False


class TestStepUpFlag:
    def test_role_grant_flags_step_up_required(self):
        ctx = _ctx(frozenset({roles.ADMINISTRATOR}))
        decision = authorize(ctx, "role.grant_global")
        assert decision.step_up_required is True

    def test_user_list_does_not_require_step_up(self):
        ctx = _ctx(frozenset({roles.ADMINISTRATOR}))
        decision = authorize(ctx, "user.list")
        assert decision.step_up_required is False
