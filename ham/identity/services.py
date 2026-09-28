"""Identity service functions (foundation.md §2.3 "Users and roles").

Every consequential action is wrapped in `@ham.authz.commands.command(...)` (the one write
path): authorize -> step-up -> impersonation block -> change + audit + outbox, atomically.
`bootstrap_administrator` and `seed_dev` are the two exceptions — there is no signed-in
`ActorContext` yet, so they record their own system-actor audit events directly.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction

from ham.audit.services import record as audit_record
from ham.authz import roles
from ham.authz.commands import CommandResult, OutboxSpec, PermissionDenied, command
from ham.authz.context import ActorContext
from ham.outbox.api import emit as outbox_emit
from ham.platform.clock import now as clock_now

from .models import ImpersonationSession, RoleAssignment, SharedIdentityProfile, User

# Least-privilege default for an invitation's role list (Q-037, Q-040 lineage): anyone who may
# invite gets at least Volunteer, without necessarily being able to grant every other role.
DEFAULT_INVITE_ROLES = (roles.VOLUNTEER,)


# ---------------------------------------------------------------------------------------
# System-actor operations (no ActorContext exists yet)
# ---------------------------------------------------------------------------------------
def bootstrap_administrator(email: str) -> User:
    """Create the first production Administrator (foundation.md §2.11), audited with actor
    `system:bootstrap`. Idempotent: re-running with the same email adds the Administrator
    role if missing rather than erroring, so a botched first run can be safely retried."""
    email = email.strip().lower()
    with transaction.atomic():
        user, created = User.objects.get_or_create(email=email)
        if created:
            user.set_unusable_password()
            user.save()
        SharedIdentityProfile.objects.get_or_create(user=user)
        has_admin = RoleAssignment.objects.filter(
            user=user, role=roles.ADMINISTRATOR, revoked_at__isnull=True
        ).exists()
        if not has_admin:
            RoleAssignment.objects.create(
                user=user,
                role=roles.ADMINISTRATOR,
                granted_by_id=None,
                granted_at=clock_now(),
                grant_reason="bootstrap",
            )
        audit_record(
            ctx=None,
            actor_type="system",
            actor_user_id=None,
            action="user.created",
            target_type="user",
            target_id=str(user.id),
            after={"roles": [roles.ADMINISTRATOR]},
            context={"system_actor": "system:bootstrap"},
        )
        outbox_emit(
            "UserCreated",
            aggregate_type="user",
            aggregate_id=user.id,
            payload={"roles": [roles.ADMINISTRATOR]},
        )
    return user


# ---------------------------------------------------------------------------------------
# Role-grant guardrails shared by invite_user and grant_global_role (Q-041, Q-055)
# ---------------------------------------------------------------------------------------
_DIRECTOR_GRANT_REASON_REQUIRED = frozenset({roles.PASTOR, roles.BOARD_REPRESENTATIVE})


def _check_can_grant(ctx: ActorContext, role: str, reason: str) -> None:
    """Raises ValueError/PermissionDenied if `ctx` may not grant `role` (Q-041, Q-055).

    The matrix already restricts `role.grant_global`/`role.revoke_global` to Administrator and
    Director; this enforces the *finer* rule of which roles a Director specifically may grant.
    """
    granter_roles = ctx.effective_roles
    if roles.ADMINISTRATOR in granter_roles:
        return  # Administrator: every role (never own; checked by the caller)
    if roles.HAM_DIRECTOR in granter_roles:
        if role == roles.ADMINISTRATOR:
            raise PermissionDenied(
                "role.grant_global: only an Administrator may grant Administrator (Q-041)"
            )
        if role in _DIRECTOR_GRANT_REASON_REQUIRED and not reason.strip():
            raise ValueError(
                "role.grant_global: granting Pastor or Board representative requires the "
                "authorizing body (Board or pastoral staff) as the reason (Q-055)"
            )
        return
    raise PermissionDenied("role.grant_global: no held role may grant roles")  # pragma: no cover


def _count_active_administrators(*, exclude_user_id: uuid.UUID | None = None) -> int:
    qs = RoleAssignment.objects.filter(
        role=roles.ADMINISTRATOR,
        revoked_at__isnull=True,
        user__is_active=True,
        user__disabled_at__isnull=True,
    )
    if exclude_user_id is not None:
        qs = qs.exclude(user_id=exclude_user_id)
    return qs.values("user_id").distinct().count()


# ---------------------------------------------------------------------------------------
# Invitation (Q-037: Admin, Director, Assistant Director may invite)
# ---------------------------------------------------------------------------------------
def _resource_self(ctx: ActorContext, *args: Any, **kwargs: Any) -> ActorContext:
    return ctx


@command("user.invite")
def invite_user(
    ctx: ActorContext,
    *,
    email: str,
    first_name: str,
    last_name: str,
    role_list: tuple[str, ...] = DEFAULT_INVITE_ROLES,
    reason: str = "",
) -> CommandResult:
    email = email.strip().lower()
    role_list = tuple(role_list) or DEFAULT_INVITE_ROLES
    for role in role_list:
        if role not in roles.GLOBAL_ROLES:
            raise ValueError(f"{role!r} is not an invitable global role")
        # PRD-GAP Q-082: the PRD doesn't spell out which roles an Assistant Director may
        # invite with (Q-037 names AD as an inviter but Q-041's grant list is Admin/Director
        # only). Least privilege: an Assistant Director may only invite as Volunteer; a
        # Director follows the same Q-041/Q-055 rules as a direct role grant.
        if roles.ASSISTANT_DIRECTOR in ctx.effective_roles and roles.ADMINISTRATOR not in (
            ctx.effective_roles
        ):
            if role != roles.VOLUNTEER:
                raise PermissionDenied(
                    "user.invite: an Assistant Director may only invite as Volunteer "
                    "(PRD-GAP Q-082)"
                )
        else:
            _check_can_grant(ctx, role, reason)

    with transaction.atomic():
        user = User.objects.create(email=email)
        user.set_unusable_password()
        user.save()
        SharedIdentityProfile.objects.create(
            user=user, full_name=f"{first_name.strip()} {last_name.strip()}".strip()
        )
        for role in role_list:
            RoleAssignment.objects.create(
                user=user,
                role=role,
                granted_by_id=ctx.user_id,
                granted_at=clock_now(),
                grant_reason=reason,
            )
    return CommandResult(
        value=user,
        audit_action="user.created",
        target_type="user",
        target_id=str(user.id),
        after={"roles": list(role_list)},
        reason=reason,
        outbox=OutboxSpec(
            "UserCreated",
            aggregate_type="user",
            aggregate_id=user.id,
            payload={"roles": list(role_list), "invited_by": str(ctx.user_id)},
        ),
    )


# ---------------------------------------------------------------------------------------
# Identity fields
# ---------------------------------------------------------------------------------------
@command("me.update", resource_from=_resource_self)
def update_own_profile(
    ctx: ActorContext, *, full_name: str | None = None, mobile_phone: str | None = None
) -> CommandResult:
    assert ctx.user_id is not None  # me.update requires authentication (matrix: shell.use+)
    profile = SharedIdentityProfile.objects.select_for_update().get(user_id=ctx.user_id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    if full_name is not None and full_name != profile.full_name:
        before["full_name_changed"] = True
        profile.full_name = full_name
        after["full_name_changed"] = True
    if mobile_phone is not None and mobile_phone != profile.mobile_phone:
        before["mobile_phone_changed"] = True
        profile.mobile_phone = mobile_phone
        after["mobile_phone_changed"] = True
    profile.save()
    return CommandResult(
        value=profile,
        audit_action="profile.updated",
        target_type="user",
        target_id=str(ctx.user_id),
        before=before,
        after=after,
    )


@command("user.update_identity")
def update_identity(
    ctx: ActorContext,
    *,
    user_id: uuid.UUID,
    full_name: str | None = None,
    mobile_phone: str | None = None,
) -> CommandResult:
    profile = SharedIdentityProfile.objects.select_for_update().get(user_id=user_id)
    changed: list[str] = []
    if full_name is not None and full_name != profile.full_name:
        profile.full_name = full_name
        changed.append("full_name")
    if mobile_phone is not None and mobile_phone != profile.mobile_phone:
        profile.mobile_phone = mobile_phone
        changed.append("mobile_phone")
    profile.save()
    return CommandResult(
        value=profile,
        audit_action="user.identity_updated",
        target_type="user",
        target_id=str(user_id),
        after={"changed_fields": changed},
        outbox=OutboxSpec(
            "UserProfileUpdated",
            aggregate_type="user",
            aggregate_id=user_id,
            payload={"changed_fields": changed},
        ),
    )


# ---------------------------------------------------------------------------------------
# Disable / enable (Q-035: never self, never the last active Administrator)
# ---------------------------------------------------------------------------------------
@command("user.disable")
def disable_user(ctx: ActorContext, *, user_id: uuid.UUID, reason: str = "") -> CommandResult:
    if user_id == ctx.user_id:
        raise PermissionDenied("user.disable: you cannot disable your own account")
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)
        is_admin = RoleAssignment.objects.filter(
            user=user, role=roles.ADMINISTRATOR, revoked_at__isnull=True
        ).exists()
        if is_admin and _count_active_administrators(exclude_user_id=user_id) == 0:
            raise ValueError(
                "user.disable: HAM refuses to disable the last active Administrator (Q-035)"
            )
        user.is_active = False
        user.disabled_at = clock_now()
        user.disabled_by_id = ctx.user_id
        user.save(update_fields=["is_active", "disabled_at", "disabled_by_id"])
    # PRD-GAP Q-052: cancelling the person's future commitments (no reliability effect) is a
    # staffing-module concern that doesn't exist yet in step 1; UserDisabled is emitted so
    # that module can react once it lands.
    return CommandResult(
        value=user,
        audit_action="user.disabled",
        target_type="user",
        target_id=str(user_id),
        before={"is_active": True},
        after={"is_active": False},
        reason=reason,
        outbox=OutboxSpec("UserDisabled", aggregate_type="user", aggregate_id=user_id, payload={}),
    )


@command("user.enable")
def enable_user(ctx: ActorContext, *, user_id: uuid.UUID, reason: str = "") -> CommandResult:
    user = User.objects.select_for_update().get(pk=user_id)
    user.is_active = True
    user.disabled_at = None
    user.disabled_by_id = None
    user.save(update_fields=["is_active", "disabled_at", "disabled_by_id"])
    return CommandResult(
        value=user,
        audit_action="user.enabled",
        target_type="user",
        target_id=str(user_id),
        before={"is_active": False},
        after={"is_active": True},
        reason=reason,
        outbox=OutboxSpec("UserEnabled", aggregate_type="user", aggregate_id=user_id, payload={}),
    )


# ---------------------------------------------------------------------------------------
# Global roles (Q-041, Q-047, Q-055)
# ---------------------------------------------------------------------------------------
@command("role.grant_global")
def grant_global_role(
    ctx: ActorContext, *, user_id: uuid.UUID, role: str, reason: str = ""
) -> CommandResult:
    if role not in roles.GLOBAL_ROLES:
        raise ValueError(f"{role!r} is not a global role")
    if user_id == ctx.user_id:
        raise PermissionDenied("role.grant_global: nobody may grant themselves a role (Q-047)")
    _check_can_grant(ctx, role, reason)

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)
        assignment = RoleAssignment.objects.create(
            user=user,
            role=role,
            granted_by_id=ctx.user_id,
            granted_at=clock_now(),
            grant_reason=reason,
        )
    return CommandResult(
        value=assignment,
        audit_action="role.granted",
        target_type="user",
        target_id=str(user_id),
        after={"role": role, "assignment_id": str(assignment.id)},
        reason=reason,
        # Q-041/Q-055: every grant emails all Administrators; S4's email adapter subscribes
        # to this event once it lands (deferred, foundation.md §2.6 outbox seam).
        outbox=OutboxSpec(
            "RoleGranted",
            aggregate_type="user",
            aggregate_id=user_id,
            payload={"role": role, "granted_by": str(ctx.user_id)},
        ),
    )


@command("role.revoke_global")
def revoke_global_role(
    ctx: ActorContext, *, assignment_id: uuid.UUID, reason: str = ""
) -> CommandResult:
    with transaction.atomic():
        assignment = RoleAssignment.objects.select_for_update().get(
            pk=assignment_id, scope_type__isnull=True, revoked_at__isnull=True
        )
        if assignment.user_id == ctx.user_id:
            raise PermissionDenied("role.revoke_global: nobody may remove their own role (Q-047)")
        _check_can_grant(ctx, assignment.role, reason)
        if (
            assignment.role == roles.ADMINISTRATOR
            and _count_active_administrators(exclude_user_id=assignment.user_id) == 0
        ):
            raise ValueError(
                "role.revoke_global: HAM refuses to remove the last active Administrator "
                "(Q-035, Q-047)"
            )
        assignment.revoked_at = clock_now()
        assignment.revoked_by_id = ctx.user_id
        assignment.revoke_reason = reason
        assignment.save(update_fields=["revoked_at", "revoked_by_id", "revoke_reason"])
    return CommandResult(
        value=assignment,
        audit_action="role.revoked",
        target_type="user",
        target_id=str(assignment.user_id),
        before={"role": assignment.role},
        after={"role": None},
        reason=reason,
        outbox=OutboxSpec(
            "RoleRevoked",
            aggregate_type="user",
            aggregate_id=assignment.user_id,
            payload={"role": assignment.role, "revoked_by": str(ctx.user_id)},
        ),
    )


# ---------------------------------------------------------------------------------------
# Project / Task Leader (Q-039, Q-054: Director and Assistant Director only, not Admin)
# ---------------------------------------------------------------------------------------
def _assign_leader(
    ctx: ActorContext, *, role: str, scope_type: str, scope_id: uuid.UUID, user_id: uuid.UUID
) -> RoleAssignment:
    with transaction.atomic():
        RoleAssignment.objects.filter(
            role=role, scope_type=scope_type, scope_id=scope_id, revoked_at__isnull=True
        ).update(revoked_at=clock_now(), revoked_by_id=ctx.user_id, revoke_reason="reassigned")
        assignment = RoleAssignment.objects.create(
            user_id=user_id,
            role=role,
            scope_type=scope_type,
            scope_id=scope_id,
            granted_by_id=ctx.user_id,
            granted_at=clock_now(),
        )
    return assignment


@command("leader.project.assign")
def assign_project_leader(
    ctx: ActorContext, *, project_id: uuid.UUID, user_id: uuid.UUID
) -> CommandResult:
    assignment = _assign_leader(
        ctx,
        role=roles.PROJECT_LEADER,
        scope_type=roles.SCOPE_TYPE_PROJECT,
        scope_id=project_id,
        user_id=user_id,
    )
    return CommandResult(
        value=assignment,
        audit_action="leader.project_assigned",
        target_type="project",
        target_id=str(project_id),
        project_id=project_id,
        after={"user_id": str(user_id)},
        outbox=OutboxSpec(
            "ProjectLeaderAssigned",
            aggregate_type="project",
            aggregate_id=project_id,
            payload={"user_id": str(user_id)},
        ),
    )


@command("leader.project.revoke")
def revoke_project_leader(ctx: ActorContext, *, project_id: uuid.UUID) -> CommandResult:
    with transaction.atomic():
        assignment = RoleAssignment.objects.select_for_update().get(
            role=roles.PROJECT_LEADER,
            scope_type=roles.SCOPE_TYPE_PROJECT,
            scope_id=project_id,
            revoked_at__isnull=True,
        )
        assignment.revoked_at = clock_now()
        assignment.revoked_by_id = ctx.user_id
        assignment.save(update_fields=["revoked_at", "revoked_by_id"])
    return CommandResult(
        value=assignment,
        audit_action="leader.project_revoked",
        target_type="project",
        target_id=str(project_id),
        project_id=project_id,
        before={"user_id": str(assignment.user_id)},
        outbox=OutboxSpec(
            "ProjectLeaderRevoked",
            aggregate_type="project",
            aggregate_id=project_id,
            payload={"user_id": str(assignment.user_id)},
        ),
    )


@command("leader.task.assign")
def assign_task_leader(
    ctx: ActorContext, *, task_id: uuid.UUID, user_id: uuid.UUID
) -> CommandResult:
    assignment = _assign_leader(
        ctx,
        role=roles.TASK_LEADER,
        scope_type=roles.SCOPE_TYPE_TASK,
        scope_id=task_id,
        user_id=user_id,
    )
    return CommandResult(
        value=assignment,
        audit_action="leader.task_assigned",
        target_type="task",
        target_id=str(task_id),
        after={"user_id": str(user_id)},
        outbox=OutboxSpec(
            "TaskLeaderAssigned",
            aggregate_type="task",
            aggregate_id=task_id,
            payload={"user_id": str(user_id)},
        ),
    )


# ---------------------------------------------------------------------------------------
# Impersonation (§59, Q-034, Q-049, Q-053)
# ---------------------------------------------------------------------------------------
@command("impersonation.start")
def start_impersonation(
    ctx: ActorContext, *, target_user_id: uuid.UUID, reason: str
) -> CommandResult:
    if not reason.strip():
        raise ValueError("impersonation.start: a reason is required (§59)")
    if target_user_id == ctx.user_id:
        raise PermissionDenied("impersonation.start: you cannot troubleshoot as yourself")
    assert ctx.user_id is not None
    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=target_user_id)
        if not target.is_active or target.is_disabled:
            raise ValueError("impersonation.start: cannot troubleshoot as a turned-off account")
        target_is_admin = RoleAssignment.objects.filter(
            user=target, role=roles.ADMINISTRATOR, revoked_at__isnull=True
        ).exists()
        if target_is_admin:
            raise PermissionDenied(
                "impersonation.start: cannot troubleshoot as another Administrator (Q-034)"
            )
        now = clock_now()
        session = ImpersonationSession.objects.create(
            admin_user_id=ctx.user_id,
            target_user_id=target_user_id,
            reason=reason,
            started_at=now,
            last_activity_at=now,
        )
    return CommandResult(
        value=session,
        audit_action="impersonation.started",
        target_type="user",
        target_id=str(target_user_id),
        reason=reason,
        after={"impersonation_id": str(session.id)},
    )


@command("impersonation.stop")
def stop_impersonation(
    ctx: ActorContext, *, end_reason: str = ImpersonationSession.END_REASON_MANUAL
) -> CommandResult:
    assert ctx.impersonation_id is not None
    with transaction.atomic():
        session = ImpersonationSession.objects.select_for_update().get(
            pk=ctx.impersonation_id, ended_at__isnull=True
        )
        now = clock_now()
        duration_seconds = int((now - session.started_at).total_seconds())
        session.ended_at = now
        session.end_reason = end_reason
        session.save(update_fields=["ended_at", "end_reason"])
    return CommandResult(
        value=session,
        audit_action="impersonation.ended",
        target_type="user",
        target_id=str(session.target_user_id),
        after={"end_reason": end_reason, "duration_seconds": duration_seconds},
    )


# ---------------------------------------------------------------------------------------
# Church profile (Q-007, S3a build note left this to S3b) and outbox retry (S4 seam)
# ---------------------------------------------------------------------------------------
@command("church_profile.update")
def update_church_profile(
    ctx: ActorContext,
    *,
    ham_phone: str | None = None,
    ham_email: str | None = None,
    time_zone: str | None = None,
    website_url: str | None = None,
) -> CommandResult:
    from ham.platform.models import ChurchProfile

    profile = ChurchProfile.objects.select_for_update().get(pk=ChurchProfile.get_solo().pk)
    changed: list[str] = []
    for field, value in (
        ("ham_phone", ham_phone),
        ("ham_email", ham_email),
        ("time_zone", time_zone),
        ("website_url", website_url),
    ):
        if value is not None and getattr(profile, field) != value:
            setattr(profile, field, value)
            changed.append(field)
    profile.updated_by_id = ctx.user_id
    profile.save()
    return CommandResult(
        value=profile,
        audit_action="church_profile.updated",
        target_type="church_profile",
        target_id=str(profile.pk),
        after={"changed_fields": changed},
    )


@command("outbox.retry")
def retry_outbox_delivery(ctx: ActorContext, *, delivery_id: uuid.UUID) -> CommandResult:
    from ham.outbox.services import retry_delivery

    retry_delivery(delivery_id)
    return CommandResult(
        value=None,
        audit_action="outbox.retried",
        target_type="outbox_delivery",
        target_id=str(delivery_id),
    )


# ---------------------------------------------------------------------------------------
# Me -> Sign-in & security: regenerate recovery codes (step-up; docs/ux/auth-and-access.md F)
# ---------------------------------------------------------------------------------------
@command("me.recovery_codes.regenerate", resource_from=_resource_self)
def regenerate_own_recovery_codes(ctx: ActorContext) -> CommandResult:
    from . import mfa

    assert ctx.user_id is not None
    user = User.objects.get(pk=ctx.user_id)
    if not mfa.is_enrolled(user):
        raise ValueError("me.recovery_codes.regenerate: two-step sign-in isn't set up yet")
    codes = mfa.regenerate_recovery_codes(user)
    return CommandResult(
        value=codes,
        audit_action="auth.mfa.recovery_codes_regenerated",
        target_type="user",
        target_id=str(ctx.user_id),
    )


@command("leader.task.revoke")
def revoke_task_leader(ctx: ActorContext, *, task_id: uuid.UUID) -> CommandResult:
    with transaction.atomic():
        assignment = RoleAssignment.objects.select_for_update().get(
            role=roles.TASK_LEADER,
            scope_type=roles.SCOPE_TYPE_TASK,
            scope_id=task_id,
            revoked_at__isnull=True,
        )
        assignment.revoked_at = clock_now()
        assignment.revoked_by_id = ctx.user_id
        assignment.save(update_fields=["revoked_at", "revoked_by_id"])
    return CommandResult(
        value=assignment,
        audit_action="leader.task_revoked",
        target_type="task",
        target_id=str(task_id),
        before={"user_id": str(assignment.user_id)},
        outbox=OutboxSpec(
            "TaskLeaderRevoked",
            aggregate_type="task",
            aggregate_id=task_id,
            payload={"user_id": str(assignment.user_id)},
        ),
    )
