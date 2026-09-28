from __future__ import annotations

import logging
import uuid

import pytest
from django.db import transaction

from ham.integrations.calendar import NoOpCalendarAdapter, handle_calendar_event
from ham.integrations.drive import NoOpDriveAdapter, handle_drive_event
from ham.integrations.fitness import NoOpFitnessAdapter, handle_fitness_event
from ham.outbox.api import emit
from ham.outbox.models import OutboxEvent


@pytest.mark.django_db
def test_calendar_stub_logs_event_type_and_ids_only(caplog):
    caplog.set_level(logging.INFO)
    aggregate_id = uuid.uuid4()
    with transaction.atomic():
        emit(
            "Test.ForCalendar",
            aggregate_type="project",
            aggregate_id=aggregate_id,
            payload={"project_id": str(aggregate_id)},
        )
    event = OutboxEvent.objects.get(event_type="Test.ForCalendar")

    handle_calendar_event(event)

    records = [r for r in caplog.records if "outbox.calendar" in r.getMessage()]
    assert len(records) == 1
    record = records[0]
    assert record.event_type == "Test.ForCalendar"
    assert record.event_id == str(event.id)
    assert record.aggregate_id == str(aggregate_id)
    assert "payload" not in record.__dict__


def test_noop_calendar_adapter_never_raises_and_returns_no_reference():
    adapter = NoOpCalendarAdapter()
    assert adapter.upsert_event(project_id="p", title="t", start="s", end="e") == ""
    adapter.delete_event(calendar_event_reference="whatever")


def test_noop_fitness_adapter_is_a_no_op():
    NoOpFitnessAdapter().record_activity(volunteer_id="v", event_type="checkin", occurred_at="x")


def test_noop_drive_adapter_returns_no_file_id():
    assert NoOpDriveAdapter().upload_file(folder_id="f", file_name="n", content_type="c") == ""


@pytest.mark.django_db
def test_fitness_and_drive_stubs_are_no_ops(caplog):
    caplog.set_level(logging.DEBUG)
    aggregate_id = uuid.uuid4()
    with transaction.atomic():
        emit(
            "Test.ForFitnessAndDrive",
            aggregate_type="thing",
            aggregate_id=aggregate_id,
            payload={},
        )
    event = OutboxEvent.objects.get(event_type="Test.ForFitnessAndDrive")

    handle_fitness_event(event)  # must not raise
    handle_drive_event(event)  # must not raise
