"""`ham.outbox.api.emit` — the exact public contract domain code (and S3a's `@command`
pipeline) codes against (foundation.md §8 S4).

    from ham.outbox.api import emit
    emit(event_type, *, aggregate_type, aggregate_id, payload, schema_version=1) -> None

Call it **inside the caller's own `transaction.atomic()`** (it raises if there is no open
atomic block): it writes the `OutboxEvent` plus one pending `OutboxDelivery` per registered
subscriber in that same transaction, then defers dispatch with `transaction.on_commit` so
nothing is enqueued for a change that gets rolled back.
"""

from __future__ import annotations

import uuid

from django.db import transaction

from ham.platform.clock import now
from ham.platform.ids import uuid7

from . import registry
from .models import DeliveryStatus, OutboxDelivery, OutboxEvent
from .validation import validate_payload


def emit(
    event_type: str,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID | str,
    payload: dict,
    schema_version: int = 1,
) -> None:
    connection = transaction.get_connection()
    if not connection.in_atomic_block:
        raise RuntimeError(
            "ham.outbox.emit() must be called inside the caller's transaction.atomic() "
            "(foundation.md §3: 'Emitted in the same transaction as the change'). Wrap the "
            "domain change and this call in one atomic block."
        )

    validate_payload(payload)
    aggregate_uuid = (
        aggregate_id if isinstance(aggregate_id, uuid.UUID) else uuid.UUID(str(aggregate_id))
    )

    event = OutboxEvent.objects.create(
        id=uuid7(),
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=now(),
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_uuid,
        payload=payload,
    )

    deliveries = [
        OutboxDelivery(
            id=uuid7(),
            event=event,
            subscriber=subscriber,
            status=DeliveryStatus.PENDING,
            next_attempt_at=now(),
        )
        for subscriber in registry.subscribers()
    ]
    if deliveries:
        OutboxDelivery.objects.bulk_create(deliveries)

    delivery_ids = [str(delivery.id) for delivery in deliveries]

    def _defer_dispatch() -> None:
        # Imported here (not at module top) so a plain `emit()` call never needs
        # `ham.jobs`/procrastinate importable unless a subscriber is actually registered and
        # the transaction actually commits.
        from .dispatch import defer_dispatch

        for delivery_id in delivery_ids:
            defer_dispatch(delivery_id)

    transaction.on_commit(_defer_dispatch)
