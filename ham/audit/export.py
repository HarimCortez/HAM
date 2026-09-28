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


# Security review M4: a cell that opens with any of these characters is interpreted by
# Excel/Sheets/LibreOffice as a formula, not text — a `reason` (free text, Q-050/L7) or any
# other field starting with one of these could otherwise run arbitrary formulas (including
# `=HYPERLINK(...)`/DDE payloads) on whoever opens the export.
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    if value and value[0] in _FORMULA_TRIGGER_CHARS:
        return "'" + value
    return value


def build_csv(events: list[AuditEvent]) -> bytes:
    """UTF-8 with a leading BOM so Excel opens it without mangling accents (PRD §58).

    Deliberately excludes `before`/`after`/`context` (may reference sensitive record IDs
    resolved elsewhere) and never includes requester name/address/phone (Q-050) — the export
    is IDs and staff-facing action codes only. Every column is passed through `_csv_safe`
    (security review M4: CSV formula injection), even columns that are normally IDs/codes,
    since defense in depth costs nothing here.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for event in events:
        writer.writerow(
            [
                _csv_safe(str(event.id)),
                _csv_safe(event.occurred_at.isoformat()),
                _csv_safe(str(event.actor_user_id or "")),
                _csv_safe(str(event.acting_as_user_id or "")),
                _csv_safe(event.action),
                _csv_safe(event.target_type),
                _csv_safe(event.target_id),
                _csv_safe(str(event.project_id or "")),
                _csv_safe(event.reason),
            ]
        )
    return ("﻿" + buf.getvalue()).encode("utf-8")
