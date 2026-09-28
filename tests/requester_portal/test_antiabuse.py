from __future__ import annotations

import datetime as dt

from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal.antiabuse import (
    honeypot_tripped,
    min_fill_time_ok,
    sign_form_opened_at,
)
from ham.rules import RULES

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


def test_honeypot():
    assert not honeypot_tripped("")
    assert not honeypot_tripped(None)
    assert honeypot_tripped("http://spam.example")


def test_min_fill_time_boundary():
    clock = FixedClock(T0)
    set_clock(clock)
    try:
        token = sign_form_opened_at()
        assert not min_fill_time_ok(token, now=T0)
        assert not min_fill_time_ok(
            token, now=T0 + RULES.intake.INTAKE_MIN_FILL_TIME - dt.timedelta(seconds=1)
        )
        assert min_fill_time_ok(token, now=T0 + RULES.intake.INTAKE_MIN_FILL_TIME)
    finally:
        set_clock(FixedClock(T0))  # restored again by the autouse fixture too


def test_min_fill_time_rejects_tampering():
    token = sign_form_opened_at(now=T0)
    ts_text, _, _sig = token.partition("|")
    forged = f"{ts_text}|deadbeef"
    assert not min_fill_time_ok(forged, now=T0 + dt.timedelta(minutes=5))


def test_min_fill_time_rejects_missing_or_malformed():
    assert not min_fill_time_ok(None)
    assert not min_fill_time_ok("")
    assert not min_fill_time_ok("not-a-token")
