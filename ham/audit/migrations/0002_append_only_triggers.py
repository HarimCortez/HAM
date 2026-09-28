"""Postgres triggers enforcing append-only `audit_event` (foundation.md §3, PRD §58).

UPDATE is always refused. DELETE is refused unless the transaction ran
`SET LOCAL ham.audit_purge = 'on'` (only the retention purge job does that; it deletes rows
older than `ham.rules.RULES.retention.AUDIT_RETENTION`, Q-036). This is the real enforcement;
the Python-level guards on the model (`AuditEvent.save`/`delete`) are defense in depth only —
a Django-level guard can't stop someone running raw SQL against the table.
"""

from django.db import migrations

_CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_event_block_write() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'audit_event rows are append-only; UPDATE is not permitted (PRD %)',
            '§58';
    ELSIF TG_OP = 'DELETE' THEN
        IF current_setting('ham.audit_purge', true) IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION
                'audit_event rows may only be deleted by the retention purge job '
                '(SET LOCAL ham.audit_purge = ''on'')';
        END IF;
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_DROP_FUNCTION = "DROP FUNCTION IF EXISTS audit_event_block_write() CASCADE;"

_CREATE_TRIGGER = """
CREATE TRIGGER audit_event_append_only
BEFORE UPDATE OR DELETE ON audit_event
FOR EACH ROW EXECUTE FUNCTION audit_event_block_write();
"""

_DROP_TRIGGER = "DROP TRIGGER IF EXISTS audit_event_append_only ON audit_event;"


class Migration(migrations.Migration):
    dependencies = [("ham_audit", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=_CREATE_FUNCTION, reverse_sql=_DROP_FUNCTION),
        migrations.RunSQL(sql=_CREATE_TRIGGER, reverse_sql=_DROP_TRIGGER),
    ]
