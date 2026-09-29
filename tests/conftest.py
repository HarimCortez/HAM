from __future__ import annotations

import pytest

from ham.platform.clock import SystemClock, set_clock


@pytest.fixture(autouse=True)
def _reset_clock():
    """Every test starts and ends with the real clock, even if it calls set_clock()."""
    set_clock(SystemClock())
    yield
    set_clock(SystemClock())


@pytest.fixture(scope="session", autouse=True)
def _terminate_stray_backends_before_db_teardown(request, django_db_setup, django_db_blocker):
    """The one outstanding pytest warning (step-2 handoff): `tests/e2e/test_smoke.py`'s
    `live_server` (pytest-django, session-scoped) runs a real threaded WSGI server that
    Playwright talks to over real HTTP/1.1 (keep-alive) connections. Each of those handler
    threads opens its own Postgres backend session; Django closes it once that connection's
    socket is recognised as finished, but nothing guarantees that has happened for every such
    thread by the time pytest-django's own session-scoped `django_db_setup` fixture tears
    down and runs `DROP DATABASE`, which then intermittently fails with "database ... is
    being accessed by other users" (a `PytestWarning`, not a test failure -- but worth
    removing, not just tolerating).

    Requesting `django_db_setup` here (rather than reaching for `django.db.connection`
    directly) makes this fixture set up *after* it, so — pytest tears fixtures down in
    reverse setup order — this one's own teardown runs first, right before `django_db_setup`
    attempts the `DROP DATABASE`: forcing every *other* backend session still open on the
    test database closed, unconditionally, regardless of which test (if any) left one
    behind. A no-op on a clean run (the query matches nothing)."""
    yield
    with django_db_blocker.unblock():
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
        connection.close()


@pytest.fixture(autouse=True)
def _sweep_leaked_procrastinate_todo_jobs(request):
    """Order-dependence fix (test-engineer pass, step 3), generalizing `tests/e2e/conftest.py`'s
    identically-named, `tests/e2e/`-only fixture to every test in the suite: a
    `django_db(transaction=True)` test commits real rows with no per-test rollback, and
    Procrastinate's own `procrastinate_jobs` table survives pytest-django's usual
    truncate-between-tests flush (it isn't reset the way an ordinary app table is) -- so a
    job left in `status='todo'` (e.g. an outbox dispatch deferred by a real `transaction.
    on_commit` that the test itself never drained with `run_due_jobs_now()`) leaks into
    whichever *later* test, in the same file or a different one entirely, happens to call
    `run_due_jobs_now()` next. That test then either double-executes a stale effect (e.g.
    `tests/web/test_fix_f2_minors.py`'s repeated `outbox.dispatch_delivery: delivery not
    found` warnings leaking into `tests/web/test_fix_f2_already_received.py`'s mailbox count,
    confirmed by running the suite in reverse file order) or fails outright trying to act on
    a target that has already moved on (`states.py`'s `WRONG_STATE`). A raw sweep, not
    `run_due_jobs_now()` (which would try to *execute* stale jobs, including any genuinely
    left over from an earlier interrupted run, rather than just discard them).

    Only runs for tests that actually touched the DB (`django_db` marker present) -- several
    files mark individual test *functions*, not the whole module, and pytest-django refuses
    DB access from an unmarked test."""
    yield
    if request.node.get_closest_marker("django_db") is None:
        return

    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM procrastinate_jobs WHERE status = 'todo'")


@pytest.fixture
def make_user(db):
    """Shared across tests/identity, tests/authz, tests/audit: a plain, no-password User."""
    from ham.identity.models import User

    def _make(email: str) -> User:
        return User.objects.create_user(email=email)

    return _make


@pytest.fixture
def real_portal_lookups(db):
    """Registers `ham.requester_portal.services`'s three lookup globals with the exact same
    production callables `ham.requester_portal.apps.RequesterPortalConfig.ready()` registers
    at process startup (duplicated here on purpose rather than calling `ready()` again, which
    would also re-register the periodic purge jobs), for tests that exercise the real
    `ham.requests.queries` wiring rather than a hand-built fake.

    Several files (`tests/requester_portal/test_submission_flow.py`,
    `tests/requester_portal/test_notifications.py`, `tests/web/test_requester_portal_screens.py`)
    used to each copy this registration as a local `autouse` fixture whose teardown reset the
    globals to `None` -- fine as long as that was the *last* portal test to run in the
    process, but a later test file relying on the app-startup registration still being intact
    (without re-registering it itself) would then hit `RuntimeError` depending on test order.
    This shared fixture instead re-registers the same real callables on teardown, so the
    globals are always left in a valid (real, non-`None`) state no matter what ran before or
    after. Request this fixture explicitly (it is not autouse at this shared level, since most
    tests don't touch the requester portal at all) -- e.g.
    `@pytest.fixture(autouse=True) def _use(self, real_portal_lookups): pass` in a module that
    wants every test in it covered.
    """
    import uuid

    from ham.requester_portal import services
    from ham.requests import queries as requests_queries

    def _facts_lookup(request_id: uuid.UUID) -> services.RequestLinkFacts:
        facts = requests_queries.request_facts_for_portal(request_id)
        return services.RequestLinkFacts(
            status=facts.status,
            closed_at=facts.closed_at,
            display_number=facts.display_number,
        )

    def _register() -> None:
        services.register_request_facts_lookup(_facts_lookup)
        services.register_request_contact_lookup(requests_queries.request_contact_for_portal)
        services.register_email_to_request_ids_lookup(requests_queries.request_ids_for_portal_email)

    _register()
    yield
    _register()
