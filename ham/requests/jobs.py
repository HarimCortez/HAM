"""Background jobs for `ham.requests` (PRD §78; intake.md §4, §9, D4/Q-127).

- The duplicate-check job (`complete_intake_checks`, SUBMITTED -> AWAITING_APPROVAL) runs a
  few seconds after every submission and every "verified by phone call".
- The retention sweep (Q-127, decided) erases requester personal details 7 years after a
  request closes, and erases a spam-closed request entirely after 90 days. Both use
  `ham.jobs.periodic_job` (foundation.md §5's "no separate scheduler process").
"""

from __future__ import annotations

from uuid import UUID

from ham import jobs
from ham.authz.context import SystemContext
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from .models import AssistanceRequest
from .states import CancelReason, RequestStatus


@jobs.job(name="requests.complete_intake_checks")
def _complete_intake_checks_job(request_id: str) -> None:
    from .services import complete_intake_checks

    complete_intake_checks(SystemContext(), request_id=UUID(request_id))


def defer_complete_intake_checks(request_id: UUID) -> None:
    """Enqueue the duplicate check (intake.md §4: SYSTEM, "after the duplicate check
    finished"). Called from `submit_request` and `verify_by_phone`."""
    jobs.defer("requests.complete_intake_checks", request_id=str(request_id))


# --------------------------------------------------------------------------------------
# Q-127 retention sweep
# --------------------------------------------------------------------------------------
def _eligible_for_pii_erasure() -> list[UUID]:
    now = clock_now()
    years = RULES.retention.REQUEST_RECORD_RETENTION_AFTER_CLOSE
    ids: list[UUID] = []
    candidates = AssistanceRequest.objects.filter(closed_at__isnull=False).exclude(
        cancel_reason_code=CancelReason.SPAM.value
    )
    for request in candidates.only("id", "closed_at"):
        requester = getattr(request, "requester", None)
        if requester is not None and requester.anonymized_at is not None:
            continue
        closed_at = request.closed_at
        assert closed_at is not None  # the queryset above filters closed_at__isnull=False
        if years.after(closed_at) <= now:
            ids.append(request.id)
    return ids


def _eligible_for_spam_purge() -> list[UUID]:
    now = clock_now()
    window = RULES.retention.SPAM_REQUEST_RETENTION
    return list(
        AssistanceRequest.objects.filter(
            status=RequestStatus.CANCELLED.value,
            cancel_reason_code=CancelReason.SPAM.value,
            closed_at__isnull=False,
            closed_at__lte=now - window,
        ).values_list("id", flat=True)
    )


@jobs.periodic_job(name="requests.retention_sweep", cron="0 3 * * *")
def retention_sweep(timestamp: int) -> None:  # noqa: ARG001 - Procrastinate periodic contract
    from .services import purge_expired_request

    ctx = SystemContext()
    for request_id in {*_eligible_for_pii_erasure(), *_eligible_for_spam_purge()}:
        purge_expired_request(ctx, request_id=request_id)


def run_retention_sweep_now() -> None:
    """Dev/test helper: run the sweep synchronously without a worker (mirrors
    `ham.jobs.run_due_jobs_now`'s spirit for a periodic task, which isn't itself deferred as
    a plain job row)."""
    retention_sweep(0)
