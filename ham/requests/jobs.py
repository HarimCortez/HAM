"""Background jobs for `ham.requests` (PRD §78; intake.md §4, §9, D4/Q-127; approvals.md §2.4,
approvals-contracts.md §4).

- The duplicate-check job (`complete_intake_checks`, SUBMITTED -> AWAITING_APPROVAL) runs a
  few seconds after every submission and every "verified by phone call".
- The retention sweep (Q-127, decided) erases requester personal details 7 years after a
  request closes, and erases a spam-closed request entirely after 90 days.
- The held-effects job (Q-156/Q-176): one deferred (not periodic) job per decision, scheduled
  for `Approval.effective_at`.
- The finalize-rejections job (Q-155/Q-174): hourly, closes any rejection past its
  reconsideration deadline with none filed.
  All use `ham.jobs.periodic_job`/`defer_later` (foundation.md §5's "no separate scheduler
  process").
"""

from __future__ import annotations

import datetime as dt
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


# --------------------------------------------------------------------------------------
# Held effects (Q-156/Q-176; approvals-contracts.md §4): one deferred job per decision,
# scheduled for exactly `Approval.effective_at` -- not periodic (mirrors
# `defer_complete_intake_checks`'s "defer a job for later, from inside the same transaction as
# the row write" shape).
# --------------------------------------------------------------------------------------
@jobs.job(name="requests.run_held_decision_effects")
def _run_held_decision_effects_job(approval_id: str) -> None:
    from .services_decisions import run_held_decision_effects

    run_held_decision_effects(UUID(approval_id))


def defer_held_decision_effects(approval_id: UUID, *, effective_at: dt.datetime) -> None:
    """Called by `approve_request`/`reject_request`/`decide_reconsideration` right after
    creating their `Approval` row, inside the same transaction."""
    jobs.defer_later(
        "requests.run_held_decision_effects",
        schedule_at=effective_at,
        approval_id=str(approval_id),
    )


# --------------------------------------------------------------------------------------
# Finalize rejections (Q-155/Q-174): hourly -- REJECTED, still open, past its
# `reconsideration_deadline_at`, with no `Reconsideration` ever filed.
# --------------------------------------------------------------------------------------
def _eligible_for_rejection_finalization() -> list[UUID]:
    now = clock_now()
    return list(
        AssistanceRequest.objects.filter(
            status=RequestStatus.REJECTED.value,
            closed_at__isnull=True,
            reconsideration_deadline_at__isnull=False,
            # Security L5: strictly past the deadline (`may_request_reconsideration` treats
            # the deadline instant itself as still in time) -- `__lte` here would race a
            # request whose deadline is exactly `now`.
            reconsideration_deadline_at__lt=now,
            reconsideration__isnull=True,
        ).values_list("id", flat=True)
    )


@jobs.periodic_job(name="requests.finalize_rejections", cron="0 * * * *")
def finalize_rejections(timestamp: int) -> None:  # noqa: ARG001 - Procrastinate periodic contract
    import logging

    from .services_decisions import finalize_rejection

    logger = logging.getLogger(__name__)
    ctx = SystemContext()
    # Security L5: one bad request must not stop the whole batch -- catch and log per item
    # (the request id only, never any free text) and keep going.
    for request_id in _eligible_for_rejection_finalization():
        try:
            finalize_rejection(ctx, request_id=request_id)
        except Exception:  # noqa: BLE001 - deliberately broad: isolate one request's failure
            logger.exception("requests.finalize_rejections failed for request_id=%s", request_id)


def run_finalize_rejections_now() -> None:
    """Dev/test helper, same shape as `run_retention_sweep_now`."""
    finalize_rejections(0)
