from __future__ import annotations

import datetime as dt
import uuid

import pytest

from ham.authz import roles
from ham.authz.commands import ImpersonationBlocked, PermissionDenied
from ham.authz.context import ActorContext
from ham.identity import services
from ham.identity.models import RoleAssignment, User
from ham.outbox.models import OutboxEvent
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db


def _ctx(user: User, *, roles_: frozenset[str] | None = None, **overrides) -> ActorContext:
    active_roles = roles_
    if active_roles is None:
        active_roles = frozenset(
            RoleAssignment.objects.filter(user=user, revoked_at__isnull=True).values_list(
                "role", flat=True
            )
        )
    step_up_at = overrides.pop(
        "step_up_at", {"role_change": clock_now(), "audit_export": clock_now()}
    )
    return ActorContext(
        user_id=user.id,
        real_user_id=None,
        roles=active_roles,
        is_active=True,
        mfa_satisfied=True,
        step_up_at=step_up_at,
        **overrides,
    )


def _grant(user, role, **kw):
    from ham.platform.clock import now as clock_now

    return RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now(), **kw)


class TestBootstrapAdministrator:
    def test_creates_administrator_and_audits_system_actor(self):
        user = services.bootstrap_administrator("owner@example.org")
        assert RoleAssignment.objects.filter(
            user=user, role=roles.ADMINISTRATOR, revoked_at__isnull=True
        ).exists()
        from ham.audit.models import AuditEvent

        event = AuditEvent.objects.get(target_id=str(user.id))
        assert event.actor_type == "system"
        assert event.context["system_actor"] == "system:bootstrap"

    def test_idempotent(self):
        first = services.bootstrap_administrator("owner@example.org")
        second = services.bootstrap_administrator("OWNER@example.org")
        assert first.id == second.id
        assert (
            RoleAssignment.objects.filter(
                user=first, role=roles.ADMINISTRATOR, revoked_at__isnull=True
            ).count()
            == 1
        )


class TestInviteUser:
    def test_admin_can_invite_with_any_role(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        ctx = _ctx(admin)
        user = services.invite_user(
            ctx,
            email="dwayne@example.org",
            first_name="Dwayne",
            last_name="Carter",
            role_list=(roles.PASTOR,),
            reason="",
        )
        assert RoleAssignment.objects.filter(user=user, role=roles.PASTOR).exists()
        assert user.is_invited is True

    def test_assistant_director_may_only_invite_as_volunteer(self, make_user):
        andre = make_user("andre@example.org")
        _grant(andre, roles.ASSISTANT_DIRECTOR)
        ctx = _ctx(andre)
        with pytest.raises(PermissionDenied):
            services.invite_user(
                ctx,
                email="dwayne@example.org",
                first_name="Dwayne",
                last_name="Carter",
                role_list=(roles.PASTOR,),
            )
        user = services.invite_user(
            ctx, email="dwayne@example.org", first_name="Dwayne", last_name="Carter"
        )
        assert RoleAssignment.objects.filter(user=user, role=roles.VOLUNTEER).exists()

    def test_volunteer_cannot_invite(self, make_user):
        kevin = make_user("kevin@example.org")
        _grant(kevin, roles.VOLUNTEER)
        ctx = _ctx(kevin)
        with pytest.raises(PermissionDenied):
            services.invite_user(ctx, email="new@example.org", first_name="New", last_name="Person")

    def test_director_granting_pastor_requires_reason(self, make_user):
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        ctx = _ctx(marcus)
        with pytest.raises(ValueError):
            services.invite_user(
                ctx,
                email="ruth@example.org",
                first_name="Ruth",
                last_name="Alvarez",
                role_list=(roles.PASTOR,),
                reason="",
            )
        services.invite_user(
            ctx,
            email="ruth@example.org",
            first_name="Ruth",
            last_name="Alvarez",
            role_list=(roles.PASTOR,),
            reason="Board vote 2026-09-01",
        )

    def test_director_cannot_invite_administrator(self, make_user):
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        ctx = _ctx(marcus)
        with pytest.raises(PermissionDenied):
            services.invite_user(
                ctx,
                email="new-admin@example.org",
                first_name="New",
                last_name="Admin",
                role_list=(roles.ADMINISTRATOR,),
            )

    def test_emits_user_created_outbox_event(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        ctx = _ctx(admin)
        services.invite_user(
            ctx, email="dwayne@example.org", first_name="Dwayne", last_name="Carter"
        )
        assert OutboxEvent.objects.filter(event_type="UserCreated").exists()

    def test_sets_created_by_id(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        ctx = _ctx(admin)
        user = services.invite_user(
            ctx, email="dwayne@example.org", first_name="Dwayne", last_name="Carter"
        )
        assert user.created_by_id == admin.id

    def test_inviting_existing_email_raises_friendly_value_error_not_500(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        ctx = _ctx(admin)
        with pytest.raises(ValueError, match="already has a HAM account"):
            services.invite_user(
                ctx, email="nadia@example.org", first_name="Nadia", last_name="Duplicate"
            )

    @pytest.mark.django_db(transaction=True)
    def test_invitation_email_sent_with_absolute_sign_in_link(self, make_user, mailoutbox):
        # transaction=True: `ham.outbox.emit`'s dispatch is deferred to `transaction.on_commit`
        # (foundation.md §3), which never fires inside pytest-django's default rolled-back
        # wrapping transaction — the same reason `tests/integrations/test_notifications_
        # subscriber.py` drives the subscriber directly instead. This test wants the real
        # end-to-end path (invite -> outbox -> dispatch job -> email subscriber -> mailbox),
        # so it needs real commits.
        from ham import jobs
        from ham.identity.models import SharedIdentityProfile

        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        SharedIdentityProfile.objects.create(user=admin, full_name="Nadia Ruiz")
        ctx = _ctx(admin)
        services.invite_user(
            ctx, email="dwayne@example.org", first_name="Dwayne", last_name="Carter"
        )
        jobs.run_due_jobs_now()
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["dwayne@example.org"]
        assert "Nadia" in mailoutbox[0].subject
        assert "http://localhost:8000/sign-in" in mailoutbox[0].body

    @pytest.mark.django_db(transaction=True)
    def test_bootstrap_created_user_gets_no_invitation_email(self, mailoutbox):
        from ham import jobs

        services.bootstrap_administrator("owner@example.org")
        jobs.run_due_jobs_now()
        assert mailoutbox == []


class TestInvitationValidity:
    def test_active_user_is_always_valid(self, make_user):
        user = make_user("kevin@example.org")
        user.first_sign_in_at = clock_now()
        user.save()
        assert services.invitation_is_valid(user) is True

    def test_fresh_invitation_is_valid(self, make_user):
        user = make_user("kevin@example.org")
        assert services.invitation_is_valid(user) is True

    def test_expired_invitation_is_invalid(self, make_user):
        from ham.rules import RULES

        user = make_user("kevin@example.org")
        user.created_at = (
            clock_now() - RULES.auth.ACCOUNT_INVITATION_LIFETIME - dt.timedelta(days=1)
        )
        user.save(update_fields=["created_at"])
        assert services.invitation_is_valid(user) is False

    def test_cancelled_invitation_is_invalid(self, make_user):
        user = make_user("kevin@example.org")
        user.is_active = False
        user.disabled_at = clock_now()
        user.save()
        assert services.invitation_is_valid(user) is False


class TestResendCancelInvitation:
    def test_resend_restarts_the_window(self, make_user):
        from ham.rules import RULES

        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        invited = make_user("kevin@example.org")
        invited.created_at = (
            clock_now() - RULES.auth.ACCOUNT_INVITATION_LIFETIME - dt.timedelta(days=1)
        )
        invited.save(update_fields=["created_at"])
        assert services.invitation_is_valid(invited) is False

        services.resend_invitation(_ctx(admin), user_id=invited.id)
        invited.refresh_from_db()
        assert services.invitation_is_valid(invited) is True

    def test_cannot_resend_after_first_sign_in(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        user = make_user("kevin@example.org")
        user.first_sign_in_at = clock_now()
        user.save()
        with pytest.raises(ValueError):
            services.resend_invitation(_ctx(admin), user_id=user.id)

    def test_cancel_disables_the_invited_account(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        invited = make_user("kevin@example.org")
        services.cancel_invitation(_ctx(admin), user_id=invited.id, reason="wrong address")
        invited.refresh_from_db()
        assert invited.is_disabled is True
        assert services.invitation_is_valid(invited) is False


class TestDisableEnableUser:
    def test_admin_disables_user(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        kevin = make_user("kevin@example.org")
        _grant(kevin, roles.VOLUNTEER)
        ctx = _ctx(admin)
        services.disable_user(ctx, user_id=kevin.id, reason="left the ministry")
        kevin.refresh_from_db()
        assert kevin.is_disabled is True
        assert kevin.is_active is False

    def test_cannot_disable_self(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        ctx = _ctx(admin)
        with pytest.raises(PermissionDenied):
            services.disable_user(ctx, user_id=admin.id)

    def test_disabling_down_to_one_administrator_is_allowed(self, make_user):
        # Q-035 blocks reaching *zero* active Administrators, not reaching one. Since
        # `user.disable` requires the actor to hold ADMINISTRATOR themselves (matrix), and
        # self-disable is blocked separately above, the only way to disable an Administrator
        # is for another Administrator to do it — which always leaves at least that actor.
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        other_admin = make_user("other-admin@example.org")
        _grant(other_admin, roles.ADMINISTRATOR)
        services.disable_user(_ctx(admin), user_id=other_admin.id, reason="stepping down")
        other_admin.refresh_from_db()
        assert other_admin.is_disabled is True

    def test_count_active_administrators_excludes_disabled_and_revoked(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        assert services._count_active_administrators() == 1
        assert services._count_active_administrators(exclude_user_id=admin.id) == 0

    def test_volunteer_cannot_disable_anyone(self, make_user):
        kevin = make_user("kevin@example.org")
        _grant(kevin, roles.VOLUNTEER)
        luis = make_user("luis@example.org")
        _grant(luis, roles.VOLUNTEER)
        with pytest.raises(PermissionDenied):
            services.disable_user(_ctx(kevin), user_id=luis.id)

    def test_director_can_disable_a_volunteer(self, make_user):
        """Q-052/Q-079: the Director may disable accounts that don't hold Administrator."""
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        kevin = make_user("kevin@example.org")
        _grant(kevin, roles.VOLUNTEER)
        services.disable_user(_ctx(marcus), user_id=kevin.id, reason="left the ministry")
        kevin.refresh_from_db()
        assert kevin.is_disabled is True

    def test_director_cannot_disable_an_administrator(self, make_user):
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        with pytest.raises(PermissionDenied):
            services.disable_user(_ctx(marcus), user_id=admin.id, reason="test")

    def test_disable_requires_a_reason(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        kevin = make_user("kevin@example.org")
        _grant(kevin, roles.VOLUNTEER)
        with pytest.raises(ValueError, match="reason"):
            services.disable_user(_ctx(admin), user_id=kevin.id, reason="   ")

    def test_cannot_disable_last_active_director(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        with pytest.raises(ValueError, match="Director"):
            services.disable_user(_ctx(admin), user_id=marcus.id, reason="leaving")

    def test_disabling_down_to_one_director_is_allowed(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        other_director = make_user("other-director@example.org")
        _grant(other_director, roles.HAM_DIRECTOR)
        services.disable_user(_ctx(admin), user_id=other_director.id, reason="leaving")
        other_director.refresh_from_db()
        assert other_director.is_disabled is True

    def test_disable_ends_impersonation_of_the_target(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        kevin = make_user("kevin@example.org")
        _grant(kevin, roles.VOLUNTEER)
        impersonate_ctx = _ctx(
            admin, step_up_at={"impersonation_start": clock_now(), "role_change": clock_now()}
        )
        session = services.start_impersonation(impersonate_ctx, target_user_id=kevin.id, reason="x")

        other_admin = make_user("other-admin@example.org")
        _grant(other_admin, roles.ADMINISTRATOR)
        services.disable_user(_ctx(other_admin), user_id=kevin.id, reason="left the ministry")

        session.refresh_from_db()
        assert session.ended_at is not None
        from ham.identity.models import ImpersonationSession

        assert session.end_reason == ImpersonationSession.END_REASON_TARGET_DISABLED
        assert OutboxEvent.objects.filter(event_type="ImpersonationEnded").exists()

    def test_disable_blocked_while_impersonating(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        kevin = make_user("kevin@example.org")
        _grant(kevin, roles.VOLUNTEER)
        ctx = _ctx(admin, impersonation_id=uuid.uuid4())
        with pytest.raises(ImpersonationBlocked):
            services.disable_user(ctx, user_id=kevin.id)


class TestGlobalRoles:
    def test_grant_and_revoke_round_trip(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        kevin = make_user("kevin@example.org")
        ctx = _ctx(admin)
        assignment = services.grant_global_role(ctx, user_id=kevin.id, role=roles.VOLUNTEER)
        assert RoleAssignment.objects.filter(pk=assignment.pk, revoked_at__isnull=True).exists()
        services.revoke_global_role(ctx, assignment_id=assignment.id, reason="no longer serving")
        assignment.refresh_from_db()
        assert assignment.revoked_at is not None

    def test_cannot_self_grant(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        ctx = _ctx(admin)
        with pytest.raises(PermissionDenied):
            services.grant_global_role(ctx, user_id=admin.id, role=roles.VOLUNTEER)

    def test_director_cannot_grant_administrator(self, make_user):
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        kevin = make_user("kevin@example.org")
        ctx = _ctx(marcus)
        with pytest.raises(PermissionDenied):
            services.grant_global_role(ctx, user_id=kevin.id, role=roles.ADMINISTRATOR)

    def test_grant_requires_step_up(self, make_user):
        from ham.authz.commands import StepUpRequired

        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        kevin = make_user("kevin@example.org")
        ctx = ActorContext(
            user_id=admin.id,
            real_user_id=None,
            roles=frozenset({roles.ADMINISTRATOR}),
            is_active=True,
            mfa_satisfied=True,
            step_up_at={},
        )
        with pytest.raises(StepUpRequired):
            services.grant_global_role(ctx, user_id=kevin.id, role=roles.VOLUNTEER)

    def test_cannot_revoke_last_active_director(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        marcus = make_user("marcus@example.org")
        assignment = _grant(marcus, roles.HAM_DIRECTOR)
        with pytest.raises(ValueError, match="Director"):
            services.revoke_global_role(
                _ctx(admin), assignment_id=assignment.id, reason="stepping down"
            )

    def test_revoking_down_to_one_administrator_is_allowed(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        other_admin = make_user("other-admin@example.org")
        other_assignment = _grant(other_admin, roles.ADMINISTRATOR)
        services.revoke_global_role(
            _ctx(admin), assignment_id=other_assignment.id, reason="stepping down"
        )
        other_assignment.refresh_from_db()
        assert other_assignment.revoked_at is not None


class TestLeaderAssignment:
    def test_director_can_assign_project_leader(self, make_user):
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        luis = make_user("luis@example.org")
        project_id = uuid.uuid4()
        ctx = _ctx(marcus)
        assignment = services.assign_project_leader(ctx, project_id=project_id, user_id=luis.id)
        assert assignment.role == roles.PROJECT_LEADER
        assert assignment.scope_id == project_id

    def test_administrator_cannot_assign_project_leader(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        luis = make_user("luis@example.org")
        ctx = _ctx(admin)
        with pytest.raises(PermissionDenied):
            services.assign_project_leader(ctx, project_id=uuid.uuid4(), user_id=luis.id)

    def test_reassigning_project_leader_replaces_previous(self, make_user):
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        luis = make_user("luis@example.org")
        tom = make_user("tom@example.org")
        project_id = uuid.uuid4()
        ctx = _ctx(marcus)
        first = services.assign_project_leader(ctx, project_id=project_id, user_id=luis.id)
        second = services.assign_project_leader(ctx, project_id=project_id, user_id=tom.id)
        first.refresh_from_db()
        assert first.revoked_at is not None
        assert second.is_active is True

    def test_reassignment_records_the_replaced_user_in_before(self, make_user):
        from ham.audit.models import AuditEvent

        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        luis = make_user("luis@example.org")
        tom = make_user("tom@example.org")
        project_id = uuid.uuid4()
        ctx = _ctx(marcus)
        services.assign_project_leader(ctx, project_id=project_id, user_id=luis.id)
        services.assign_project_leader(ctx, project_id=project_id, user_id=tom.id)
        event = AuditEvent.objects.filter(
            action="leader.project_assigned", target_id=str(project_id)
        ).latest("seq")
        assert event.before == {"previous_user_id": str(luis.id)}

    def test_leader_assign_blocked_while_impersonating_no_step_up_needed_otherwise(self, make_user):
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        luis = make_user("luis@example.org")
        ctx = _ctx(marcus, impersonation_id=uuid.uuid4())
        with pytest.raises(ImpersonationBlocked):
            services.assign_project_leader(ctx, project_id=uuid.uuid4(), user_id=luis.id)
