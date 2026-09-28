"""Google Calendar seam (PRD §51; CLAUDE.md "stub only in step 1").

Step 1 ships a no-op subscriber only, so the outbox dispatcher has somewhere real to deliver
`calendar` deliveries to. The real Google Calendar client (one event per confirmed project
work date, task events only when timing meaningfully differs, §51.2) lands with the
projects/schedule step; it will implement `CalendarAdapter` and replace `NoOpCalendarAdapter`
without any outbox-side change.

Titles must stay privacy-safe (e.g. `HAM Project #024 — Plumbing Repair`, §51.1, §68): never
pass a requester name, address or circumstances to this interface, even once a real adapter
exists. Only leadership sees the calendar; never add volunteers/requesters/contractors as
guests.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ham.outbox.models import OutboxEvent

logger = logging.getLogger(__name__)


class CalendarAdapter(Protocol):
    """One confirmed project work date <-> one calendar event (PRD §51.2)."""

    def upsert_event(self, *, project_id: str, title: str, start: str, end: str) -> str:
        """Create or update the linked event; returns a `CalendarEventReference` id to store
        on the project/task."""
        ...

    def delete_event(self, *, calendar_event_reference: str) -> None: ...


class NoOpCalendarAdapter:
    """§70.3: HAM keeps working with the calendar down. Step 1 has no schedule-change logic
    yet to call this — it exists only so the interface and the outbox subscriber wiring are
    ready for the step that adds it."""

    def upsert_event(self, *, project_id: str, title: str, start: str, end: str) -> str:
        return ""

    def delete_event(self, *, calendar_event_reference: str) -> None:
        return None


def get_default_adapter() -> CalendarAdapter:
    return NoOpCalendarAdapter()


def handle_calendar_event(event: OutboxEvent) -> None:
    """The `calendar` outbox subscriber. Logs only the event type and ids — never the
    payload — in case a future event accidentally carries more than ids (defense in depth
    alongside `ham.outbox.validation`)."""
    logger.info(
        "outbox.calendar: received event (no-op stub, PRD §51 seam)",
        extra={
            "event_type": event.event_type,
            "event_id": str(event.id),
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
        },
    )
