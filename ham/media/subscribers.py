"""The `media` outbox subscriber (registered by `MediaConfig.ready()`).

Reacts to domain events from other modules without ever being imported by them (foundation.md
§1/§3: subscribers fetch what they need through their own services, under their own least
privilege; never trust the payload beyond ids/codes, §68).
"""

from __future__ import annotations

import logging

from django.db import transaction

from ham.outbox.models import OutboxEvent

logger = logging.getLogger(__name__)


def handle_media_event(event: OutboxEvent) -> None:
    if event.event_type == "RequestCancelled":
        from .services import close_open_batches

        with transaction.atomic():
            close_open_batches(event.aggregate_id, reason_code="request_cancelled")
        return
    logger.info("media subscriber: no handler for event_type=%s", event.event_type)
