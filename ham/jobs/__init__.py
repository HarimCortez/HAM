"""`ham.jobs` — the only module domain code imports to define and enqueue background jobs.

Wraps Procrastinate (docs/adr/0001-stack.md Option B): reminders, retention, waitlists and
calendar sync all go through here (PRD §78), never through `procrastinate` directly, so the
job backend can change later without touching callers (CLAUDE.md engineering defaults).

Usage:
    from ham import jobs

    @jobs.job(name="notifications.send_reminder")
    def send_reminder(user_id: str) -> None: ...

    jobs.defer("notifications.send_reminder", user_id=str(user.id))

Run the worker with `python manage.py procrastinate worker` (registered by
`procrastinate.contrib.django`, in INSTALLED_APPS).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from procrastinate.contrib.django import app as _app

app = _app


def job(*, name: str, **task_options: Any) -> Callable:
    """Decorator registering a background job under a stable, versioned name.

    Name jobs `<domain>.<verb>` (e.g. `staffing.release_unconfirmed`) so the outbox/dispatcher
    and this module's own tests can refer to them without importing the domain module.
    """
    return _app.task(name=name, **task_options)


def defer(job_name: str, /, **kwargs: Any) -> None:
    """Enqueue a previously-registered job by name, in the same Postgres transaction if
    called inside one (Procrastinate uses the Django connection)."""
    _app.tasks[job_name].defer(**kwargs)


def defer_later(job_name: str, /, *, schedule_at, **kwargs: Any) -> None:
    """Enqueue a job to run no earlier than `schedule_at` (a timezone-aware UTC datetime)."""
    _app.tasks[job_name].configure(schedule_at=schedule_at).defer(**kwargs)


def queue_lag_seconds() -> float | None:
    """Seconds since the oldest still-due job was supposed to run, or None if nothing is due.

    Used by the health check (`GET /healthz`, PRD §70.2) to detect a stalled worker without
    any other module needing to know Procrastinate's table layout.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXTRACT(EPOCH FROM (now() - scheduled_at)) "
            "FROM procrastinate_jobs "
            "WHERE status = 'todo' AND scheduled_at <= now() "
            "ORDER BY scheduled_at ASC LIMIT 1"
        )
        row = cursor.fetchone()
    return float(row[0]) if row else None
