"""Fitness & Accountability seam (PRD §36; CLAUDE.md "Deferred ... keep a clean seam").

No real client is built in V1. `NoOpFitnessAdapter` and the `fitness` outbox subscriber exist
only so a later integration can plug in behind `FitnessAdapter` without any outbox-side or
domain-side change.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ham.outbox.models import OutboxEvent

logger = logging.getLogger(__name__)


class FitnessAdapter(Protocol):
    def record_activity(self, *, volunteer_id: str, event_type: str, occurred_at: str) -> None: ...


class NoOpFitnessAdapter:
    def record_activity(self, *, volunteer_id: str, event_type: str, occurred_at: str) -> None:
        return None


def get_default_adapter() -> FitnessAdapter:
    return NoOpFitnessAdapter()


def handle_fitness_event(event: OutboxEvent) -> None:
    """The `fitness` outbox subscriber: a documented no-op (§36 seam)."""
    logger.debug(
        "outbox.fitness: received event (no-op stub, PRD §36 seam)",
        extra={
            "event_type": event.event_type,
            "event_id": str(event.id),
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
        },
    )
