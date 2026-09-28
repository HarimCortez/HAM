"""CSV formatting for the audit export (PRD §58: "opens in Excel" -> UTF-8 with a BOM).

Pure formatting: no authorization, no recording of the `audit.exported` event itself (that
needs `ActorContext`/step-up, which live in `ham.authz`; see `ham.authz.audit_access`, which
is the entry point views should call).
"""

from __future__ import annotations

import csv
import io

from .models import AuditEvent

CSV_COLUMNS = (
    "event_id",
    "occurred_at_utc",
    "actor_user_id",
    "acting_as_user_id",
    "action",
    "target_type",
    "target_id",
    "project_id",
    "reason",
)


def build_csv(events: list[AuditEvent]) -> bytes:
    """UTF-8 with a leading BOM so Excel opens it without mangling accents (PRD §58).

    Deliberately excludes `before`/`after`/`context` (may reference sensitive record IDs
    resolved elsewhere) and never includes requester name/address/phone (Q-050) — the export
    is IDs and staff-facing action codes only.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for event in events:
        writer.writerow(
            [
                str(event.id),
                event.occurred_at.isoformat(),
                str(event.actor_user_id or ""),
                str(event.acting_as_user_id or ""),
                event.action,
                event.target_type,
                event.target_id,
                str(event.project_id or ""),
                event.reason,
            ]
        )
    return ("﻿" + buf.getvalue()).encode("utf-8")
