"""Google Drive seam (PRD §50; CLAUDE.md "Deferred ... keep a clean seam").

No real client is built in V1. `NoOpDriveAdapter` and the `drive` outbox subscriber exist only
so a later integration can plug in behind `DriveAdapter` without any outbox-side or
domain-side change.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ham.outbox.models import OutboxEvent

logger = logging.getLogger(__name__)


class DriveAdapter(Protocol):
    def upload_file(self, *, folder_id: str, file_name: str, content_type: str) -> str:
        """Returns a provider file id."""
        ...


class NoOpDriveAdapter:
    def upload_file(self, *, folder_id: str, file_name: str, content_type: str) -> str:
        return ""


def get_default_adapter() -> DriveAdapter:
    return NoOpDriveAdapter()


def handle_drive_event(event: OutboxEvent) -> None:
    """The `drive` outbox subscriber: a documented no-op (§50 seam)."""
    logger.debug(
        "outbox.drive: received event (no-op stub, PRD §50 seam)",
        extra={
            "event_type": event.event_type,
            "event_id": str(event.id),
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
        },
    )
