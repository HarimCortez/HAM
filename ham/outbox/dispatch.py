"""The dispatcher job: one delivery attempt per call, with exponential backoff and
dead-lettering after `RULES.outbox.OUTBOX_MAX_ATTEMPTS` (PRD §70.3; foundation.md §5, §8 S4).

Registered through `ham.jobs` (the only module allowed to import `procrastinate` directly) so
this file never touches the job backend itself.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from ham import jobs
from ham.platform.clock import now
from ham.platform.logging import scrub
from ham.rules.v1 import RULES

from . import registry
from .models import DeliveryStatus, OutboxDelivery

logger = logging.getLogger(__name__)

_MAX_ERROR_LENGTH = 2000


def defer_dispatch(delivery_id: str) -> None:
    """Enqueue an immediate dispatch attempt for one delivery."""
    jobs.defer("outbox.dispatch_delivery", delivery_id=delivery_id)


@jobs.job(name="outbox.dispatch_delivery")
def dispatch_delivery(delivery_id: str) -> None:
    _attempt(delivery_id)


def _attempt(delivery_id: str) -> None:
    try:
        delivery = OutboxDelivery.objects.select_related("event").get(id=delivery_id)
    except OutboxDelivery.DoesNotExist:  # pragma: no cover - defensive; ids are our own uuid7s
        logger.warning(
            "outbox.dispatch_delivery: delivery not found", extra={"delivery_id": delivery_id}
        )
        return

    if delivery.status in (DeliveryStatus.DELIVERED, DeliveryStatus.DEAD):
        return  # already resolved (e.g. a duplicate/late job run) — nothing to do

    try:
        handler = registry.get_handler(delivery.subscriber)
    except KeyError:
        logger.error(
            "outbox.dispatch_delivery: no handler registered for subscriber",
            extra={"subscriber": delivery.subscriber, "delivery_id": delivery_id},
        )
        return

    delivery.attempts += 1
    try:
        handler(delivery.event)
    except Exception as exc:  # noqa: BLE001 - any adapter failure must be retried, never crash
        _record_failure(delivery, exc)
    else:
        delivery.status = DeliveryStatus.DELIVERED
        delivery.delivered_at = now()
        delivery.last_error = ""
        delivery.next_attempt_at = None
        delivery.save(
            update_fields=["attempts", "status", "delivered_at", "last_error", "next_attempt_at"]
        )


def _record_failure(delivery: OutboxDelivery, exc: Exception) -> None:
    delivery.last_error = scrub(f"{type(exc).__name__}: {exc}")[:_MAX_ERROR_LENGTH]
    max_attempts = RULES.outbox.OUTBOX_MAX_ATTEMPTS
    if delivery.attempts >= max_attempts:
        delivery.status = DeliveryStatus.DEAD
        delivery.next_attempt_at = None
        delivery.save(update_fields=["attempts", "status", "last_error", "next_attempt_at"])
        logger.error(
            "outbox.dispatch_delivery: dead-lettered after max attempts",
            extra={
                "delivery_id": str(delivery.id),
                "subscriber": delivery.subscriber,
                "attempts": delivery.attempts,
            },
        )
        return

    delay = _backoff_delay(delivery.attempts)
    delivery.status = DeliveryStatus.FAILED
    delivery.next_attempt_at = now() + delay
    delivery.save(update_fields=["attempts", "status", "last_error", "next_attempt_at"])
    jobs.defer_later(
        "outbox.dispatch_delivery",
        schedule_at=delivery.next_attempt_at,
        delivery_id=str(delivery.id),
    )


def _backoff_delay(attempts: int) -> timedelta:
    """Doubling backoff from `OUTBOX_BACKOFF_INITIAL`, capped at `OUTBOX_BACKOFF_MAX`."""
    initial = RULES.outbox.OUTBOX_BACKOFF_INITIAL
    cap = RULES.outbox.OUTBOX_BACKOFF_MAX
    delay = initial * (2 ** max(attempts - 1, 0))
    return min(delay, cap)
