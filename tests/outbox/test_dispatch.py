from __future__ import annotations

import datetime as dt
import uuid

import pytest
from django.db import transaction

from ham.outbox import services
from ham.outbox.api import emit
from ham.outbox.dispatch import dispatch_delivery
from ham.outbox.models import DeliveryStatus, OutboxDelivery
from ham.platform.clock import FixedClock, set_clock
from ham.rules.v1 import RULES


def _emit_one(fake_subscriber, name: str, handler) -> OutboxDelivery:
    fake_subscriber(name, handler)
    aggregate_id = uuid.uuid4()
    with transaction.atomic():
        emit(
            "Test.NeedsDelivery",
            aggregate_type="thing",
            aggregate_id=aggregate_id,
            payload={},
        )
    return OutboxDelivery.objects.get(subscriber=name)


@pytest.mark.django_db
def test_successful_delivery_is_marked_delivered(fake_subscriber):
    seen = []
    delivery = _emit_one(fake_subscriber, "test_ok", lambda event: seen.append(event.id))

    dispatch_delivery(delivery_id=str(delivery.id))

    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.DELIVERED
    assert delivery.delivered_at is not None
    assert delivery.attempts == 1
    assert delivery.last_error == ""
    assert seen == [delivery.event_id]


@pytest.mark.django_db
def test_adapter_failure_retries_with_exponential_backoff(fake_subscriber):
    clock = FixedClock(dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    set_clock(clock)
    try:

        def always_fails(event):
            raise ValueError("simulated adapter failure")

        delivery = _emit_one(fake_subscriber, "test_always_fails", always_fails)

        initial = RULES.outbox.OUTBOX_BACKOFF_INITIAL
        cap = RULES.outbox.OUTBOX_BACKOFF_MAX
        max_attempts = RULES.outbox.OUTBOX_MAX_ATTEMPTS

        for attempt in range(1, max_attempts):
            dispatch_delivery(delivery_id=str(delivery.id))
            delivery.refresh_from_db()
            assert delivery.attempts == attempt
            assert delivery.status == DeliveryStatus.FAILED
            expected_delay = min(initial * (2 ** (attempt - 1)), cap)
            assert delivery.next_attempt_at == clock.now() + expected_delay
            assert "simulated adapter failure" in delivery.last_error
            clock.advance(expected_delay)

        # One more failure at the attempt limit dead-letters the delivery.
        dispatch_delivery(delivery_id=str(delivery.id))
        delivery.refresh_from_db()
        assert delivery.attempts == max_attempts
        assert delivery.status == DeliveryStatus.DEAD
        assert delivery.next_attempt_at is None
    finally:
        from ham.platform.clock import SystemClock

        set_clock(SystemClock())


@pytest.mark.django_db
def test_delivery_never_retried_past_dead_letter(fake_subscriber):
    calls = []

    def always_fails(event):
        calls.append(1)
        raise ValueError("boom")

    delivery = _emit_one(fake_subscriber, "test_dead", always_fails)
    delivery.attempts = RULES.outbox.OUTBOX_MAX_ATTEMPTS
    delivery.status = DeliveryStatus.DEAD
    delivery.save(update_fields=["attempts", "status"])

    dispatch_delivery(delivery_id=str(delivery.id))

    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.DEAD
    assert calls == []  # dispatch_delivery is a no-op for an already-dead delivery


@pytest.mark.django_db
def test_retry_delivery_works_after_dead_letter(fake_subscriber):
    def always_fails(event):
        raise ValueError("boom")

    delivery = _emit_one(fake_subscriber, "test_retry", always_fails)
    delivery.attempts = RULES.outbox.OUTBOX_MAX_ATTEMPTS
    delivery.status = DeliveryStatus.DEAD
    delivery.next_attempt_at = None
    delivery.save(update_fields=["attempts", "status", "next_attempt_at"])

    # The integration comes back up: a later call registers a working handler under the same
    # subscriber name (this is exactly what an Admin's "Retry" button is for, §70.3).
    from ham.outbox import registry

    registry.register("test_retry", lambda event: None)

    services.retry_delivery(delivery.id)
    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.PENDING

    dispatch_delivery(delivery_id=str(delivery.id))
    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.DELIVERED


@pytest.mark.django_db
def test_dispatch_delivery_missing_id_is_a_no_op():
    dispatch_delivery(delivery_id=str(uuid.uuid4()))  # must not raise


@pytest.mark.django_db
def test_dispatch_delivery_unregistered_subscriber_is_a_no_op(fake_subscriber):
    fake_subscriber("test_temp", lambda event: None)
    delivery = _emit_one(fake_subscriber, "test_temp", lambda event: None)
    from ham.outbox import registry

    registry.unregister("test_temp")

    dispatch_delivery(delivery_id=str(delivery.id))

    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.PENDING  # untouched; nothing to dispatch to


@pytest.mark.django_db
def test_subscriber_status_counts_and_recent_failures(fake_subscriber):
    ok_delivery = _emit_one(fake_subscriber, "test_status_ok", lambda event: None)
    dispatch_delivery(delivery_id=str(ok_delivery.id))

    def always_fails(event):
        raise ValueError("boom")

    failing_delivery = _emit_one(fake_subscriber, "test_status_fail", always_fails)
    dispatch_delivery(delivery_id=str(failing_delivery.id))

    counts = {(c.subscriber, c.status): c.count for c in services.subscriber_status_counts()}
    assert counts[("test_status_ok", DeliveryStatus.DELIVERED)] == 1
    assert counts[("test_status_fail", DeliveryStatus.FAILED)] == 1

    failures = services.recent_failures()
    assert any(d.id == failing_delivery.id for d in failures)
    assert not any(d.id == ok_delivery.id for d in failures)
