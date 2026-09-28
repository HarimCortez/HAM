from __future__ import annotations

import uuid

import pytest
from django.db import transaction

from ham.integrations.email.notifications import (
    NotificationEmail,
    handle_email_event,
    register_notification,
    unregister_notification,
)
from ham.outbox.api import emit
from ham.outbox.models import OutboxEvent


@pytest.mark.django_db
def test_no_builder_registered_is_a_documented_no_op(mailoutbox, caplog):
    aggregate_id = uuid.uuid4()
    with transaction.atomic():
        emit(
            "Test.NothingRegistered",
            aggregate_type="thing",
            aggregate_id=aggregate_id,
            payload={},
        )
    event = OutboxEvent.objects.get(event_type="Test.NothingRegistered")

    handle_email_event(event)

    assert mailoutbox == []


@pytest.mark.django_db
def test_registered_builder_sends_an_email(mailoutbox):
    aggregate_id = uuid.uuid4()

    def builder(event: OutboxEvent) -> NotificationEmail:
        return NotificationEmail(
            to="volunteer@example.org",
            subject="You were invited",
            text_body=f"Event {event.event_type} for {event.aggregate_id}",
            category="volunteer_invited",
        )

    register_notification("Test.VolunteerInvited", builder)
    try:
        with transaction.atomic():
            emit(
                "Test.VolunteerInvited",
                aggregate_type="thing",
                aggregate_id=aggregate_id,
                payload={},
            )
        event = OutboxEvent.objects.get(event_type="Test.VolunteerInvited")

        handle_email_event(event)

        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["volunteer@example.org"]
    finally:
        unregister_notification("Test.VolunteerInvited")


@pytest.mark.django_db
def test_builder_returning_none_sends_nothing(mailoutbox):
    aggregate_id = uuid.uuid4()
    register_notification("Test.NoEmailWanted", lambda event: None)
    try:
        with transaction.atomic():
            emit(
                "Test.NoEmailWanted",
                aggregate_type="thing",
                aggregate_id=aggregate_id,
                payload={},
            )
        event = OutboxEvent.objects.get(event_type="Test.NoEmailWanted")

        handle_email_event(event)

        assert mailoutbox == []
    finally:
        unregister_notification("Test.NoEmailWanted")
