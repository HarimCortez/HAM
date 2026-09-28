"""``ActorContext``: everything the policy engine needs about "who is asking", built fresh on
every request by ``ham.identity.middleware.ActorContextMiddleware`` (foundation.md §1, §7).

Every module except ``ham.identity`` receives this instead of reading User/RoleAssignment
tables directly. Domain code must never import ``django.contrib.auth`` models; it takes an
``ActorContext`` as the first argument of every ``@command``-wrapped service function.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

from .roles import MFA_REQUIRED_ROLES

# Session keys S3b (auth) must use so this middleware and the step-up/impersonation logic here
# agree with the sign-in/MFA/impersonation flows built in the next slice.
SESSION_KEY_IMPERSONATION_ID = "ham_impersonation_id"
SESSION_KEY_MFA_SATISFIED = "ham_mfa_satisfied"
# Maps step-up "kind" (ham.rules.RULES.auth.STEP_UP_ACTIONS' second element) -> ISO8601 UTC
# timestamp of the last successful step-up of that kind, in this session.
SESSION_KEY_STEP_UP = "ham_step_up_at"


@dataclass(frozen=True, slots=True)
class ScopedRole:
    """One active project- or task-scoped role held by the actor (RoleAssignment row)."""

    role: str
    scope_type: str
    scope_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ActorContext:
    """Immutable snapshot of the acting identity for one request (foundation.md §1, §59).

    ``user_id`` is the *effective* identity (the impersonation target, if any).
    ``real_user_id`` is the actual signed-in person, set only while impersonating, so every
    audit event can record both (foundation.md §3 AuditEvent).
    """

    user_id: uuid.UUID | None
    real_user_id: uuid.UUID | None
    roles: frozenset[str]
    scoped_roles: tuple[ScopedRole, ...] = ()
    is_active: bool = False
    mfa_satisfied: bool = False
    impersonation_id: uuid.UUID | None = None
    step_up_at: dict[str, dt.datetime] = field(default_factory=dict)
    # Populated by `ham.identity.middleware` only while impersonating, purely so the shell
    # banner (`web/base.html`, docs/ux/auth-and-access.md I2) has what it needs without
    # `ham.web` ever querying identity tables directly (foundation.md §1: "only ham.identity
    # reads auth tables").
    impersonation_reason: str = ""
    target_display_name: str = ""
    impersonation_last_activity_at: dt.datetime | None = None

    @classmethod
    def anonymous(cls) -> ActorContext:
        return cls(user_id=None, real_user_id=None, roles=frozenset(), is_active=False)

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    @property
    def is_impersonating(self) -> bool:
        return self.impersonation_id is not None

    @property
    def effective_roles(self) -> frozenset[str]:
        """Roles that currently grant permissions.

        Q-045: a role requiring two-step sign-in is recorded immediately but its permissions
        activate only once the person has enrolled/verified MFA this session
        (``mfa_satisfied``). Until then, any non-MFA roles the person also holds still apply.
        """
        if self.mfa_satisfied:
            return self.roles
        return frozenset(r for r in self.roles if r not in MFA_REQUIRED_ROLES)

    def has_fresh_step_up(self, kind: str, *, now: dt.datetime, freshness: dt.timedelta) -> bool:
        """Whether a step-up of this ``kind`` succeeded within ``freshness`` (Q-010, Q-046)."""
        last = self.step_up_at.get(kind)
        if last is None:
            return False
        return now - last <= freshness

    @property
    def impersonation_idle_minutes_left(self) -> int:
        """Minutes before the impersonation session auto-ends (§59; `web/base.html` banner).
        0 when not impersonating or the middleware hasn't supplied a last-activity time."""
        if self.impersonation_last_activity_at is None:
            return 0
        from ham.platform.clock import now as clock_now
        from ham.rules import RULES

        remaining = RULES.auth.IMPERSONATION_IDLE_TIMEOUT - (
            clock_now() - self.impersonation_last_activity_at
        )
        return max(0, int(remaining.total_seconds() // 60))


# --- S2.0 (intake.md §5): pseudo-principals for requester- and system-initiated writes -------
#
# The command pipeline (`ham.authz.commands.command()`) is the *one* write path (foundation.md
# §1). Requests submitted by a member of the public, and background jobs acting on their own
# behalf ("the duplicate check finished", "purge this expired draft"), both need to go through
# that same pipeline — authorized, audited, emitted — without pretending to be a signed-in
# `User`. `RequesterContext`/`SystemContext` are duck-type-compatible with `ActorContext`
# (`ham.authz.matrix.authorize` and `ham.audit.services.record` only ever call attributes/
# properties both shapes provide) rather than subclassing it, since neither has a `user_id`
# that means "a HAM staff account", nor impersonation, nor MFA.
#
# `roles={"REQUESTER"}` / `{"SYSTEM"}` are deliberately NOT in `ham.authz.roles.GLOBAL_ROLES`
# or `ANY_STANDING_ROLE` (intake.md §5): a requester or a background job must never reach
# `shell.use`, `me.*`, or any staff-only action just because its role string happens to appear
# in a matrix rule's `allowed_roles` — every action either pseudo-context can perform is
# declared explicitly for `REQUESTER`/`SYSTEM` in `ham.authz.matrix.MATRIX`.
@dataclass(frozen=True, slots=True)
class RequesterContext:
    """The acting identity for a public requester's own writes (submitting the form, uploading
    their own media, regenerating their own link) — intake.md §5.

    ``request_id`` is the request this session is scoped to (via a verified access link or, for
    the very first ``request.submit`` before the request row exists, ``None``); ``Scope.
    OWN_REQUEST`` compares it to a resource's own ``request_id``, never to a ``user_id`` (a
    requester has no ``User`` row at all — intake.md §3 ``Requester`` "not a User").
    """

    request_id: uuid.UUID | None
    link_id: uuid.UUID | None = None
    verification_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    real_user_id: uuid.UUID | None = None
    roles: frozenset[str] = field(default_factory=lambda: frozenset({"REQUESTER"}))
    scoped_roles: tuple[ScopedRole, ...] = ()
    is_active: bool = True
    step_up_at: dict[str, dt.datetime] = field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_impersonating(self) -> bool:
        return False

    @property
    def effective_roles(self) -> frozenset[str]:
        # No MFA concept for a requester session (Q-045 only governs staff MFA-required
        # roles); the role always applies once the link/verification checks in the service
        # layer have passed.
        return self.roles

    def has_fresh_step_up(self, kind: str, *, now: dt.datetime, freshness: dt.timedelta) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class SystemContext:
    """The acting identity for a background job doing its own work with no human behind it
    (e.g. the duplicate-check job moving a request to Awaiting Approval, a retention purge) —
    intake.md §5 ``system.*`` actions. There is exactly one of these per call; jobs construct a
    fresh one, they are never stored."""

    user_id: uuid.UUID | None = None
    real_user_id: uuid.UUID | None = None
    roles: frozenset[str] = field(default_factory=lambda: frozenset({"SYSTEM"}))
    scoped_roles: tuple[ScopedRole, ...] = ()
    is_active: bool = True
    step_up_at: dict[str, dt.datetime] = field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_impersonating(self) -> bool:
        return False

    @property
    def effective_roles(self) -> frozenset[str]:
        return self.roles

    def has_fresh_step_up(self, kind: str, *, now: dt.datetime, freshness: dt.timedelta) -> bool:
        return False
