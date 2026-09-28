"""Requester link validity (PRD §7.3; Q-116, Q-117, Q-025). Pure, boundary times.

Expected durations are typed here (7 days, 14 days), not read from the rules module, so a
rules change that breaks §7.3 fails these tests.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from ham.requester_portal.validity import (
    LinkKind,
    LinkState,
    LinkValidity,
    fixed_expiry,
    link_validity,
    may_self_regenerate,
    normal_access_ends_at,
)
from ham.rules import RULES, Rules

T0 = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)  # the request closes / completes here
SEC = timedelta(seconds=1)
DAY = timedelta(days=1)
END = T0 + 7 * DAY  # normal access ends (7 days after close or completion)


def _v(
    *,
    kind: str = "initial",
    issued_at: datetime = T0 - 30 * DAY,
    revoked_at: datetime | None = None,
    status: str = "CANCELLED",
    closed_at: datetime | None = T0,
    completed_at: datetime | None = None,
    now: datetime,
    rules: Rules = RULES,
) -> LinkValidity:
    return link_validity(
        kind=kind,
        issued_at=issued_at,
        revoked_at=revoked_at,
        status=status,
        closed_at=closed_at,
        completed_at=completed_at,
        now=now,
        rules=rules,
    )


# --- initial link ----------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["SUBMITTED", "AWAITING_APPROVAL", "APPROVED"])
def test_open_request_link_never_expires_by_time(status: str) -> None:
    far = T0 + 3650 * DAY
    v = _v(status=status, closed_at=None, now=far)
    assert v == LinkValidity(LinkState.VALID, None)


@pytest.mark.parametrize(
    ("now", "state"),
    [
        (T0, LinkState.VALID),
        (END - DAY, LinkState.VALID),  # 6 days after close
        (END - timedelta(hours=1), LinkState.VALID),  # 6 days 23 hours
        (END - SEC, LinkState.VALID),
        (END, LinkState.EXPIRED),  # exactly 7 days
        (END + SEC, LinkState.EXPIRED),
    ],
)
def test_initial_link_after_cancellation(now: datetime, state: LinkState) -> None:
    """Q-116: 7 days after a close without completion."""
    v = _v(status="CANCELLED", now=now)
    assert v.state is state
    assert v.valid_until == END


@pytest.mark.parametrize(
    ("now", "state"),
    [
        (END - SEC, LinkState.VALID),
        (END, LinkState.EXPIRED),
    ],
)
def test_initial_link_after_completion(now: datetime, state: LinkState) -> None:
    """§7.3: 7 days after project completion."""
    v = _v(status="COMPLETED", closed_at=None, completed_at=T0, now=now)
    assert v.state is state
    assert v.valid_until == END


def test_completion_takes_precedence_over_close() -> None:
    v = _v(status="COMPLETED", closed_at=T0 + DAY, completed_at=T0, now=T0)
    assert v.valid_until == END


def test_final_rejection_and_not_executable_close_like_cancellation() -> None:
    for status in ("REJECTED", "NOT_EXECUTABLE"):
        assert _v(status=status, now=END - SEC).state is LinkState.VALID
        assert _v(status=status, now=END).state is LinkState.EXPIRED


def test_reconsiderable_rejection_is_still_open() -> None:
    v = _v(status="REJECTED", closed_at=None, now=T0 + 365 * DAY)
    assert v == LinkValidity(LinkState.VALID, None)


# --- regenerated link ------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("issued_at", "now", "state", "valid_until"),
    [
        # issued after normal access ended: 14 days from issue (§7.3)
        (END + DAY, END + DAY, LinkState.VALID, END + 15 * DAY),
        (END + DAY, END + 15 * DAY - SEC, LinkState.VALID, END + 15 * DAY),
        (END + DAY, END + 15 * DAY, LinkState.EXPIRED, END + 15 * DAY),
        (END + DAY, END + 14 * DAY, LinkState.VALID, END + 15 * DAY),  # 13 days old
        # issued at exactly the end: counts as after (normal access is over at END)
        (END, END + 14 * DAY - SEC, LinkState.VALID, END + 14 * DAY),
        (END, END + 14 * DAY, LinkState.EXPIRED, END + 14 * DAY),
        # issued one second before the end: follows normal access (Q-117)
        (END - SEC, END - SEC, LinkState.VALID, END),
        (END - SEC, END, LinkState.EXPIRED, END),
    ],
)
def test_regenerated_link_boundaries(
    issued_at: datetime, now: datetime, state: LinkState, valid_until: datetime
) -> None:
    v = _v(kind="regenerated", issued_at=issued_at, now=now)
    assert v.state is state
    assert v.valid_until == valid_until


def test_regenerated_while_open_follows_normal_access_then_close() -> None:
    """Q-117: a lost link replaced before the end lasts as long as the normal link would,
    including after the request later closes."""
    issued = T0 - 10 * DAY
    open_v = _v(kind="regenerated", issued_at=issued, status="AWAITING_APPROVAL",
                closed_at=None, now=T0 + 100 * DAY)  # fmt: skip
    assert open_v == LinkValidity(LinkState.VALID, None)
    closed_v = _v(kind="regenerated", issued_at=issued, now=END)
    assert closed_v.state is LinkState.EXPIRED
    assert closed_v.valid_until == END


def test_q117_alternative_always_14_days() -> None:
    ra = dataclasses.replace(
        RULES.requester_access, EARLY_REGENERATED_LINK_FOLLOWS_NORMAL_ACCESS=False
    )
    rules = dataclasses.replace(RULES, requester_access=ra)
    issued = T0 - 10 * DAY
    v = _v(kind="regenerated", issued_at=issued, status="AWAITING_APPROVAL", closed_at=None,
           now=issued + 14 * DAY - SEC, rules=rules)  # fmt: skip
    assert v.state is LinkState.VALID
    v = _v(kind="regenerated", issued_at=issued, status="AWAITING_APPROVAL", closed_at=None,
           now=issued + 14 * DAY, rules=rules)  # fmt: skip
    assert v.state is LinkState.EXPIRED
    # the initial link is unaffected by the Q-117 switch
    assert _v(status="AWAITING_APPROVAL", closed_at=None, now=T0, rules=rules).is_valid


def test_fixed_expiry_for_storage() -> None:
    assert fixed_expiry(kind="initial", issued_at=END + DAY, access_ends_at=END) is None
    assert fixed_expiry(kind=LinkKind.REGENERATED, issued_at=END, access_ends_at=END) == (
        END + 14 * DAY
    )
    assert fixed_expiry(kind="regenerated", issued_at=END - SEC, access_ends_at=END) is None
    assert fixed_expiry(kind="regenerated", issued_at=T0, access_ends_at=None) is None


# --- revocation ------------------------------------------------------------------------------
def test_revoked_link_is_dead_whatever_the_time() -> None:
    for now in (T0 - DAY, T0, END - SEC):
        v = _v(revoked_at=T0 - 2 * DAY, now=now)
        assert v.state is LinkState.REVOKED
        assert not v.is_valid


def test_revoked_wins_over_expired() -> None:
    assert _v(revoked_at=T0, now=END + DAY).state is LinkState.REVOKED


# --- Q-025 phone-check requests --------------------------------------------------------------
def test_phone_check_requests_have_no_link_access() -> None:
    v = _v(status="NEEDS_PHONE_CHECK", closed_at=None, now=T0)
    assert v == LinkValidity(LinkState.NO_ACCESS, None)
    assert not may_self_regenerate("NEEDS_PHONE_CHECK")
    for status in ("AWAITING_APPROVAL", "CANCELLED", "COMPLETED"):
        assert may_self_regenerate(status)


# --- consistency and time zones --------------------------------------------------------------
@pytest.mark.parametrize(
    ("status", "closed_at", "completed_at"),
    [
        ("CANCELLED", None, None),  # a cancelled request must carry its close time
        ("AWAITING_APPROVAL", T0, None),
        ("SUBMITTED", None, T0),
        ("RECONSIDERATION_PENDING", T0, None),
    ],
)
def test_inconsistent_facts_raise(
    status: str, closed_at: datetime | None, completed_at: datetime | None
) -> None:
    with pytest.raises(ValueError):
        normal_access_ends_at(status=status, closed_at=closed_at, completed_at=completed_at)


def test_naive_datetimes_are_refused() -> None:
    naive = datetime(2026, 10, 1, 15, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        _v(now=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        _v(closed_at=naive, now=T0)
    with pytest.raises(ValueError, match="timezone-aware"):
        _v(issued_at=naive, now=T0)


def test_other_time_zones_compare_as_instants() -> None:
    from zoneinfo import ZoneInfo

    ny_end = END.astimezone(ZoneInfo("America/New_York"))
    assert _v(now=ny_end - SEC).is_valid
    assert _v(now=ny_end).state is LinkState.EXPIRED


def test_access_end_helper() -> None:
    assert normal_access_ends_at(status="AWAITING_APPROVAL", closed_at=None) is None
    assert normal_access_ends_at(status="CANCELLED", closed_at=T0) == END
    assert normal_access_ends_at(status="COMPLETED", closed_at=None, completed_at=T0) == END
