"""`retry_delivery` and the integration-status query service (foundation.md §8 S4).

`retry_delivery` is a plain service function with no permission check and no audit event of
its own — S3a/S5's Admin "Retry" action must wrap it:

    @command("outbox.retry")
    def retry_outbox_delivery(ctx, delivery_id):
        retry_delivery(delivery_id)

This module must never import `ham.authz`/`ham.audit` itself (foundation.md §1: outbox sits
below web in the dependency layering; permission/audit concerns belong to the caller).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.db.models import Count

from ham.platform.clock import now

from .dispatch import defer_dispatch
from .models import DeliveryStatus, OutboxDelivery


def retry_delivery(delivery_id: uuid.UUID | str) -> None:
    """Re-attempt one delivery right away, regardless of its current status (including a
    dead-lettered one). Does not reset `attempts`, so a delivery already at the retry limit
    that fails again is dead-lettered immediately — this is a deliberate one-shot manual
    retry, not a reset of the automatic retry budget.
    """
    delivery = OutboxDelivery.objects.get(id=delivery_id)
    delivery.status = DeliveryStatus.PENDING
    delivery.next_attempt_at = now()
    delivery.save(update_fields=["status", "next_attempt_at"])
    defer_dispatch(str(delivery.id))


@dataclass(frozen=True, slots=True)
class SubscriberStatusCount:
    subscriber: str
    status: str
    count: int


def subscriber_status_counts() -> list[SubscriberStatusCount]:
    """Counts per subscriber/status, for the Admin integrations page (`integrations.view_status`,
    foundation.md §7 `GET /admin/integrations`)."""
    rows = (
        OutboxDelivery.objects.values("subscriber", "status")
        .annotate(count=Count("id"))
        .order_by("subscriber", "status")
    )
    return [SubscriberStatusCount(row["subscriber"], row["status"], row["count"]) for row in rows]


def recent_failures(limit: int = 20) -> list[OutboxDelivery]:
    """Most recent failed/dead-lettered deliveries, newest event first."""
    return list(
        OutboxDelivery.objects.filter(status__in=[DeliveryStatus.FAILED, DeliveryStatus.DEAD])
        .select_related("event")
        .order_by("-event__occurred_at")[:limit]
    )
