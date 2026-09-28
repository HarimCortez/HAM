"""ham.notifications.inapp: the `inapp` outbox subscriber + `register_inapp` builder registry
(intake.md §2 "Convention change", mirrors ham.integrations.email.notifications)."""

from __future__ import annotations

import uuid

import pytest
from django.db import transaction

from ham.notifications.inapp import (
    InAppNotice,
    handle_inapp_event,
    register_inapp,
    unregister_inapp,
)
from ham.notifications.models import Notification
from ham.notifications.validation import NotificationTitlePIIError
from ham.outbox.api import emit
from ham.outbox.models import OutboxEvent

pytestmark = pytest.mark.django_db


def _emit(event_type: str, *, aggregate_id=None, payload=None) -> OutboxEvent:
    aggregate_id = aggregate_id or uuid.uuid4()
    with transaction.atomic():
        emit(
            event_type,
            aggregate_type="thing",
            aggregate_id=aggregate_id,
            payload=payload or {},
        )
    return OutboxEvent.objects.get(event_type=event_type, aggregate_id=aggregate_id)


def test_no_builder_registered_is_a_documented_no_op(caplog):
    event = _emit("Test.NothingRegistered")
    handle_inapp_event(event)
    assert Notification.objects.count() == 0


def test_registered_builder_creates_a_notification_row():
    recipient_id = uuid.uuid4()
    subject_id = uuid.uuid4()

    def builder(event: OutboxEvent) -> InAppNotice:
        return InAppNotice(
            recipient_user_id=recipient_id,
            kind="request_awaiting_approval",
            subject_type="request",
            subject_id=subject_id,
            title="A request is waiting for a decision",
        )

    register_inapp("Test.RequestAwaitingApproval", builder)
    try:
        event = _emit("Test.RequestAwaitingApproval")
        handle_inapp_event(event)
        notification = Notification.objects.get()
        assert notification.recipient_user_id == recipient_id
        assert notification.subject_id == subject_id
        assert notification.outbox_event_id == event.id
        assert notification.urgent is False
        assert notification.requires_ack is False
        assert notification.read_at is None
        assert notification.acknowledged_at is None
    finally:
        unregister_inapp("Test.RequestAwaitingApproval")


def test_a_builder_can_return_a_list_for_multiple_recipients():
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

    def builder(event: OutboxEvent) -> list[InAppNotice]:
        return [
            InAppNotice(
                recipient_user_id=user_id,
                kind="urgent_request",
                subject_type="request",
                subject_id=uuid.uuid4(),
                title="An urgent request needs certification",
                urgent=True,
                requires_ack=True,
            )
            for user_id in ids
        ]

    register_inapp("Test.UrgentBroadcast", builder)
    try:
        event = _emit("Test.UrgentBroadcast")
        handle_inapp_event(event)
        recipients = set(Notification.objects.values_list("recipient_user_id", flat=True))
        assert recipients == set(ids)
        assert all(Notification.objects.values_list("urgent", flat=True))
        assert all(Notification.objects.values_list("requires_ack", flat=True))
    finally:
        unregister_inapp("Test.UrgentBroadcast")


def test_builder_returning_none_creates_nothing():
    def builder(event: OutboxEvent) -> None:
        return None

    register_inapp("Test.Skipped", builder)
    try:
        event = _emit("Test.Skipped")
        handle_inapp_event(event)
        assert Notification.objects.count() == 0
    finally:
        unregister_inapp("Test.Skipped")


class TestNoPIIInTitle:
    def test_a_title_that_looks_like_an_email_is_rejected(self):
        def builder(event: OutboxEvent) -> InAppNotice:
            return InAppNotice(
                recipient_user_id=uuid.uuid4(),
                kind="oops",
                subject_type="request",
                subject_id=uuid.uuid4(),
                title="Contact doris@example.org about this",
            )

        register_inapp("Test.LeakyEmail", builder)
        try:
            event = _emit("Test.LeakyEmail")
            with pytest.raises(NotificationTitlePIIError):
                handle_inapp_event(event)
            assert Notification.objects.count() == 0
        finally:
            unregister_inapp("Test.LeakyEmail")

    def test_a_title_that_looks_like_a_phone_number_is_rejected(self):
        def builder(event: OutboxEvent) -> InAppNotice:
            return InAppNotice(
                recipient_user_id=uuid.uuid4(),
                kind="oops",
                subject_type="request",
                subject_id=uuid.uuid4(),
                title="Call 555-123-4567 about this",
            )

        register_inapp("Test.LeakyPhone", builder)
        try:
            event = _emit("Test.LeakyPhone")
            with pytest.raises(NotificationTitlePIIError):
                handle_inapp_event(event)
            assert Notification.objects.count() == 0
        finally:
            unregister_inapp("Test.LeakyPhone")
