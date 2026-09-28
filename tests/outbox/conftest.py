from __future__ import annotations

import pytest

from ham.outbox import registry


@pytest.fixture
def fake_subscriber():
    """Register a fake subscriber under a name that never collides with a real one
    (`ham.integrations`'s `email`/`calendar`/`fitness`/`drive`/`dev_logging`), and unregister
    it afterwards so it never leaks into another test."""
    registered: list[str] = []

    def _register(name: str, handler):
        registry.register(name, handler)
        registered.append(name)

    yield _register

    for name in registered:
        registry.unregister(name)
