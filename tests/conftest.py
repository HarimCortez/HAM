from __future__ import annotations

import pytest

from ham.platform.clock import SystemClock, set_clock


@pytest.fixture(autouse=True)
def _reset_clock():
    """Every test starts and ends with the real clock, even if it calls set_clock()."""
    set_clock(SystemClock())
    yield
    set_clock(SystemClock())
