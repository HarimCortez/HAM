from __future__ import annotations

import uuid

import pytest
from django.db import transaction

from ham.outbox.api import emit
from ham.outbox.models import DeliveryStatus, OutboxDelivery, OutboxEvent
from ham.outbox.validation import PayloadPIIError


@pytest.mark.django_db(transaction=True)
def test_emit_outside_atomic_block_raises():
    with pytest.raises(RuntimeError, match="transaction.atomic"):
        emit(
            "Test.Thing",
            aggregate_type="thing",
            aggregate_id=uuid.uuid4(),
            payload={"thing_id": str(uuid.uuid4())},
        )
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db
def test_emit_writes_event_and_one_pending_delivery_per_subscriber(fake_subscriber):
    fake_subscriber("test_sub_a", lambda event: None)
    fake_subscriber("test_sub_b", lambda event: None)
    aggregate_id = uuid.uuid4()

    with transaction.atomic():
        emit(
            "Test.ThingHappened",
            aggregate_type="thing",
            aggregate_id=aggregate_id,
            payload={"thing_id": str(aggregate_id)},
            schema_version=2,
        )

    event = OutboxEvent.objects.get(event_type="Test.ThingHappened")
    assert event.aggregate_type == "thing"
    assert event.aggregate_id == aggregate_id
    assert event.schema_version == 2
    assert event.payload == {"thing_id": str(aggregate_id)}

    # One delivery per *registered* subscriber, which includes the real ham.integrations
    # subscribers (email/calendar/fitness/drive) wired at Django startup, not just our fakes.
    deliveries = OutboxDelivery.objects.filter(event=event)
    subscribers = {d.subscriber for d in deliveries}
    assert {"test_sub_a", "test_sub_b"} <= subscribers
    assert all(d.status == DeliveryStatus.PENDING for d in deliveries)
    assert all(d.next_attempt_at is not None for d in deliveries)


@pytest.mark.django_db
def test_emit_defers_dispatch_only_after_commit(
    fake_subscriber, django_capture_on_commit_callbacks
):
    fake_subscriber("test_sub_defer", lambda event: None)
    calls: list[str] = []

    import ham.outbox.dispatch as dispatch_module

    original = dispatch_module.defer_dispatch
    dispatch_module.defer_dispatch = lambda delivery_id: calls.append(delivery_id)
    try:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            with transaction.atomic():
                emit(
                    "Test.Deferred",
                    aggregate_type="thing",
                    aggregate_id=uuid.uuid4(),
                    payload={},
                )
            # Not yet run: emit() defers via transaction.on_commit, captured but not executed.
            assert calls == []
        assert len(callbacks) == 1
        for callback in callbacks:
            callback()
        # One deferred dispatch per registered subscriber (real + fake), all for this event.
        assert len(calls) == len(dispatch_module.registry.subscribers())
    finally:
        dispatch_module.defer_dispatch = original


@pytest.mark.django_db
def test_rollback_of_callers_transaction_leaves_no_event(fake_subscriber):
    fake_subscriber("test_sub_rollback", lambda event: None)

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with transaction.atomic():
            emit(
                "Test.WillRollBack",
                aggregate_type="thing",
                aggregate_id=uuid.uuid4(),
                payload={},
            )
            raise Boom

    assert OutboxEvent.objects.count() == 0
    assert OutboxDelivery.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bad_payload",
    [
        {"requester_email": "someone@example.org"},
        {"contact": "someone@example.org"},
        {"phone": "305-555-0100"},
        {"mobile_phone": "+1 305 555 0100"},
        {"full_name": "Kevin Torres"},
        {"address": "123 Main St"},
        {"street": "Main St"},
        {"circumstances": "flooded basement"},
        {"nested": {"email": "a@b.org"}},
        {"list_of_things": [{"phone": "3055550100"}]},
    ],
)
def test_emit_rejects_payloads_that_look_like_pii(bad_payload):
    with pytest.raises(PayloadPIIError):
        with transaction.atomic():
            emit(
                "Test.BadPayload",
                aggregate_type="thing",
                aggregate_id=uuid.uuid4(),
                payload=bad_payload,
            )
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db
def test_emit_accepts_ids_and_codes(fake_subscriber):
    fake_subscriber("test_sub_ok", lambda event: None)
    aggregate_id = uuid.uuid4()
    with transaction.atomic():
        emit(
            "Test.GoodPayload",
            aggregate_type="thing",
            aggregate_id=aggregate_id,
            payload={
                "project_id": str(uuid.uuid4()),
                "status": "confirmed",
                "count": 3,
            },
        )
    assert OutboxEvent.objects.filter(event_type="Test.GoodPayload").exists()


@pytest.mark.django_db
def test_emit_accepts_string_aggregate_id(fake_subscriber):
    fake_subscriber("test_sub_str_id", lambda event: None)
    aggregate_id = uuid.uuid4()
    with transaction.atomic():
        emit(
            "Test.StringAggregateId",
            aggregate_type="thing",
            aggregate_id=str(aggregate_id),
            payload={},
        )
    event = OutboxEvent.objects.get(event_type="Test.StringAggregateId")
    assert event.aggregate_id == aggregate_id
