from __future__ import annotations

import pytest
from django.db import connection, transaction

from ham.audit.models import AppendOnlyError, AuditEvent
from ham.audit.services import record

pytestmark = pytest.mark.django_db


def _make_event() -> AuditEvent:
    return record(
        ctx=None,
        actor_type="system",
        action="user.created",
        target_type="user",
        target_id="u1",
    )


class TestPythonLevelGuards:
    def test_save_on_existing_row_raises(self):
        event = _make_event()
        event.reason = "changed my mind"
        with pytest.raises(AppendOnlyError):
            event.save()

    def test_delete_raises(self):
        event = _make_event()
        with pytest.raises(AppendOnlyError):
            event.delete()


class TestDatabaseTrigger:
    def test_raw_update_is_refused(self):
        event = _make_event()
        with pytest.raises(Exception, match="append-only"):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE audit_event SET reason = %s WHERE seq = %s",
                        ["tampered", event.seq],
                    )

    def test_raw_delete_without_purge_flag_is_refused(self):
        event = _make_event()
        with pytest.raises(Exception, match="retention purge job"):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM audit_event WHERE seq = %s", [event.seq])

    def test_raw_delete_with_purge_flag_succeeds(self):
        event = _make_event()
        seq = event.seq
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ham.audit_purge = 'on'")
                cursor.execute("DELETE FROM audit_event WHERE seq = %s", [seq])
        assert not AuditEvent.objects.filter(seq=seq).exists()

    @pytest.mark.django_db(transaction=True)
    def test_purge_flag_does_not_leak_across_transactions(self):
        # SET LOCAL is scoped to one transaction; a later transaction must be refused again.
        _make_event()
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ham.audit_purge = 'on'")
        another = _make_event()
        with pytest.raises(Exception, match="retention purge job"):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM audit_event WHERE seq = %s", [another.seq])
