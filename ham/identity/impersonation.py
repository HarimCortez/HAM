"""Ending an impersonation session (§59, Q-049, Q-053): the one function every end path
(manual "Stop", idle timeout, sign-out, the target's account being turned off) must funnel
through, so an ``ImpersonationEnded`` domain event — and the after-the-fact email to the
impersonated person it triggers (Q-049) — happen exactly once, from exactly one place, no
matter which path ended the session.

``ham.identity.services.stop_impersonation`` (the ``@command``-wrapped manual "Stop" action)
emits the same event through its own ``CommandResult`` (it already has an ``ActorContext`` and
records its own audit event that way). The other end paths don't have an ``ActorContext`` handy
(the idle timeout and sign-out fire outside/after the normal command pipeline) — they should
call ``end_impersonation(session_id, reason)`` here instead of duplicating the
session-ending/audit logic:

- ``ham.identity.middleware.SessionLifetimeMiddleware._enforce_impersonation_idle`` (idle
  timeout) — currently ends the session and audits inline; switching it to call
  ``end_impersonation(session.id, reason=ImpersonationSession.END_REASON_IDLE_TIMEOUT)`` would
  also get it the ``ImpersonationEnded`` event/email for free.
- the sign-out view (``ham.web.auth_views.sign_out`` / wherever "Stop impersonating and sign
  out" lives) — end any active impersonation session for the signing-out admin via
  ``end_impersonation`` before/instead of just clearing the session key.

``end_impersonations_for_target`` is ``disable_user``'s hook (Q-052: disabling someone must end
any impersonation of them, ``END_REASON_TARGET_DISABLED``).
"""

from __future__ import annotations

import uuid

from ham.audit.services import record as audit_record
from ham.outbox.api import emit as outbox_emit
from ham.platform.clock import now as clock_now

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
