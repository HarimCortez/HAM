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

from ham.audit.labels import ACTION_GROUPS
from ham.audit.queries import AuditFilter
from ham.authz import roles
from ham.authz.audit_access import export_csv, get_event, list_events
from ham.authz.commands import ImpersonationBlocked, PermissionDenied, StepUpRequired
from ham.authz.guard import requires_action
from ham.identity.services import UserListFilters, display_names_for, list_users
from ham.platform.church import church_profile
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from .stepup import redirect_to_step_up

_EXPORT_KIND = dict(RULES.auth.STEP_UP_ACTIONS)["audit.export"]

# usability M7: date-range presets on the H1 filter bar. Today's church-local calendar day is
# always in the list; the rest are rolling windows ending today.
_RANGE_PRESETS: tuple[tuple[str, str, int], ...] = (
    ("today", "Today", 0),
    ("7", "Last 7 days", 7),
    ("30", "Last 30 days", 30),
)


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


def _range_dates(range_key: str) -> tuple[str, str]:
    """A preset's `from`/`to` as church-local "YYYY-MM-DD" strings, so it plugs into the same
    parsing as a typed date (usability M7: "presets like Last 7/30 days")."""
    days = next((n for key, _label, n in _RANGE_PRESETS if key == range_key), 0)
    today_local = clock_now().astimezone(_church_zone()).date()
    start = today_local - dt.timedelta(days=days)
    return start.isoformat(), today_local.isoformat()


def _resolve_user_filter(get) -> tuple[uuid.UUID | None, list]:
    """The G2 "See all in audit log" link passes a raw `user` UUID; the H1 filter bar itself
    offers a plain-language name/email search instead (usability M5/M7: "no internal IDs" and
    "a User search control"). Returns `(user_id, other_matches)`; `other_matches` is only
    non-empty when the typed text matched more than one person, so the template can offer a
    pick list instead of silently filtering by nothing or the wrong person."""
    if get.get("user"):
        try:
            return uuid.UUID(get["user"]), []
        except ValueError:
            pass
    query = (get.get("user_q") or "").strip()
    if not query:
        return None, []
    matches = list_users(UserListFilters(q=query))
    if len(matches) == 1:
        return matches[0].user.id, []
    return None, matches[:10]


def _parse_filters(get) -> AuditFilter:
    range_key = get.get("range") or ""
    from_value = get.get("from") or ""
    to_value = get.get("to") or ""
    if range_key and range_key != "custom":
        from_value, to_value = _range_dates(range_key)
    date_from = _parse_church_date(from_value, end_of_day=False) if from_value else None
    date_to = _parse_church_date(to_value, end_of_day=True) if to_value else None
    user_id, _user_matches = _resolve_user_filter(get)
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


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _range_label(get) -> str:
    range_key = get.get("range") or ""
    for key, label, _n in _RANGE_PRESETS:
        if key == range_key:
            return label
    if get.get("from") or get.get("to"):
        return "Custom dates"
    return "All time"


def _list_context(request, *, export_blocked: bool = False) -> dict[str, object]:
    """Shared by the list page and the "export blocked while impersonating" re-render, so
    both show the same filter bar, presets and human-readable rows (usability M5/M6/M7)."""
    get = request.GET if not export_blocked else request.POST
    filters = _parse_filters(get)
    events = list_events(request.actor, filters, limit=50)
    target_user_ids = [
        uuid.UUID(e.target_id) for e in events if e.target_type == "user" and _is_uuid(e.target_id)
    ]
    names = display_names_for(
        [e.actor_user_id for e in events] + [e.acting_as_user_id for e in events] + target_user_ids
    )
    _user_id, user_matches = _resolve_user_filter(get)
    return {
        "events": events,
        "names": names,
        "request_get": get,
        "action_groups": ACTION_GROUPS,
        "range_presets": _RANGE_PRESETS,
        "range_label": _range_label(get),
        "role_choices": sorted(roles.ROLE_LABELS, key=lambda code: roles.ROLE_LABELS[code]),
        "role_labels": roles.ROLE_LABELS,
        "user_matches": user_matches,
        "export_blocked": export_blocked,
    }


@require_http_methods(["GET"])
@requires_action("audit.view")
def audit_log_list(request):
    return render(request, "web/audit_log_list.html", _list_context(request))


@require_http_methods(["GET"])
@requires_action("audit.view")
def audit_log_detail(request, event_id: uuid.UUID):
    event = get_event(request.actor, event_id)
    if event is None:
        return render(request, "web/not_found.html", status=404)
    ids = [event.actor_user_id, event.acting_as_user_id]
    if event.target_type == "user" and _is_uuid(event.target_id):
        ids.append(uuid.UUID(event.target_id))
    names = display_names_for(ids)
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
        context = _list_context(request, export_blocked=True)
        return render(request, "web/audit_log_list.html", context)
    except PermissionDenied:
        return render(request, "web/not_found.html", status=404)
    response = HttpResponse(data, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="ham-audit-log.csv"'
    return response
