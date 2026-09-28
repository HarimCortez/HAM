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
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

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
    context: dict[str, object] = {}
    if authorize(ctx, "integrations.view_status").allowed:
        from ham.outbox.services import subscriber_status_counts

        from .views_admin_settings import _VISIBLE_SUBSCRIBERS

        context["integration_counts"] = [
            row for row in subscriber_status_counts() if row.subscriber in _VISIBLE_SUBSCRIBERS
        ]
        context["recent_sign_in_failures"] = _recent_sign_in_failures(ctx)
    if authorize(ctx, "user.invite").allowed and not authorize(ctx, "user.list").allowed:
        context["show_invite_card"] = True
    return render(request, "web/home.html", context)


def _recent_sign_in_failures(ctx) -> dict[str, object]:
    """Counts/times only (§68: never names or emails) of recent lockouts, for the
    Administrator Home summary (foundation.md §10). Goes through `ham.authz.audit_access`
    (never `ham.audit.queries` directly, repo convention) even though the caller has already
    checked `integrations.view_status`, so this stays authorized the same way the audit log
    itself is."""
    import datetime as dt

    from ham.audit.queries import AuditFilter
    from ham.authz.audit_access import list_events
    from ham.platform.clock import now as clock_now

    since = clock_now() - dt.timedelta(hours=24)
    events = list_events(ctx, AuditFilter(action="auth.sign_in.locked", date_from=since), limit=200)
    return {
        "count": len(events),
        "latest_at": events[0].occurred_at if events else None,
    }


@require_GET
@requires_action("shell.use")
def inbox(request):
    """Inbox placeholder (foundation.md §10; navigation.md §4)."""
    return render(request, "web/inbox.html")


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


@require_GET
def not_found(request, exception=None):
    """The neutral 'no permission / not found' page (navigation.md §6, auth-and-access.md J3):
    same status code, copy and timing whether a route doesn't exist or the viewer just isn't
    allowed to see it, so a project's existence is never leaked (§68)."""
    return render(request, "web/not_found.html", status=404)


def server_error(request):
    """Generic 500 (foundation.md §10)."""
    return render(request, "web/server_error.html", status=500)
