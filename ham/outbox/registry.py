"""The subscriber registry: subscriber name -> handler(event) -> None.

Subscribers register from their own app's `AppConfig.ready()` (Django guarantees every app's
`ready()` runs once, at startup, before any request or job is handled) — never at plain
module import time, since import order between apps is not guaranteed.

This module has no knowledge of what a subscriber *is* (email, calendar, a future SMS
provider, a test fake); it only holds callables. That keeps `ham.outbox` independent of
`ham.integrations` (foundation.md §1: outbox sits below web; integrations is a leaf that
plugs in here, never the reverse).
"""

from __future__ import annotations

from collections.abc import Callable

from .models import OutboxEvent

Handler = Callable[[OutboxEvent], None]

_handlers: dict[str, Handler] = {}


def register(subscriber: str, handler: Handler) -> None:
    """Register (or replace) the handler for `subscriber`. Idempotent by design so an
    app's `ready()` can safely run more than once (e.g. under the test runner)."""
    _handlers[subscriber] = handler


def get_handler(subscriber: str) -> Handler:
    """Raises `KeyError` if nothing is registered under `subscriber`."""
    return _handlers[subscriber]


def subscribers() -> tuple[str, ...]:
    """Every currently-registered subscriber name, in registration order."""
    return tuple(_handlers.keys())


def is_registered(subscriber: str) -> bool:
    return subscriber in _handlers


def unregister(subscriber: str) -> None:
    """Test-only: undo a single `register()` call. Prefer this over `reset()` in tests, so a
    test-added fake subscriber doesn't disable the real ones registered by
    `IntegrationsConfig.ready()` for the rest of the test session."""
    _handlers.pop(subscriber, None)


def reset() -> None:
    """Test-only: clear every registration."""
    _handlers.clear()
