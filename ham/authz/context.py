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
