"""`GET /audit`, `GET /audit/<id>`, `POST /audit/export` (foundation.md §7; auth-and-access.md
§H "Audit log"). Every read/export goes through `ham.authz.audit_access`, never
`ham.audit.queries` directly (repo convention)."""

from __future__ import annotations

import datetime as dt
import uuid

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from ham.audit.queries import AuditFilter
from ham.authz.audit_access import export_csv, get_event, list_events
from ham.authz.commands import ImpersonationBlocked, PermissionDenied, StepUpRequired
from ham.authz.guard import requires_action
from ham.identity.services import display_names_for
from ham.rules import RULES

from .stepup import redirect_to_step_up

_EXPORT_KIND = dict(RULES.auth.STEP_UP_ACTIONS)["audit.export"]


def _parse_filters(get) -> AuditFilter:
    date_from = None
    date_to = None
    if get.get("from"):
        date_from = dt.datetime.fromisoformat(get["from"]).replace(tzinfo=dt.UTC)
    if get.get("to"):
        date_to = dt.datetime.fromisoformat(get["to"]).replace(tzinfo=dt.UTC)
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
