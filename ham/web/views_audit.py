"""`GET /audit`, `GET /audit/<id>`, `POST /audit/export` (foundation.md §7; auth-and-access.md
§H "Audit log"). Every read/export goes through `ham.authz.audit_access`, never
`ham.audit.queries` directly (repo convention)."""

from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from ham.audit.queries import AuditFilter
from ham.authz.audit_access import export_csv, get_event, list_events
from ham.authz.commands import ImpersonationBlocked, PermissionDenied, StepUpRequired
from ham.authz.guard import requires_action
from ham.identity.services import display_names_for
from ham.platform.church import church_profile
from ham.rules import RULES

from .stepup import redirect_to_step_up

_EXPORT_KIND = dict(RULES.auth.STEP_UP_ACTIONS)["audit.export"]


def _church_zone() -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(church_profile().time_zone)
    except zoneinfo.ZoneInfoNotFoundError:  # pragma: no cover - defensive; validated on save
        return zoneinfo.ZoneInfo("UTC")


def _parse_church_date(value: str, *, end_of_day: bool) -> dt.datetime:
    """Q-030/§70.5: the H1 filter bar's date fields are interpreted in church-local time, not
    UTC or the server's own time zone — a plain "YYYY-MM-DD" is that whole calendar day in the
    church time zone. A value that already carries its own time/offset is trusted as-is."""
    if "T" in value:
        parsed = dt.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.UTC)
        return parsed
    local_date = dt.date.fromisoformat(value)
    local_time = dt.time(23, 59, 59, 999999) if end_of_day else dt.time(0, 0)
    local_dt = dt.datetime.combine(local_date, local_time, tzinfo=_church_zone())
    return local_dt.astimezone(dt.UTC)


def _parse_filters(get) -> AuditFilter:
    date_from = None
    date_to = None
    if get.get("from"):
        date_from = _parse_church_date(get["from"], end_of_day=False)
    if get.get("to"):
        date_to = _parse_church_date(get["to"], end_of_day=True)
    user_id = None
    if get.get("user"):
        try:
            user_id = uuid.UUID(get["user"])
        except ValueError:
            user_id = None
    project_id = None
    if get.get("project"):
        try:
            project_id = uuid.UUID(get["project"])
        except ValueError:
            project_id = None
    return AuditFilter(
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        project_id=project_id,
        action=get.get("action") or None,
        role=get.get("role") or None,
    )


@require_http_methods(["GET"])
@requires_action("audit.view")
def audit_log_list(request):
    filters = _parse_filters(request.GET)
    events = list_events(request.actor, filters, limit=50)
    names = display_names_for(
        [e.actor_user_id for e in events] + [e.acting_as_user_id for e in events]
    )
    return render(
        request,
        "web/audit_log_list.html",
        {"events": events, "names": names, "request_get": request.GET},
    )


@require_http_methods(["GET"])
@requires_action("audit.view")
def audit_log_detail(request, event_id: uuid.UUID):
    event = get_event(request.actor, event_id)
    if event is None:
        return render(request, "web/not_found.html", status=404)
    names = display_names_for([event.actor_user_id, event.acting_as_user_id])
    return render(request, "web/audit_log_detail.html", {"event": event, "names": names})


@require_http_methods(["POST"])
@requires_action("audit.export")
def audit_export(request):
    filters = _parse_filters(request.POST)
    try:
        data = export_csv(request.actor, filters)
    except StepUpRequired:
        return redirect_to_step_up(request, request.path, _EXPORT_KIND)
    except ImpersonationBlocked:
        return render(
            request,
            "web/audit_log_list.html",
            {
                "events": list_events(request.actor, filters, limit=50),
                "names": {},
                "request_get": request.GET,
                "export_blocked": True,
            },
        )
    except PermissionDenied:
        return render(request, "web/not_found.html", status=404)
    response = HttpResponse(data, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="ham-audit-log.csv"'
    return response
