"""Pending placeholders refuse use; CalendarYears never under-retains; cancellation bands."""

import unittest
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ham.rules import (
    RULES,
    CalendarYears,
    Pending,
    RuleNotDecidedError,
    cancellation_band,
    check_reliability_penalties,
)


class PendingRefusesUseTest(unittest.TestCase):
    P = Pending("Q-001", "3 points")

    def test_every_kind_of_use_raises(self) -> None:
        p = self.P
        uses: dict[str, Callable[[], object]] = {
            "bool": lambda: bool(p),
            "if": lambda: 1 if p else 0,
            "int": lambda: int(p),
            "float": lambda: float(p),
            "index": lambda: [0, 1][p],  # type: ignore[index]
            "round": lambda: round(p),  # type: ignore[call-overload]
            "neg": lambda: -p,  # type: ignore[operator]
            "add": lambda: p + 1,  # type: ignore[operator]
            "radd": lambda: 100 + p,  # type: ignore[operator]
            "rsub score": lambda: 100 - p,  # type: ignore[operator]
            "timedelta + p": lambda: timedelta(hours=1) + p,  # type: ignore[operator]
            "datetime - p": lambda: datetime.now(UTC) - p,  # type: ignore[operator]
            "mul": lambda: p * 2,  # type: ignore[operator]
            "min": lambda: min(p, 5),  # type: ignore[type-var]
            "max": lambda: max(0, p),  # type: ignore[type-var]
            "lt": lambda: p < 5,  # type: ignore[operator]
            "gt reflected": lambda: 5 > p,  # type: ignore[operator]
            "eq int": lambda: p == 5,
            "eq reflected": lambda: 5 == p,
            "eq timedelta": lambda: timedelta(1) == p,
            "ne": lambda: p != 5,
            "iter": lambda: list(p),  # type: ignore[call-overload]
            "len": lambda: len(p),  # type: ignore[arg-type]
            "in": lambda: 1 in p,  # type: ignore[operator]
            "range": lambda: range(p),  # type: ignore[call-overload]
        }
        for name, use in uses.items():
            with self.subTest(use=name):
                with self.assertRaises(RuleNotDecidedError) as ctx:
                    use()
                self.assertIn("Q-001", str(ctx.exception))

    def test_real_undecided_rules_raise_when_used(self) -> None:
        with self.assertRaises(RuleNotDecidedError):
            _ = 100 - RULES.reliability.PENALTY_NO_SHOW  # type: ignore[operator]
        with self.assertRaises(RuleNotDecidedError):
            _ = RULES.reporting.PUBLIC_EMBED_MIN_GROUP_SIZE > 3  # type: ignore[operator]
        with self.assertRaises(RuleNotDecidedError):
            _ = datetime.now(UTC) + RULES.auth.ACCOUNT_INVITATION_LIFETIME  # type: ignore[operator]

    def test_display_and_hash_are_allowed(self) -> None:
        self.assertEqual(repr(self.P), "Pending('Q-001')")
        self.assertIn("Q-001", str(self.P))
        self.assertIn("Q-001", f"{self.P}")
        self.assertEqual(hash(self.P), hash(Pending("Q-001", "other text")))
        self.assertEqual(self.P, Pending("Q-001", "other text"))
        self.assertNotEqual(self.P, Pending("Q-027", ""))

    def test_identity_comparisons_are_safe(self) -> None:
        self.assertIs(self.P, self.P)
        self.assertIsNotNone(self.P)
        self.assertIn(self.P, [self.P])  # identity shortcut in list containment


class CalendarYearsTest(unittest.TestCase):
    def test_after(self) -> None:
        cases = [
            # (years, start, expected)
            (1, date(2026, 9, 27), date(2027, 9, 27)),
            (7, date(2026, 1, 1), date(2033, 1, 1)),
            (1, date(2024, 2, 29), date(2025, 3, 1)),  # leap day rounds UP, never early
            (4, date(2024, 2, 29), date(2028, 2, 29)),  # leap to leap stays
            (7, date(2020, 2, 29), date(2027, 3, 1)),
            (1, date(2023, 3, 1), date(2024, 3, 1)),
            (0, date(2026, 5, 5), date(2026, 5, 5)),
        ]
        for years, start, expected in cases:
            with self.subTest(years=years, start=start):
                self.assertEqual(CalendarYears(years).after(start), expected)

    def test_after_keeps_time_and_utc(self) -> None:
        start = datetime(2024, 2, 29, 23, 30, tzinfo=UTC)
        self.assertEqual(CalendarYears(1).after(start), datetime(2025, 3, 1, 23, 30, tzinfo=UTC))

    def test_seven_calendar_years_is_never_shorter_than_elapsed_days_it_spans(self) -> None:
        start = date(2020, 2, 29)
        end = CalendarYears(7).after(start)
        self.assertGreaterEqual((end - start).days, 7 * 365 + 1)  # 2 leap days in span

    def test_invalid(self) -> None:
        for bad in (-1, True, 1.5, "7"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    CalendarYears(bad)  # type: ignore[arg-type]


class CancellationBandTest(unittest.TestCase):
    def test_band_boundaries(self) -> None:
        cases = [
            (30, "free"),
            (8, "free"),
            (7, "free"),  # exactly 7 days: no penalty (§33 "at least seven days")
            (6, "days_4_to_6"),
            (4, "days_4_to_6"),
            (3, "days_2_to_3"),
            (2, "days_2_to_3"),
            (1, "day_1"),
            (0, "same_day"),
        ]
        for days, band in cases:
            with self.subTest(days_before=days):
                self.assertEqual(cancellation_band(days), band)

    def test_after_the_project_day_is_not_a_cancellation(self) -> None:
        with self.assertRaises(ValueError):
            cancellation_band(-1)

    def test_rejects_non_ints(self) -> None:
        for bad in (6.9, True, "7", None):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    cancellation_band(bad)  # type: ignore[arg-type]


class ReliabilityProposalCheckTest(unittest.TestCase):
    BASE: dict[str, Any] = dict(
        days_4_to_6=3, days_2_to_3=6, day_1=10, same_day=16, no_show=20, recovery=2
    )

    def test_proposal_for_q001_satisfies_prd_ordering(self) -> None:
        self.assertEqual(check_reliability_penalties(**self.BASE), ())

    def test_violations(self) -> None:
        cases: list[tuple[dict[str, Any], str]] = [
            ({"same_day": 20}, "same day (20) must be less than no-show"),
            ({"same_day": 25}, "same day (25) must be less than no-show"),
            ({"days_2_to_3": 3}, "4-6 days (3) must be less than 2-3 days"),
            ({"days_4_to_6": 0}, "between 1 and 100"),
            ({"no_show": 101}, "between 1 and 100"),
            ({"recovery": 0}, "recovery must be a positive int"),
            ({"recovery": 20}, "gradual"),
            ({"day_1": True}, "must be an int"),
        ]
        for change, fragment in cases:
            with self.subTest(change=change):
                problems = check_reliability_penalties(**{**self.BASE, **change})
                self.assertTrue(any(fragment in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
