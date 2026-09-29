"""GET /healthz — public (foundation.md §7 route table). Checks the database and the job
queue for a stalled worker. Never returns anything beyond booleans/numbers (PRD §68: no PII
in a public endpoint's response)."""

from __future__ import annotations

import time
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from ham.authz.guard import requires_action
from ham.authz.matrix import authorize
from ham.jobs import queue_lag_seconds
from ham.platform.brand import load_brand
from ham.platform.church import church_profile
from ham.platform.tokens import token_hex
from ham.rules import RULES


@require_GET
def healthz(request):
    checks: dict[str, object] = {}
    healthy = True

    started = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        healthy = False
    checks["database_latency_ms"] = round((time.monotonic() - started) * 1000, 1)

    try:
        lag = queue_lag_seconds()
        checks["job_queue_lag_seconds"] = lag
        # PRD-GAP Q-056: proposed default in use; owner may change.
        max_lag = RULES.operations.HEALTH_MAX_QUEUE_LAG.total_seconds()
        if lag is not None and lag > max_lag:
            healthy = False
    except Exception:
        checks["job_queue"] = "error"
        healthy = False

    status = "ok" if healthy else "degraded"
    return JsonResponse({"status": status, "checks": checks}, status=200 if healthy else 503)


# ---------------------------------------------------------------------------------------
# App shell (foundation.md §7, §10 "step 1")
# ---------------------------------------------------------------------------------------


@require_GET
@requires_action("shell.use")
def home(request):
    """Home placeholder (foundation.md §10 "Home placeholder per highest role"). Real per-role
    to-do cards land with staffing/projects; every signed-in person sees the same placeholder
    for now (navigation.md §1), plus two step-1-only additions: an Administrator's summary of
    integrations health and recent sign-in failures (counts/times only, §68 — never who), and
    an "Invite someone" card for anyone who may invite but has no `user.list` nav destination
    (an Assistant Director, Q-082)."""
    ctx = request.actor
    from ham.identity.services import display_names_for

    full_name = display_names_for([ctx.user_id]).get(ctx.user_id, "")
    context: dict[str, object] = {"first_name": full_name.split(" ")[0] if full_name else ""}
    if authorize(ctx, "integrations.view_status").allowed:
        from ham.outbox.services import subscriber_status_counts

        from .views_admin_settings import _VISIBLE_SUBSCRIBERS

        context["integration_counts"] = [
            row for row in subscriber_status_counts() if row.subscriber in _VISIBLE_SUBSCRIBERS
        ]
        context["recent_sign_in_failures"] = _recent_sign_in_failures(ctx)
    if authorize(ctx, "user.invite").allowed and not authorize(ctx, "user.list").allowed:
        context["show_invite_card"] = True

    # S2.8 (intake.md §6, navigation.md §8.3 group 4): "Needs your attention" — computed live
    # by every registered attention provider, never stored (ham.notifications.attention). The
    # urgent banner itself is app-wide (see ham.web.context_processors.shell), not set here.
    from ham.notifications.services import needs_response_for

    items = needs_response_for(ctx)
    context["attention_items"] = items
    # FIX-F1 minor 1: only the first urgent+actionable card is a primary (solid) button --
    # a whole column of solid-primary "Open" buttons (seen with a lot of urgent awaiting-
    # approval requests at once) breaks the "one primary action" pattern.
    first_urgent = next((item for item in items if item.urgent and not item.muted), None)
    context["first_urgent_kind"] = first_urgent.kind if first_urgent else None
    # FIX-3B UX m1: "{n} things need you" in the greeting -- a small, additively-named context
    # key (not a template-side count, since `attention_items` may hold aggregate cards worth
    # more than 1 each in a future round; today it's just `len()`).
    context["attention_count"] = len(items)
    return render(request, "web/home.html", context)


def _recent_sign_in_failures(ctx) -> dict[str, object]:
    """Counts/times only (§68: never names or emails) of recent lockouts, for the
    Administrator Home summary (foundation.md §10). Goes through `ham.authz.audit_access`
    (never `ham.audit.queries` directly, repo convention) even though the caller has already
    checked `integrations.view_status`, so this stays authorized the same way the audit log
    itself is."""
    from ham.audit.queries import AuditFilter
    from ham.authz.audit_access import list_events
    from ham.platform.clock import now as clock_now
    from ham.rules import RULES

    since = clock_now() - RULES.operations.RECENT_ACTIVITY_WINDOW
    events = list_events(ctx, AuditFilter(action="auth.sign_in.locked", date_from=since), limit=200)
    return {
        "count": len(events),
        "latest_at": events[0].occurred_at if events else None,
        "window_hours": int(RULES.operations.RECENT_ACTIVITY_WINDOW.total_seconds() // 3600),
    }


@require_GET
@requires_action("shell.use")
def inbox(request):
    """Inbox: "Needs response" (live attention items) + "Updates" (stored notifications)
    (foundation.md §10; navigation.md §4; intake.md §6, PRD §35). The urgent banner is
    app-wide (ham.web.context_processors.shell), not set here."""
    from ham.notifications.services import needs_response_for, updates_for

    ctx = request.actor
    return render(
        request,
        "web/inbox.html",
        {
            "needs_response": needs_response_for(ctx),
            "updates": updates_for(ctx),
        },
    )


@require_http_methods(["POST"])
@requires_action("notification.acknowledge")
def notification_acknowledge(request, notification_id):
    """Acknowledges the app-wide urgent banner for this person (§10/§35, Q-123)."""
    from ham.authz.commands import PermissionDenied
    from ham.notifications.services import acknowledge_notification

    try:
        acknowledge_notification(request.actor, notification_id=notification_id)
    except PermissionDenied:
        pass
    next_url = request.POST.get("next") or reverse("web:home")
    return redirect(next_url)


_NOTIFICATION_SUBJECT_URL_NAMES = {
    "request": "web:request_detail",
}


@require_GET
@requires_action("shell.use")
def notification_open(request, notification_id):
    """Usability M13: an Inbox "Updates" row is a link, not inert text -- opens the
    notification's subject (marking it read on the way) instead of leaving the pastor to find
    the request themselves on the Requests list.

    N7: while impersonating, this reads the notification without marking it read
    (`get_owned_notification`, not `mark_read`) -- an Administrator browsing someone else's
    inbox to look something up shouldn't silently change what that person sees as unread when
    they next sign in themselves. A malformed/unknown subject (bad `subject_type`, or a
    `subject_id` that no longer reverses to a real route, e.g. a since-deleted request) always
    redirects to the inbox rather than 500ing."""
    from django.urls import NoReverseMatch

    from ham.notifications.services import get_owned_notification, mark_read

    ctx = request.actor
    if ctx.is_impersonating:
        notification = get_owned_notification(ctx, notification_id)
    else:
        notification = mark_read(ctx, notification_id)
    if notification is None:
        return redirect("web:inbox")
    url_name = _NOTIFICATION_SUBJECT_URL_NAMES.get(notification.subject_type)
    if url_name is None:
        return redirect("web:inbox")
    try:
        return redirect(url_name, request_id=notification.subject_id)
    except NoReverseMatch:
        return redirect("web:inbox")


@require_GET
@requires_action("shell.use")
def admin_index(request):
    """The Admin hub (visual QA C2 / usability C2, Q-091): a plain server-rendered list of the
    admin-group destinations (Users & roles, Church settings, Integrations, Rules, Audit log)
    this viewer may use, so they share one mobile tab instead of five. `nav.admin_group_items`
    already applies `authorize()` per item, so this page shows exactly what the sidebar/rail
    would — nothing here grants access beyond the per-route guard on each destination."""
    from ham.web.nav import admin_group_items_for

    return render(request, "web/admin_index.html", {"admin_items": admin_group_items_for(request)})


@require_GET
@requires_action("shell.use")
def more(request):
    """The More page (visual QA C2 / usability C2, Q-091): whatever this role's built nav has
    left over once Home/Admin/Inbox have their own tab — Me, and for a Director-like role,
    the admin-group items too — plus Sign out, so it's always reachable on a phone."""
    from ham.web.nav import more_items_for

    return render(request, "web/more.html", {"more_nav_items": more_items_for(request)})


@require_GET
def offline(request):
    """The offline fallback page the service worker serves on a failed navigation
    (frontend/src/sw.ts). Public: it must render with no session and no network."""
    return render(request, "web/offline.html")


@require_GET
def manifest(request):
    """PWA manifest, built from the church profile + brand (foundation.md §10 "The PWA
    manifest ... come from the church profile"). Icons use the brand's `mark` logo
    (design-system/README.md "Logo usage": "For the PWA icon, put the mark logo centered on
    white at 80% safe zone")."""
    brand = load_brand()
    church = church_profile()
    icon_url = staticfiles_storage.url(f"brands/{brand.id}/{brand.logo_mark}")
    data = {
        "name": f"{church.short_name} HAM",
        "short_name": "HAM",
        "description": church.mission_line,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": token_hex("ham-color-neutral-0"),
        # The app bar is dark ink in both themes (design-system/README.md "Color decisions"),
        # so the PWA splash/theme color matches it rather than the brand color.
        "theme_color": token_hex("ham-color-neutral-950"),
        "lang": "en-US",
        "icons": [
            {"src": icon_url, "sizes": "any", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    return JsonResponse(data, content_type="application/manifest+json")


@require_GET
def service_worker(request):
    """Serves the esbuild-built service worker (frontend/src/sw.ts -> frontend/dist/sw.js)
    from the root, with `Service-Worker-Allowed: /` so its scope covers the whole app even
    though it is technically served from a static-files path (foundation.md §10)."""
    sw_path = Path(settings.BASE_DIR) / "frontend" / "dist" / "sw.js"
    if not sw_path.exists():
        # frontend/ hasn't been built yet (dev machine without `npm run build`). Fail soft: a
        # near-empty script is safer than a 404, which would break `serviceWorker.register()`.
        body = b"// frontend/dist/sw.js not built yet; run `npm run build` in frontend/.\n"
    else:
        body = sw_path.read_bytes()
    response = HttpResponse(body, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@require_GET
@requires_action("me.view")
def api_me(request):
    """`GET /api/v1/me` (foundation.md §10): id, display name, roles, nav, impersonation
    state, rules_version. Never email or phone (§68) — those are only on the `Me` screen
    itself, which the signed-in person is looking at their own record on."""
    from ham.authz.nav import nav_for
    from ham.identity.services import display_names_for
    from ham.rules import RULES_VERSION

    ctx = request.actor
    names = display_names_for([ctx.user_id])
    nav = [
        {"key": item.key, "label": item.label, "url": reverse(item.url_name)}
        for item in nav_for(ctx)
    ]
    data = {
        "id": str(ctx.user_id),
        "display_name": names.get(ctx.user_id, ""),
        "roles": sorted(ctx.effective_roles),
        "nav": nav,
        "impersonation": {
            "active": ctx.is_impersonating,
            "target_display_name": ctx.target_display_name if ctx.is_impersonating else "",
        },
        "rules_version": RULES_VERSION,
    }
    return JsonResponse(data)


def not_found(request, exception=None):
    """The neutral 'no permission / not found' page (navigation.md §6, auth-and-access.md J3):
    same status code, copy and timing whether a route doesn't exist or the viewer just isn't
    allowed to see it, so a project's existence is never leaked (§68).

    Visual QA C1: a signed-in person never drops out of the shell (nav stays, and — while
    impersonating — so does the banner), so this renders `not_found.html` with `base.html`'s
    nav/banner for anyone with a session, and only falls back to the no-nav `base_public.html`
    for a genuinely anonymous visitor."""
    actor = getattr(request, "actor", None)
    signed_in = bool(actor and actor.is_authenticated)
    return render(request, "web/not_found.html", {"signed_in": signed_in}, status=404)


def server_error(request):
    """Generic 500 (foundation.md §10). Same C1 treatment as `not_found`: a signed-in person
    keeps the shell (nav, impersonation banner) instead of dropping to the no-nav public
    layout."""
    actor = getattr(request, "actor", None)
    signed_in = bool(actor and actor.is_authenticated)
    return render(request, "web/server_error.html", {"signed_in": signed_in}, status=500)
