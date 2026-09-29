"""S3.4: `ham.media.subscribers.handle_media_event` closes open batches on the held-effect
release events (`RequestApproved`/`RequestRejected`) -- and only on those, never at decision
time and never on an undo (approvals-contracts.md §4 "Held effects").
"""

from __future__ import annotations

import pytest
from django.db import transaction

from ham.jobs import run_due_jobs_now
from ham.media.models import RequestMediaBatch
from ham.media.services import UploadIntent, reserve_uploads
from ham.outbox.api import emit

pytestmark = pytest.mark.django_db(transaction=True)


def _open_a_batch(open_request):
    from ham.authz.context import RequesterContext

    reserve_uploads(
        RequesterContext(request_id=open_request.id),
        intents=[UploadIntent("photo", "image/jpeg", 1000)],
    )
    return RequestMediaBatch.objects.get(request=open_request, number=1)


@pytest.mark.parametrize("event_type", ["RequestApproved", "RequestRejected"])
def test_batch_closes_once_the_held_effect_event_is_dispatched(open_request, event_type):
    batch = _open_a_batch(open_request)
    assert batch.is_open

    # Simulates S3.2's held-effects job emitting the event at `effective_at` -- this
    # subscriber must not know or care about the undo-window timing, only react to the event
    # actually arriving.
    with transaction.atomic():
        emit(
            event_type,
            aggregate_type="request",
            aggregate_id=open_request.id,
            payload={"request_id": str(open_request.id), "stage": "initial"},
        )
    # Not yet dispatched: proves the assertion below really exercises the subscriber.
    batch.refresh_from_db()
    assert batch.is_open

    run_due_jobs_now()

    batch.refresh_from_db()
    assert not batch.is_open


def test_batch_stays_open_when_only_an_unrelated_event_is_emitted(open_request):
    """An undo never emits `RequestApproved`/`RequestRejected` at all (S3.2's held-effects job
    skips the held effects entirely once `undone_at` is set before it runs) -- it emits
    `RequestDecisionUndone` instead, immediately. This subscriber has no handler for that
    event type, so the batch must stay open."""
    batch = _open_a_batch(open_request)
    assert batch.is_open

    with transaction.atomic():
        emit(
            "RequestDecisionUndone",
            aggregate_type="request",
            aggregate_id=open_request.id,
            payload={"request_id": str(open_request.id), "approval_id": str(open_request.id)},
        )

    run_due_jobs_now()

    batch.refresh_from_db()
    assert batch.is_open
