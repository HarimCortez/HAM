"""The `requester_portal` outbox subscriber (registered by `RequesterPortalConfig.ready()`).

L4 (step-2 fix round): when `ham.requests.services.purge_expired_request` deletes a spam
request entirely, this app's own `RequesterAccessLink`/`RequesterVerificationChallenge` rows
(plain `request_id` UUID fields, not real FKs -- `ham.requests` may not import this app to
delete them directly, intake.md §2 layering) would otherwise be left orphaned. Reacting to
`RequestPurged` here, the same pattern `ham.media`'s own subscriber uses for `RequestCancelled`,
is how this app cleans up after itself without `ham.requests` ever importing it.
"""

from __future__ import annotations

import logging

from django.db import transaction

from ham.outbox.models import OutboxEvent

logger = logging.getLogger(__name__)


def handle_requester_portal_event(event: OutboxEvent) -> None:
    if event.event_type == "RequestPurged":
        from .models import RequesterAccessLink, RequesterVerificationChallenge

        request_id = event.aggregate_id
        with transaction.atomic():
            RequesterAccessLink.objects.filter(request_id=request_id).delete()
            RequesterVerificationChallenge.objects.filter(request_id=request_id).delete()
        return
    logger.info("requester_portal subscriber: no handler for event_type=%s", event.event_type)
