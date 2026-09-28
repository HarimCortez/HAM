"""Ending impersonation sessions from outside the normal manual-stop/idle-timeout paths.

foundation.md §3 lists `target_disabled` as an `ImpersonationSession.end_reason` (PRD §59:
disabling an account "ends all sessions and impersonations of that user"), but nothing calls
it yet. This module gives `ham.identity.services.disable_user` (or any other future caller) one
function to end every *active* impersonation session where `user_id` is the *target*, so a
disabled account can't keep being acted-as by an Admin who started before the disable.

    from ham.identity.impersonation import end_impersonations_for_target
    end_impersonations_for_target(user_id, reason="target_disabled")

Deliberately outside `ham.identity.services` (which another engineer may be editing in
parallel): a plain function here, imported and called from wherever `user.disable` actually
flips `is_active`/`disabled_at`, keeps that merge to "add one import + one call" rather than a
diff inside a function both engineers touched.
"""

from __future__ import annotations

import uuid

from ham.audit.services import record as audit_record
from ham.platform.clock import now as clock_now

from .models import ImpersonationSession


def end_impersonations_for_target(
    user_id: uuid.UUID, *, reason: str = ImpersonationSession.END_REASON_TARGET_DISABLED
) -> int:
    """Ends every active `ImpersonationSession` where `target_user_id == user_id`. Returns how
    many sessions were ended. Safe to call even if there are none (the common case)."""
    now = clock_now()
    sessions = list(
        ImpersonationSession.objects.filter(target_user_id=user_id, ended_at__isnull=True)
    )
    for session in sessions:
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
            after={"end_reason": reason},
        )
    return len(sessions)
