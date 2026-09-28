from __future__ import annotations

import datetime as dt

import pytest

from ham.platform.clock import FixedClock, SystemClock, get_clock, now, set_clock


def test_system_clock_is_utc_and_aware():
    clock = SystemClock()
    when = clock.now()
    assert when.tzinfo is not None
    assert when.utcoffset() == dt.timedelta(0)


def test_now_uses_the_injected_clock():
    fixed = FixedClock(dt.datetime(2027, 1, 1, tzinfo=dt.UTC))
    set_clock(fixed)
    assert now() == dt.datetime(2027, 1, 1, tzinfo=dt.UTC)
    assert get_clock() is fixed


def test_fixed_clock_advance_and_set():
    fixed = FixedClock(dt.datetime(2027, 1, 1, tzinfo=dt.UTC))
    fixed.advance(dt.timedelta(hours=48))
    assert fixed.now() == dt.datetime(2027, 1, 3, tzinfo=dt.UTC)
    fixed.set(dt.datetime(2027, 6, 1, tzinfo=dt.UTC))
    assert fixed.now() == dt.datetime(2027, 6, 1, tzinfo=dt.UTC)


def test_fixed_clock_rejects_naive_datetime():
    with pytest.raises(ValueError):
        FixedClock(dt.datetime(2027, 1, 1))


def test_fixed_clock_converts_non_utc_to_utc():
    tz = dt.timezone(dt.timedelta(hours=-5))
    fixed = FixedClock(dt.datetime(2027, 1, 1, 12, tzinfo=tz))
    assert fixed.now() == dt.datetime(2027, 1, 1, 17, tzinfo=dt.UTC)
