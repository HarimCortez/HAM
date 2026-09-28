"""A subscriber registered only when `DEBUG` is on (foundation.md §2 "Step-1 subscribers: ...
a logging stub in dev"), so a developer running the Procrastinate worker locally can see every
outbox event without a real provider account. Never registered in test or prod settings
(`ham.integrations.apps.IntegrationsConfig.ready`).

Logs the full payload: safe only because `ham.outbox.validation.validate_payload` has already
rejected anything that looks like PII before the event was ever written.
"""

from __future__ import annotations

import logging

from ham.outbox.models import OutboxEvent

logger = logging.getLogger(__name__)


def handle_dev_logging_event(event: OutboxEvent) -> None:
    logger.info(
        "outbox.dev: event delivered",
        extra={
            "event_type": event.event_type,
            "event_id": str(event.id),
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
            "payload": event.payload,
        },
    )
