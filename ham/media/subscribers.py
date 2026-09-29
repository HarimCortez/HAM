"""The `media` outbox subscriber (registered by `MediaConfig.ready()`).

Reacts to domain events from other modules without ever being imported by them (foundation.md
§1/§3: subscribers fetch what they need through their own services, under their own least
privilege; never trust the payload beyond ids/codes, §68).

S3.4 (approvals-contracts.md §4 "Held effects"): `RequestApproved`/`RequestRejected` close any
still-open media batch, same as `RequestCancelled` always has -- but for step 3 those two
event types are emitted by S3.2's held-effects job only once a decision's undo window has
passed (`effective_at`), never by the deciding command itself at `decided_at`. This subscriber
does not need to know that timing exists: it just reacts to the event whenever it arrives,
which is exactly what makes "close on effect, not on decision" fall out for free -- the job
choosing *when* to emit is the only place that decision lives (this module must never itself
gate on `undone_at`/`effective_at`, or it would duplicate that timing decision here).
"""

from __future__ import annotations

import logging

from django.db import transaction

from ham.outbox.models import OutboxEvent

logger = logging.getLogger(__name__)

# approvals-contracts.md §4: the held-effect release events, emitted at `effective_at` (never
# at `decided_at`) by S3.2's `run_held_decision_effects` job. `aggregate_id` is the request id
# for both (same convention `RequestCancelled` already uses -- see `ham.requests.services`'s
# own `aggregate_type="request"` emits).
_DECISION_EFFECT_EVENTS = frozenset({"RequestApproved", "RequestRejected"})


def handle_media_event(event: OutboxEvent) -> None:
    if event.event_type == "RequestCancelled":
        from .services import close_open_batches

        with transaction.atomic():
            close_open_batches(event.aggregate_id, reason_code="request_cancelled")
        return
    if event.event_type in _DECISION_EFFECT_EVENTS:
        from .services import close_open_batches

        with transaction.atomic():
            close_open_batches(event.aggregate_id, reason_code="decision")
        return
    logger.info("media subscriber: no handler for event_type=%s", event.event_type)
