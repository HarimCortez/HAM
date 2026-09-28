"""Builds `request.actor` (an `ActorContext`) on every request (foundation.md §1, §7).

Must run after `AuthenticationMiddleware` (needs `request.user`) and before
`ham.authz.guard.RouteGuardMiddleware` (needs `request.actor`) — see `config/settings/base.py`.

Session key contract for S3b (auth/MFA/impersonation) and S5 (screens) to write to:
- `ham_impersonation_id`: the active `ImpersonationSession.id` (str), or absent.
- `ham_mfa_satisfied`: bool — true once the signed-in person has verified TOTP/a recovery
  code this session (Q-045: before that, MFA-role permissions are inactive).
- `ham_step_up_at`: dict of step-up "kind" (see `ham.rules.RULES.auth.STEP_UP_ACTIONS`) to an
  ISO 8601 UTC timestamp string of the last successful step-up of that kind.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from ham.authz.context import (
    SESSION_KEY_IMPERSONATION_ID,
    SESSION_KEY_MFA_SATISFIED,
    SESSION_KEY_STEP_UP,
    ActorContext,
    ScopedRole,
)

from .models import ImpersonationSession, RoleAssignment, User


def _parse_step_up(raw: dict[str, str]) -> dict[str, dt.datetime]:
    out: dict[str, dt.datetime] = {}
    for kind, value in raw.items():
        try:
            out[kind] = dt.datetime.fromisoformat(value)
        except (TypeError, ValueError):  # pragma: no cover - defensive against bad sessions
            continue
    return out


def build_actor_context(request: HttpRequest) -> ActorContext:
    django_user = getattr(request, "user", None)
    if django_user is None or not django_user.is_authenticated:
        return ActorContext.anonymous()

    real_user: User = django_user
    effective_user = real_user
    impersonation_id_raw = request.session.get(SESSION_KEY_IMPERSONATION_ID)
    impersonation_uuid: uuid.UUID | None = None

    if impersonation_id_raw:
        session = ImpersonationSession.objects.filter(
            id=impersonation_id_raw, ended_at__isnull=True, admin_user_id=real_user.id
        ).first()
        if session is not None:
            target = User.objects.filter(pk=session.target_user_id).first()
            if target is not None and target.is_active and not target.is_disabled:
                effective_user = target
                impersonation_uuid = session.id
        # An invalid/expired/mismatched session id is treated as "not impersonating" rather
        # than an error — S3b is responsible for clearing the session key when it ends.

    active_assignments = RoleAssignment.objects.filter(user=effective_user, revoked_at__isnull=True)
    roles = frozenset(
        active_assignments.filter(scope_type__isnull=True).values_list("role", flat=True)
    )
    scoped_roles = tuple(
        ScopedRole(role=a.role, scope_type=a.scope_type, scope_id=a.scope_id)
        for a in active_assignments.filter(scope_type__isnull=False)
        if a.scope_type is not None and a.scope_id is not None
    )

    return ActorContext(
        user_id=effective_user.id,
        real_user_id=real_user.id if impersonation_uuid else None,
        roles=roles,
        scoped_roles=scoped_roles,
        is_active=effective_user.is_active and not effective_user.is_disabled,
        mfa_satisfied=bool(request.session.get(SESSION_KEY_MFA_SATISFIED, False)),
        impersonation_id=impersonation_uuid,
        step_up_at=_parse_step_up(request.session.get(SESSION_KEY_STEP_UP, {})),
    )


class ActorContextMiddleware:
    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.actor = build_actor_context(request)  # type: ignore[attr-defined]
        return self.get_response(request)
