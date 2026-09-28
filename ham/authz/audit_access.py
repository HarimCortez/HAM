"""Authorized entry points for the audit viewer and export (PRD §58, Q-010).

`ham.audit.queries`/`ham.audit.export` are pure data/formatting with no authorization (so
`ham.audit` never has to import `ham.authz` — see the comment in `commands.py`). Views must
call through here instead of `ham.audit.queries` directly, so every read/export is checked.
"""

from __future__ import annotations

import csv
import io

from django.db import transaction

from ham.audit.export import build_csv
from ham.audit.models import AuditEvent
from ham.audit.queries import AuditFilter
from ham.audit.queries import list_events as _list_events
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from . import commands as _commands
from .commands import ImpersonationBlocked, PermissionDenied, StepUpRequired
from .context import ActorContext
from .matrix import authorize

_EXPORT_STEP_UP_KIND = dict(RULES.auth.STEP_UP_ACTIONS)["audit.export"]

# Q-095: a free-text `reason` may contain a person's name or circumstances someone typed in
# (Q-050) — it stays visible in the audit *viewer* (a leader looking at their own action) but
# is excluded from the CSV export, which can leave the building. `ham.audit.export.build_csv`
# is Fix A's file, so the column drop happens here (authorization/output-shaping layer)
# instead, keyed off the module's own `CSV_COLUMNS` order rather than a hard-coded index.
_EXCLUDED_EXPORT_COLUMNS = frozenset({"reason"})


def _drop_excluded_columns(data: bytes) -> bytes:
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return data
    header = rows[0]
    keep_indexes = [i for i, name in enumerate(header) if name not in _EXCLUDED_EXPORT_COLUMNS]
    out = io.StringIO()
    writer = csv.writer(out)
    for row in rows:
        writer.writerow([row[i] for i in keep_indexes if i < len(row)])
    return ("﻿" + out.getvalue()).encode("utf-8")


def list_events(
    ctx: ActorContext,
    filters: AuditFilter | None = None,
    *,
    before_seq: int | None = None,
    limit: int = 50,
) -> list[AuditEvent]:
    decision = authorize(ctx, "audit.view")
    if not decision.allowed:
        raise PermissionDenied(f"audit.view: {decision.reason}")
    return _list_events(filters, before_seq=before_seq, limit=limit)


def list_events_for_target(
    ctx: ActorContext, *, target_type: str, target_id: str, limit: int = 5
) -> list[AuditEvent]:
    """The last `limit` events *about* one record (G2 "Recent access changes"), e.g.
    `target_type="user"` for role grants/revokes/resets/impersonations on that person. Same
    `audit.view` authorization as the full log (Admin and Director, foundation.md §4)."""
    decision = authorize(ctx, "audit.view")
    if not decision.allowed:
        raise PermissionDenied(f"audit.view: {decision.reason}")
    return _list_events(AuditFilter(target_type=target_type, target_id=target_id), limit=limit)


def get_event(ctx: ActorContext, event_id) -> AuditEvent | None:
    decision = authorize(ctx, "audit.view")
    if not decision.allowed:
        raise PermissionDenied(f"audit.view: {decision.reason}")
    from ham.audit.queries import get_event as _get_event

    return _get_event(event_id)


def export_csv(ctx: ActorContext, filters: AuditFilter | None = None) -> bytes:
    """Export the current filter set as CSV, recording `audit.exported` (PRD §58)."""
    decision = authorize(ctx, "audit.export")
    if not decision.allowed:
        assert _commands._audit_record is not None
        _commands._audit_record(
            ctx=ctx,
            action="authz.denied",
            target_type="action",
            target_id="audit.export",
            reason=decision.reason,
        )
        raise PermissionDenied(f"audit.export: {decision.reason}")
    if decision.blocked_by_impersonation:
        assert _commands._audit_record is not None
        _commands._audit_record(
            ctx=ctx,
            action="impersonation.action_blocked",
            target_type="action",
            target_id="audit.export",
            reason="blocked while impersonating (§59)",
        )
        raise ImpersonationBlocked("audit.export")
    if not ctx.has_fresh_step_up(
        _EXPORT_STEP_UP_KIND, now=clock_now(), freshness=RULES.auth.STEP_UP_WINDOW
    ):
        raise StepUpRequired("audit.export", _EXPORT_STEP_UP_KIND)

    filters = filters or AuditFilter()
    with transaction.atomic():
        events = _list_events(filters, limit=100_000)
        data = _drop_excluded_columns(build_csv(events))
        assert _commands._audit_record is not None  # AuthzConfig.ready() always registers this
        _commands._audit_record(
            ctx=ctx,
            action="audit.exported",
            target_type="audit_export",
            target_id=str(len(events)),
            reason="",
            context={"filters": filters.as_dict(), "row_count": len(events), "format": "csv"},
        )
    return data
