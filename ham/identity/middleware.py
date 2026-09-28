"""Builds `request.actor` (an `ActorContext`) on every request (foundation.md §1, §7).

Must run after `AuthenticationMiddleware` (needs `request.user`) and before
`ham.authz.guard.RouteGuardMiddleware` (needs `request.actor`) — see `config/settings/base.py`.

Session key contract for S3b (auth/MFA/impersonation) and S5 (screens) to write to:
- `ham_impersonation_id`: the active `ImpersonationSession.id` (str), or absent.
- `ham_mfa_satisfied`: bool — true once the signed-in person has verified TOTP/a recovery
  code this session (Q-045: before that, MFA-role permissions are inactive).
- `ham_step_up_at`: dict of step-up "kind" (see `ham.rules.RULES.auth.STEP_UP_ACTIONS`) to an
  ISO 8601 UTC timestamp string of the last successful step-up of that kind.
- `ham_session_epoch` (security review H3, UX M8, added S3b follow-up): the signed-in
  (real) user's `User.session_epoch` value *at sign-in* (`ham.identity.authn.complete_sign_in`
  sets it). Compared against the current DB value on every request
  (`SessionLifetimeMiddleware._enforce_session_epoch`); a mismatch force-ends the session. Any
  code that must invalidate every existing session for a user (MFA reset/replace, "sign out
  everywhere") increments `User.session_epoch` — never delete Django sessions directly, there
  is no server-side session index to find them all by user.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

from django.contrib.auth import logout as django_logout
from django.http import HttpRequest, HttpResponse

from ham.audit.services import record as audit_record
from ham.authz.context import (
    SESSION_KEY_IMPERSONATION_ID,
    SESSION_KEY_MFA_SATISFIED,
    SESSION_KEY_STEP_UP,
    ActorContext,
    ScopedRole,
)
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from .models import ImpersonationSession, RoleAssignment, SharedIdentityProfile, User

SESSION_KEY_STARTED_AT = "ham_session_started_at"
SESSION_KEY_LAST_ACTIVITY = "ham_last_activity"
SESSION_KEY_EPOCH = "ham_session_epoch"


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
    impersonation_reason = ""
    target_display_name = ""
    impersonation_last_activity_at: dt.datetime | None = None

    if impersonation_id_raw:
        session = ImpersonationSession.objects.filter(
            id=impersonation_id_raw, ended_at__isnull=True, admin_user_id=real_user.id
        ).first()
        if session is not None:
            target = User.objects.filter(pk=session.target_user_id).first()
            if target is not None and target.is_active and not target.is_disabled:
                effective_user = target
                impersonation_uuid = session.id
                impersonation_reason = session.reason
                impersonation_last_activity_at = session.last_activity_at
                profile = SharedIdentityProfile.objects.filter(user_id=target.id).first()
                target_display_name = profile.display_name if profile else target.email
        # An invalid/expired/mismatched session id is treated as "not impersonating" rather
        # than an error — the sign-out/impersonation views are responsible for clearing the
        # session key when it ends (`ham.identity.services.stop_impersonation`,
        # `SessionLifetimeMiddleware` below for the idle-timeout case).

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
        impersonation_reason=impersonation_reason,
        target_display_name=target_display_name,
        impersonation_last_activity_at=impersonation_last_activity_at,
    )


class ActorContextMiddleware:
    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.actor = build_actor_context(request)  # type: ignore[attr-defined]
        return self.get_response(request)


class SessionLifetimeMiddleware:
    """Enforces session lifetimes (Q-032) and the impersonation idle timeout (§59, Q-053).

    Must run after `AuthenticationMiddleware`/`ActorContextMiddleware` are already correct for
    *this* request's decision (it reads `request.actor` and `request.user`) but *before* the
    route guard, so an expired session is signed out before any view runs. Placed in
    `config/settings/base.py`'s `MIDDLEWARE` right after `ActorContextMiddleware`.
    """

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            if self._enforce_session_epoch(request):
                # Security review H3/UX M8: the session was just force-ended (an MFA
                # reset/replace or "sign out everywhere" happened on some other device) —
                # nothing else in this middleware (idle lifetime, impersonation idle) applies
                # to a request that is now anonymous.
                return self.get_response(request)
            self._enforce_session_lifetime(request)
        actor = getattr(request, "actor", None)
        if actor is not None and actor.is_impersonating:
            self._enforce_impersonation_idle(request, actor)
        return self.get_response(request)

    def _enforce_session_epoch(self, request: HttpRequest) -> bool:
        """Security review H3, UX M8: compares the epoch captured at sign-in
        (`ham.identity.authn.complete_sign_in`) against the *real* signed-in user's current
        `session_epoch`. A mismatch means an Administrator reset/replaced this person's MFA,
        or the person used "Sign out everywhere" from a different session — either way, this
        session must stop being privileged immediately, not merely on its next idle check.
        Returns True if the session was just force-ended."""
        stored = request.session.get(SESSION_KEY_EPOCH)
        if stored is None:
            return False
        real_user: User = request.user  # type: ignore[assignment]
        current = (
            User.objects.filter(pk=real_user.id).values_list("session_epoch", flat=True).first()
        )
        if current is not None and int(stored) != int(current):
            django_logout(request)
            request.actor = ActorContext.anonymous()  # type: ignore[attr-defined]
            return True
        return False

    def _enforce_session_lifetime(self, request: HttpRequest) -> None:
        now = clock_now()
        started_raw = request.session.get(SESSION_KEY_STARTED_AT)
        last_raw = request.session.get(SESSION_KEY_LAST_ACTIVITY)
        actor = getattr(request, "actor", None)
        # PRD-guardian review Major 6(b): while impersonating, `ActorContext.roles` reflects
        # the *target*'s roles, not the real Admin's — session lifetime must still use the
        # real Admin's own MFA-role limits (an Admin is always an MFA role, foundation.md §8
        # owner-decisions box), never whatever the target happens to hold.
        if actor is not None and actor.is_impersonating and actor.real_user_id is not None:
            real_roles = set(
                RoleAssignment.objects.filter(
                    user_id=actor.real_user_id, revoked_at__isnull=True, scope_type__isnull=True
                ).values_list("role", flat=True)
            )
        else:
            # Use the *held* roles (not `effective_roles`) so someone who hasn't finished MFA
            # enrollment yet still gets the shorter MFA-role session policy, not the standard
            # one.
            real_roles = set(actor.roles) if actor is not None else set()
        is_mfa_role = bool(real_roles & set(RULES.auth.MFA_REQUIRED_ROLES))
        idle_limit = (
            RULES.auth.SESSION_IDLE_LIFETIME_MFA_ROLES
            if is_mfa_role
            else RULES.auth.SESSION_IDLE_LIFETIME_STANDARD
        )
        expired = False
        if last_raw:
            try:
                last = dt.datetime.fromisoformat(last_raw)
                if now - last > idle_limit:
                    expired = True
            except ValueError:  # pragma: no cover - defensive
                pass
        if is_mfa_role and started_raw and not expired:
            try:
                started = dt.datetime.fromisoformat(started_raw)
                if now - started > RULES.auth.SESSION_ABSOLUTE_LIFETIME_MFA_ROLES:
                    expired = True
            except ValueError:  # pragma: no cover - defensive
                pass
        if expired:
            django_logout(request)
            request.actor = ActorContext.anonymous()  # type: ignore[attr-defined]
            return
        request.session[SESSION_KEY_LAST_ACTIVITY] = now.isoformat()

    def _enforce_impersonation_idle(self, request: HttpRequest, actor: ActorContext) -> None:
        assert actor.impersonation_id is not None  # guaranteed by the `is_impersonating` caller
        now = clock_now()
        session = ImpersonationSession.objects.filter(
            id=actor.impersonation_id, ended_at__isnull=True
        ).first()
        if session is None:
            request.session.pop(SESSION_KEY_IMPERSONATION_ID, None)
            return
        if now - session.last_activity_at > RULES.auth.IMPERSONATION_IDLE_TIMEOUT:
            session.ended_at = now
            session.end_reason = ImpersonationSession.END_REASON_IDLE_TIMEOUT
            session.save(update_fields=["ended_at", "end_reason"])
            request.session.pop(SESSION_KEY_IMPERSONATION_ID, None)
            audit_record(
                ctx=None,
                actor_type="system",
                actor_user_id=session.admin_user_id,
                acting_as_user_id=session.target_user_id,
                impersonation_id=session.id,
                action="impersonation.ended",
                target_type="user",
                target_id=str(session.target_user_id),
                after={"end_reason": ImpersonationSession.END_REASON_IDLE_TIMEOUT},
            )
            # PRD-guardian review Major 6(a) / security M1: rebuild `request.actor` right
            # away so the *rest of this same request* (the view that's about to run) sees the
            # real Admin, not the now-ended impersonation target — previously only the *next*
            # request picked this up.
            request.actor = build_actor_context(request)  # type: ignore[attr-defined]
        else:
            session.last_activity_at = now
            session.save(update_fields=["last_activity_at"])
