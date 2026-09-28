"""Ending an impersonation session (§59, Q-049, Q-053): the one function every end path
(manual "Stop", idle timeout, sign-out, the target's account being turned off) must funnel
through, so an ``ImpersonationEnded`` domain event — and the after-the-fact email to the
impersonated person it triggers (Q-049) — happen exactly once, from exactly one place, no
matter which path ended the session.

``ham.identity.services.stop_impersonation`` (the ``@command``-wrapped manual "Stop" action)
emits the same event through its own ``CommandResult`` (it already has an ``ActorContext`` and
records its own audit event that way). The other end paths don't have an ``ActorContext`` handy
(the idle timeout and sign-out fire outside/after the normal command pipeline) — they call
``end_impersonation``/``end_impersonation_for_session`` here instead of duplicating the
session-ending/audit logic:

- ``ham.identity.middleware.SessionLifetimeMiddleware._enforce_impersonation_idle`` (idle
  timeout) calls ``end_impersonation(session.id, reason=ImpersonationSession.
  END_REASON_IDLE_TIMEOUT)`` directly (it already has the ``ImpersonationSession``, not just a
  session id to look up).
- Every other place a browser session can end — ``ham.web.auth_views.sign_out``/
  ``sign_in_cancel`` (via their shared ``_end_session_fully``) and
  ``SessionLifetimeMiddleware``'s session-epoch/absolute-lifetime force-logouts (security
  review round 3, N1) — call ``end_impersonation_for_session(request, reason=...)``, which
  reads/clears ``request.session``'s impersonation key itself.
- ``sweep_idle_impersonation_sessions`` (a periodic job, security review round 3, N1) is the
  backstop for a session that never sends another request at all — every path above still only
  runs when *some* request comes in for that session.

``end_impersonations_for_target`` is ``disable_user``'s hook (Q-052: disabling someone must end
any impersonation of them, ``END_REASON_TARGET_DISABLED``).
"""

from __future__ import annotations

import uuid

from django.http import HttpRequest

from ham.audit.services import record as audit_record
from ham.authz.context import SESSION_KEY_IMPERSONATION_ID
from ham.outbox.api import emit as outbox_emit
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from .models import ImpersonationSession


def end_impersonation(
    session_id: uuid.UUID, *, reason: str = ImpersonationSession.END_REASON_MANUAL
) -> ImpersonationSession | None:
    """Ends one active impersonation session. Idempotent: returns ``None`` (no-op) if the
    session doesn't exist or is already ended, so callers on independent end paths (idle
    timeout racing a manual stop, a disable racing a sign-out) never double-record."""
    session = ImpersonationSession.objects.filter(pk=session_id, ended_at__isnull=True).first()
    if session is None:
        return None
    now = clock_now()
    duration_seconds = int((now - session.started_at).total_seconds())
    session.ended_at = now
    session.end_reason = reason
    session.save(update_fields=["ended_at", "end_reason"])
    audit_record(
        ctx=None,
        actor_type="system",
        actor_user_id=session.admin_user_id,
        acting_as_user_id=session.target_user_id,
        impersonation_id=session.id,
        action="impersonation.ended",
        target_type="user",
        target_id=str(session.target_user_id),
        after={"end_reason": reason, "duration_seconds": duration_seconds},
    )
    # Q-049: ids/codes only (§68 — no free-text `reason`, no timestamps that the payload
    # validator's PII heuristics could flag) — the email builder
    # (`ham.identity.notifications`) resolves display names, the reason and the church-local
    # times itself, from the session id.
    outbox_emit(
        "ImpersonationEnded",
        aggregate_type="user",
        aggregate_id=session.target_user_id,
        payload={
            "session_id": str(session.id),
            "admin_user_id": str(session.admin_user_id),
            "end_reason": reason,
            "duration_seconds": duration_seconds,
        },
    )
    return session


def end_impersonation_for_session(
    request: HttpRequest, *, reason: str
) -> ImpersonationSession | None:
    """Security review round 3, N1: the one call every session-ending path (idle/absolute
    session lifetime expiry, the session-epoch force-logout, "Sign out", "Cancel and sign
    out" from a pending sign-in screen) must make *before* `django.contrib.auth.logout`, so an
    admin's browser session can never go from "impersonating" to "signed out" without an
    audited `ImpersonationEnded` (Q-049) in between. Reads/clears the session key itself so
    callers don't have to know it; a no-op (returns ``None``) if nothing was active."""
    session_id_raw = request.session.pop(SESSION_KEY_IMPERSONATION_ID, None)
    if not session_id_raw:
        return None
    try:
        session_id = uuid.UUID(str(session_id_raw))
    except ValueError:  # pragma: no cover - defensive against a malformed session value
        return None
    return end_impersonation(session_id, reason=reason)


from ham import jobs as _jobs  # noqa: E402 - kept near the job it defines, not the top imports


@_jobs.periodic_job(name="identity.sweep_idle_impersonation_sessions", cron="*/5 * * * *")
def sweep_idle_impersonation_sessions(timestamp: int) -> int:
    """Periodic sweep (security review N1) ending any impersonation session whose
    ``last_activity_at`` is already past `RULES.auth.IMPERSONATION_IDLE_TIMEOUT`, even if the
    admin's browser never sends another request (closed tab, crashed machine, or the target
    account got disabled and nobody happens to hit `_enforce_impersonation_idle` for that
    session first). The per-request idle check in `ham.identity.middleware` still ends a
    session immediately on its owner's next request; this is the backstop for "nobody's
    request ever comes back"."""
    cutoff = clock_now() - RULES.auth.IMPERSONATION_IDLE_TIMEOUT
    session_ids = list(
        ImpersonationSession.objects.filter(
            ended_at__isnull=True, last_activity_at__lt=cutoff
        ).values_list("id", flat=True)
    )
    ended = [
        end_impersonation(sid, reason=ImpersonationSession.END_REASON_IDLE_TIMEOUT)
        for sid in session_ids
    ]
    return len([s for s in ended if s is not None])


def end_impersonations_for_target(
    user_id: uuid.UUID, *, reason: str = ImpersonationSession.END_REASON_TARGET_DISABLED
) -> list[ImpersonationSession]:
    """Ends every currently-active impersonation session targeting ``user_id`` (Q-052: turning
    an account off must end any impersonation of it, not leave it running against a disabled
    account). Safe to call even if none are active."""
    session_ids = list(
        ImpersonationSession.objects.filter(
            target_user_id=user_id, ended_at__isnull=True
        ).values_list("id", flat=True)
    )
    ended = (end_impersonation(sid, reason=reason) for sid in session_ids)
    return [s for s in ended if s is not None]
