"""Audit viewer data access (foundation.md §2.5, PRD §58): filters by date range, user,
project, action, role; paginated by `seq` (newest first).

Pure data access, no authorization here (ham.audit must not import ham.authz — foundation.md
§1 dependency rules put authz above audit). Callers must authorize first; see
`ham.authz.audit_access` for the authorized, step-up-checked entry point used by views.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from django.db.models import Q

from .models import AuditEvent

DEFAULT_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class AuditFilter:
    date_from: dt.datetime | None = None
    date_to: dt.datetime | None = None
    user_id: UUID | None = None
    project_id: UUID | None = None
    action: str | None = None
    role: str | None = None

    def as_dict(self) -> dict[str, str]:
        """PII-free filter summary for the `audit.exported` event's `context` (Q-050: IDs and
        codes only)."""
        out: dict[str, str] = {}
        if self.date_from:
            out["date_from"] = self.date_from.isoformat()
        if self.date_to:
            out["date_to"] = self.date_to.isoformat()
        if self.user_id:
            out["user_id"] = str(self.user_id)
        if self.project_id:
            out["project_id"] = str(self.project_id)
        if self.action:
            out["action"] = self.action
        if self.role:
            out["role"] = self.role
        return out


def _queryset(filters: AuditFilter):
    qs = AuditEvent.objects.all()
    if filters.date_from:
        qs = qs.filter(occurred_at__gte=filters.date_from)
    if filters.date_to:
        qs = qs.filter(occurred_at__lte=filters.date_to)
    if filters.user_id:
        qs = qs.filter(Q(actor_user_id=filters.user_id) | Q(acting_as_user_id=filters.user_id))
    if filters.project_id:
        qs = qs.filter(project_id=filters.project_id)
    if filters.action:
        qs = qs.filter(action=filters.action)
    if filters.role:
        qs = qs.filter(actor_roles__contains=[filters.role])
    return qs


def list_events(
    filters: AuditFilter | None = None,
    *,
    before_seq: int | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> list[AuditEvent]:
    """Newest-first page of events matching `filters`, before `before_seq` if given."""
    qs = _queryset(filters or AuditFilter())
    if before_seq is not None:
        qs = qs.filter(seq__lt=before_seq)
    return list(qs[:limit])


def get_event(event_id: UUID) -> AuditEvent | None:
    return AuditEvent.objects.filter(id=event_id).first()
