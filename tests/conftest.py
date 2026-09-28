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


@pytest.fixture
def make_user(db):
    """Shared across tests/identity, tests/authz, tests/audit: a plain, no-password User."""
    from ham.identity.models import User

    def _make(email: str) -> User:
        return User.objects.create_user(email=email)

    return _make
