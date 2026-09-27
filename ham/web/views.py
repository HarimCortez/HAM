"""GET /healthz — public (foundation.md §7 route table). Checks the database and the job
queue for a stalled worker. Never returns anything beyond booleans/numbers (PRD §68: no PII
in a public endpoint's response)."""

from __future__ import annotations

import time

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from ham.jobs import queue_lag_seconds

# Generous margin before a delayed job is treated as "the worker is stuck", not just busy.
MAX_HEALTHY_QUEUE_LAG_SECONDS = 300


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
        if lag is not None and lag > MAX_HEALTHY_QUEUE_LAG_SECONDS:
            healthy = False
    except Exception:
        checks["job_queue"] = "error"
        healthy = False

    status = "ok" if healthy else "degraded"
    return JsonResponse({"status": status, "checks": checks}, status=200 if healthy else 503)
