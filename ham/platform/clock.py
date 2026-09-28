"""Injectable UTC clock so rules like "48 hours before" and "day before" (§70.5, Q-023) are
testable without patching `datetime` globally.

Domain code must call `ham.platform.clock.now()`, never `datetime.now()` / `datetime.utcnow()`
directly, so tests can time-travel deterministically (foundation.md §1 "Clock (injectable UTC
now)"; test plan hook "time-machine via the Clock" in docs/architecture/foundation.md §9).
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol


class Clock(Protocol):
    def now(self) -> dt.datetime: ...


class SystemClock:
    """The real clock. Always returns a timezone-aware UTC instant."""

    def now(self) -> dt.datetime:
        return dt.datetime.now(dt.UTC)


class FixedClock:
    """A test clock that stands still until explicitly advanced.

    Use via `set_clock(FixedClock(...))` in a test, and `set_clock(SystemClock())` (or the
    `clock` fixture in tests/conftest.py) to restore it afterwards.
    """

    def __init__(self, when: dt.datetime):
        if when.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime (use UTC).")
        self._when = when.astimezone(dt.UTC)

    def now(self) -> dt.datetime:
        return self._when

    def advance(self, delta: dt.timedelta) -> None:
        self._when += delta

    def set(self, when: dt.datetime) -> None:
        if when.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime (use UTC).")
        self._when = when.astimezone(dt.UTC)


_current: Clock = SystemClock()


def get_clock() -> Clock:
    return _current


def set_clock(clock: Clock) -> None:
    """Test-only hook. Production code never calls this."""
    global _current
    _current = clock


def now() -> dt.datetime:
    """The one function domain code calls for "now". Always UTC, always aware (§70.5)."""
    return get_clock().now()
