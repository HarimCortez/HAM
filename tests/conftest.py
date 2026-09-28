from __future__ import annotations

import pytest

from ham.platform.clock import SystemClock, set_clock


@pytest.fixture(autouse=True)
def _reset_clock():
    """Every test starts and ends with the real clock, even if it calls set_clock()."""
    set_clock(SystemClock())
    yield
    set_clock(SystemClock())


@pytest.fixture
def make_user(db):
    """Shared across tests/identity, tests/authz, tests/audit: a plain, no-password User."""
    from ham.identity.models import User

    def _make(email: str) -> User:
        return User.objects.create_user(email=email)

    return _make
