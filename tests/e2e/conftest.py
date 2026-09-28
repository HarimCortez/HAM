"""Shared fixtures for every test under `tests/e2e/` (Playwright + `live_server`)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _sweep_leaked_procrastinate_todo_jobs(request):
    """`live_server` tests marked `django_db(transaction=True)` commit real rows with no
    per-test rollback. A test that drives an effect directly (e.g. calling
    `complete_intake_checks`/`verify_by_phone` itself) rather than letting the request that
    deferred a Procrastinate job run to completion via `run_due_jobs_now()` leaves that job
    sitting in status='todo' in the shared `procrastinate_jobs` table. A *later*, unrelated
    test that calls `run_due_jobs_now()` then picks it up and fails nondeterministically
    (states.py's `WRONG_STATE`, depending on file/test order) trying to execute a job whose
    target has already moved on.

    One shared teardown for every test in this directory replaces the per-file raw
    `DELETE FROM procrastinate_jobs WHERE status = 'todo'` that `test_step2_leadership.py`
    and `test_step2_leadership_screenshots.py` used to each copy by hand (and that a new e2e
    test file could easily forget to copy). A raw sweep, not `run_due_jobs_now()` (which
    would try to *execute* stale jobs, including any left over from an earlier interrupted
    run, rather than just discard them).

    Only runs for tests that actually touched the DB (`django_db` marker present) --
    `tests/e2e/test_shell_screenshots.py` et al. mark individual test *functions*, not the
    whole module, with `@pytest.mark.django_db(transaction=True)`, and pytest-django refuses
    any DB access from a test that isn't marked.
    """
    yield
    if request.node.get_closest_marker("django_db") is None:
        return

    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM procrastinate_jobs WHERE status = 'todo'")
