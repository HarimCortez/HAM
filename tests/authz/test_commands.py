from __future__ import annotations

import uuid

import pytest

from ham.audit.models import AuditEvent
from ham.authz import roles
from ham.authz.commands import (
    CommandResult,
    ImpersonationBlocked,
    OutboxSpec,
    PermissionDenied,
    StepUpRequired,
    command,
)
from ham.authz.context import ActorContext
from ham.identity.models import User
from ham.outbox.models import OutboxEvent

pytestmark = pytest.mark.django_db


@command("user.update_identity")
def _rename_user(ctx: ActorContext, *, user_id, new_name: str, blow_up: bool = False):
    user = User.objects.get(pk=user_id)
    user.email = user.email  # touch, no real change needed for the test
    user.save()
    if blow_up:
        raise RuntimeError("boom")
    return CommandResult(
        value=new_name,
        audit_action="user.identity_updated",
        target_type="user",
        target_id=str(user_id),
        after={"full_name": new_name},
        outbox=OutboxSpec(
            "UserProfileUpdated",
            aggregate_type="user",
            aggregate_id=user_id,
            payload={"changed_fields": ["full_name"]},
        ),
    )


def _admin_ctx(user_id) -> ActorContext:
    return ActorContext(
        user_id=user_id,
        real_user_id=None,
        roles=frozenset({roles.ADMINISTRATOR}),
        is_active=True,
        mfa_satisfied=True,
    )


class TestCommandPipeline:
    def test_denied_action_raises_and_writes_nothing(self, make_user):
        volunteer = make_user("kevin@example.org")
        ctx = ActorContext(
            user_id=volunteer.id,
            real_user_id=None,
            roles=frozenset({roles.VOLUNTEER}),
            is_active=True,
            mfa_satisfied=True,
        )
        before = AuditEvent.objects.count()
        with pytest.raises(PermissionDenied):
            _rename_user(ctx, user_id=volunteer.id, new_name="X")
        assert AuditEvent.objects.count() == before

    def test_success_records_audit_and_outbox_atomically(self, make_user):
        admin = make_user("nadia@example.org")
        target = make_user("kevin@example.org")
        ctx = _admin_ctx(admin.id)
        result = _rename_user(ctx, user_id=target.id, new_name="Kevin T.")
        assert result == "Kevin T."
        event = AuditEvent.objects.get(target_id=str(target.id))
        assert event.action == "user.identity_updated"
        assert event.actor_user_id == admin.id
        assert event.rules_version
        assert OutboxEvent.objects.filter(event_type="UserProfileUpdated").exists()

    def test_exception_in_service_rolls_back_change_audit_and_outbox(self, make_user):
        admin = make_user("nadia@example.org")
        target = make_user("kevin@example.org")
        ctx = _admin_ctx(admin.id)
        events_before = OutboxEvent.objects.count()
        audit_before = AuditEvent.objects.count()
        with pytest.raises(RuntimeError):
            _rename_user(ctx, user_id=target.id, new_name="Kevin T.", blow_up=True)
        assert AuditEvent.objects.count() == audit_before
        assert OutboxEvent.objects.count() == events_before

    def test_impersonation_blocked_action_is_audited_and_raises(self, make_user):
        admin = make_user("nadia@example.org")
        target = make_user("kevin@example.org")
        ctx = ActorContext(
            user_id=admin.id,
            real_user_id=None,
            roles=frozenset({roles.ADMINISTRATOR}),
            is_active=True,
            mfa_satisfied=True,
            impersonation_id=uuid.uuid4(),
        )
        with pytest.raises(ImpersonationBlocked):
            from ham.identity.services import disable_user

            disable_user(ctx, user_id=target.id)
        event = AuditEvent.objects.filter(action="impersonation.action_blocked").latest("seq")
        assert event.target_id == "user.disable"

    def test_step_up_required_raises_without_recording(self, make_user):
        admin = make_user("nadia@example.org")
        target = make_user("kevin@example.org")
        ctx = ActorContext(
            user_id=admin.id,
            real_user_id=None,
            roles=frozenset({roles.ADMINISTRATOR}),
            is_active=True,
            mfa_satisfied=True,
        )
        audit_before = AuditEvent.objects.count()
        with pytest.raises(StepUpRequired):
            from ham.identity.services import grant_global_role

            grant_global_role(ctx, user_id=target.id, role=roles.VOLUNTEER)
        assert AuditEvent.objects.count() == audit_before

    def test_denied_privileged_action_writes_authz_denied(self, make_user):
        volunteer = make_user("kevin@example.org")
        ctx = ActorContext(
            user_id=volunteer.id,
            real_user_id=None,
            roles=frozenset({roles.VOLUNTEER}),
            is_active=True,
            mfa_satisfied=True,
        )
        with pytest.raises(PermissionDenied):
            from ham.identity.services import disable_user

            disable_user(ctx, user_id=volunteer.id)
        assert AuditEvent.objects.filter(action="authz.denied").exists()
