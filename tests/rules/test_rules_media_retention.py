"""media_retention_period: §47 clocks for Completed/Rejected, Q-128 for Cancelled."""

import dataclasses
from datetime import timedelta

import pytest

from ham.rules import RULES, media_retention_period


@pytest.mark.parametrize(
    ("kind", "status", "expected"),
    [
        ("photo", "COMPLETED", timedelta(days=90)),
        ("photo", "REJECTED", timedelta(days=90)),
        ("photo", "CANCELLED", timedelta(days=90)),  # Q-128
        ("video", "COMPLETED", timedelta(days=30)),
        ("video", "REJECTED", timedelta(days=30)),
        ("video", "CANCELLED", timedelta(days=30)),  # Q-128
    ],
)
def test_periods(kind: str, status: str, expected: timedelta) -> None:
    assert media_retention_period(kind, status) == expected


@pytest.mark.parametrize("status", ["NOT_EXECUTABLE", "AWAITING_APPROVAL", "completed", ""])
def test_status_without_a_rule_is_refused_not_guessed(status: str) -> None:
    with pytest.raises(ValueError, match="no media retention rule"):
        media_retention_period("photo", status)


@pytest.mark.parametrize("kind", ["document", "PHOTO", ""])
def test_unknown_kind(kind: str) -> None:
    with pytest.raises(ValueError, match="unknown media kind"):
        media_retention_period(kind, "COMPLETED")


def test_cancellation_clock_can_be_switched_off_by_a_rules_version() -> None:
    media = dataclasses.replace(RULES.media, MEDIA_RETENTION_CLOCK_ON_CANCELLATION=False)
    rules = dataclasses.replace(RULES, media=media)
    assert media_retention_period("photo", "CANCELLED", rules) is None
    assert media_retention_period("photo", "COMPLETED", rules) == timedelta(days=90)
