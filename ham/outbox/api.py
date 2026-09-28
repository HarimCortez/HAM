"""STUB — replaced by S4 at merge.

`ham.authz.commands.command()` calls `emit()` inside the same transaction as the change and
its audit event (foundation.md §1 "One write path"). Until S4 lands `OutboxEvent`/
`OutboxDelivery`, this just appends to an in-memory list — nothing is persisted, and nothing
here is a substitute for the real outbox (no retry, no delivery, no durability across
process restarts). Do not add models or persistence to this module; S4 owns `ham/outbox/`
and will replace this file whole.

`events()` / `clear()` exist for tests only (this slice's and S4's).
"""

from __future__ import annotations

import uuid
from typing import Any

_events: list[dict[str, Any]] = []


def emit(
    event_type: str,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID | str,
    payload: dict[str, Any],
    schema_version: int = 1,
) -> None:
    _events.append(
        {
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "payload": payload,
            "schema_version": schema_version,
        }
    )


def events() -> list[dict[str, Any]]:
    """Test-only accessor for what has been emitted (in process memory)."""
    return list(_events)


def clear() -> None:
    """Test-only: reset the in-memory event list between tests."""
    _events.clear()
