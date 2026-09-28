"""Step-2 handoff "known loose end" #2: confirm `ham.media.subscribers.handle_media_event`'s
`RequestCancelled` branch actually matches what `ham.requests.services.cancel_request` emits
(event type *and* `aggregate_type="request"`) -- not just by reading both modules, but by
cancelling a real request through the real `@command`/outbox/dispatch pipeline and checking
the batch actually closes.
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.authz.context import ActorContext
from ham.jobs import run_due_jobs_now
from ham.media.models import RequestMediaBatch
from ham.media.services import UploadIntent, reserve_uploads
from ham.outbox.models import OutboxDelivery, OutboxEvent
from ham.requests.services import cancel_request

pytestmark = pytest.mark.django_db(transaction=True)


def _director_ctx() -> ActorContext:
    return ActorContext(
        user_id=uuid.UUID("00000000-0000-7000-8000-000000000009"),
        real_user_id=None,
        roles=frozenset({roles.HAM_DIRECTOR}),
        is_active=True,
        mfa_satisfied=True,
    )


def test_cancelling_a_request_closes_its_open_media_batch(open_request):
    from ham.authz.context import RequesterContext

    reserve_uploads(
        RequesterContext(request_id=open_request.id),
        intents=[UploadIntent("photo", "image/jpeg", 1000)],
    )
    batch = RequestMediaBatch.objects.get(request=open_request, number=1)
    assert batch.is_open

    cancel_request(_director_ctx(), request_id=open_request.id, reason_code="requester_withdrew")

    event = OutboxEvent.objects.get(event_type="RequestCancelled", aggregate_id=open_request.id)
    assert event.aggregate_type == "request"
    delivery = OutboxDelivery.objects.get(event=event, subscriber="media")
    assert delivery.status != "delivered"  # not dispatched yet -- proves the assertion below
    # really exercises the subscriber, not a batch already closed by `cancel_request` itself.

    run_due_jobs_now()

    delivery.refresh_from_db()
    assert delivery.status == "delivered"
    batch.refresh_from_db()
    assert not batch.is_open
