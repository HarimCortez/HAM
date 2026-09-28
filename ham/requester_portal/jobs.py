"""Purge jobs for the public requester surface (intake.md §10 "S2.10 owns `ham/*/jobs.py`" —
this file only registers the two purges that belong entirely to this app's own tables so they
don't sit unscheduled; S2.10 may relocate/extend them alongside the media/retention sweeps).

Both run hourly, mirroring `ham.identity.authn.purge_expired_sign_in_challenges` (security
review L5: a row that exists purely to rate-limit/lock out by address, or an unfinished form
nobody ever came back to, is not a record worth keeping).
"""

from __future__ import annotations

from ham import jobs
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from .models import IntakeDraft, RequesterVerificationChallenge


@jobs.periodic_job(name="requester_portal.purge_expired_drafts", cron="0 * * * *")
def purge_expired_drafts(timestamp: int) -> int:
    """Q-100/Q-127/Q-139: an unfinished form is erased `INTAKE_DRAFT_LIFETIME` (24 h) after it
    was started, whether or not it was ever verified. A *consumed* draft (already turned into
    a request) is purged too, once past its own `expires_at` — its payload has no further use
    once `ham.requests.services.submit_request` has copied what it needs into the real
    request row."""
    cutoff = clock_now()
    deleted, _ = IntakeDraft.objects.filter(expires_at__lt=cutoff).delete()
    return deleted


@jobs.periodic_job(name="requester_portal.purge_expired_challenges", cron="0 * * * *")
def purge_expired_challenges(timestamp: int) -> int:
    """Mirrors `ham.identity.authn.purge_expired_sign_in_challenges`: these rows exist purely
    to rate-limit/lock out by address, kept only `RULES.intake.REQUESTER_CHALLENGE_RETENTION`
    past creation."""
    cutoff = clock_now() - RULES.intake.REQUESTER_CHALLENGE_RETENTION
    deleted, _ = RequesterVerificationChallenge.objects.filter(created_at__lt=cutoff).delete()
    return deleted
