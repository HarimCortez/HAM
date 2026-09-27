"""Structure of the rules module: sources on every value, immutability, and purity."""

import ast
import dataclasses
import re
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

from ham.rules import RULES, Pending, check_invariants
from ham.rules.types import contains_pending, pending_questions
from ham.rules.v1 import iter_rules

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = REPO_ROOT / "ham" / "rules"


def _imported_modules(path: Path) -> list[str]:
    """Modules imported by a file (relative imports start with '.')."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.append("." * node.level + (node.module or ""))
    return mods


SOURCE_RE = re.compile(r"^(PRD §\d+(\.\d+)?|Q-\d{3}|foundation\.md §\d+)$")


class SourcesAndLabelsTest(unittest.TestCase):
    def test_every_rule_has_a_label_and_well_formed_sources(self) -> None:
        for gf, rf, _value in iter_rules(RULES):
            with self.subTest(rule=f"{gf.name}.{rf.name}"):
                meta = rf.metadata
                self.assertTrue(meta["label"].strip())
                self.assertIsInstance(meta["sources"], tuple)
                self.assertTrue(meta["sources"], "every value needs a PRD § or Q-id")
                for src in meta["sources"]:
                    self.assertRegex(src, SOURCE_RE)

    def test_every_group_has_a_label(self) -> None:
        for gf in dataclasses.fields(RULES):
            with self.subTest(group=gf.name):
                self.assertTrue(gf.metadata["label"].strip())

    def test_pending_values_cite_their_open_question(self) -> None:
        for gf, rf, value in iter_rules(RULES):
            for q in pending_questions(value):
                with self.subTest(rule=f"{gf.name}.{rf.name}"):
                    self.assertIn(q, rf.metadata["sources"])

    def test_exactly_these_rules_are_undecided(self) -> None:
        pending = {
            f"{gf.name}.{rf.name}": pending_questions(v)
            for gf, rf, v in iter_rules(RULES)
            if contains_pending(v)
        }
        self.assertEqual(
            pending,
            {
                "reliability.PENALTY_CANCEL_4_TO_6_DAYS": ("Q-001",),
                "reliability.PENALTY_CANCEL_2_TO_3_DAYS": ("Q-001",),
                "reliability.PENALTY_CANCEL_1_DAY": ("Q-001",),
                "reliability.PENALTY_CANCEL_SAME_DAY": ("Q-001",),
                "reliability.PENALTY_NO_SHOW": ("Q-001",),
                "reliability.RECOVERY_PER_FULFILLED_COMMITMENT": ("Q-001",),
                "auth.SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR": ("Q-070",),
                "auth.SIGN_IN_RESEND_COOLDOWN": ("Q-070",),
                "auth.ACCOUNT_INVITATION_LIFETIME": ("Q-071",),
                "auth.MFA_CODE_MAX_ATTEMPTS": ("Q-072",),
                "reporting.PUBLIC_EMBED_MIN_GROUP_SIZE": ("Q-027",),
            },
        )

    def test_pending_proposals_are_recorded(self) -> None:
        for gf, rf, value in iter_rules(RULES):
            if isinstance(value, Pending):
                with self.subTest(rule=f"{gf.name}.{rf.name}"):
                    self.assertTrue(value.proposal.strip())


class ImmutabilityTest(unittest.TestCase):
    def test_groups_are_frozen(self) -> None:
        with self.assertRaises(dataclasses.FrozenInstanceError):
            RULES.staffing = None  # type: ignore[misc, assignment]

    def test_values_are_frozen(self) -> None:
        for gf in dataclasses.fields(RULES):
            group = getattr(RULES, gf.name)
            first = dataclasses.fields(group)[0].name
            with self.subTest(group=gf.name):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(group, first, 1)

    def test_no_new_attributes(self) -> None:
        with self.assertRaises((AttributeError, TypeError)):
            RULES.staffing.NEW_RULE = 1  # type: ignore[attr-defined]

    def test_metadata_is_read_only(self) -> None:
        rf = dataclasses.fields(RULES.staffing)[0]
        with self.assertRaises(TypeError):
            rf.metadata["label"] = "changed"  # type: ignore[index]

    def test_collection_values_are_tuples(self) -> None:
        for gf, rf, value in iter_rules(RULES):
            with self.subTest(rule=f"{gf.name}.{rf.name}"):
                self.assertNotIsInstance(value, (list, dict, set))

    def test_pending_is_immutable(self) -> None:
        p = Pending("Q-001", "x")
        with self.assertRaises(AttributeError):
            p.question = "Q-002"  # type: ignore[misc]


class PurityTest(unittest.TestCase):
    def test_no_django_import_in_source(self) -> None:
        for path in RULES_DIR.glob("*.py"):
            with self.subTest(file=path.name):
                self.assertFalse(any(m.split(".")[0] == "django" for m in _imported_modules(path)))

    def test_importing_rules_does_not_load_django_or_io_modules(self) -> None:
        code = (
            "import sys, ham.rules; "
            "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
            "{'django', 'psycopg', 'procrastinate', 'requests', 'socket'}); "
            "print(','.join(bad))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(out.stdout.strip(), "")

    def test_rules_only_import_within_package_and_stdlib(self) -> None:
        allowed = {"__future__", "dataclasses", "datetime", "typing", "hashlib", "json"}
        for path in RULES_DIR.glob("*.py"):
            for mod in _imported_modules(path):
                with self.subTest(file=path.name, module=mod):
                    self.assertTrue(mod.startswith(".") or mod.split(".")[0] in allowed, mod)


class InvariantsTest(unittest.TestCase):
    def test_current_rules_are_consistent(self) -> None:
        self.assertEqual(check_invariants(RULES), ())

    def _with(self, group: str, **changes: object):  # type: ignore[no-untyped-def]
        g = dataclasses.replace(getattr(RULES, group), **changes)
        return dataclasses.replace(RULES, **{group: g})

    def test_inconsistent_values_are_caught(self) -> None:
        cases: list[tuple[str, dict[str, Any], str]] = [
            ("staffing", {"UNCONFIRMED_RELEASE_DAYS_BEFORE": 7}, "release"),
            ("staffing", {"RECONFIRMATION_REMINDER_DAYS_BEFORE": (5, 6, 7)}, "descending"),
            ("staffing", {"RECONFIRMATION_REMINDER_DAYS_BEFORE": (8, 6, 5)}, "between"),
            (
                "staffing",
                {
                    "UNDERSTAFFED_ALERT_BEFORE_START": RULES.staffing.AUTO_STAFFING_CUTOFF_BEFORE_START
                },
                "understaffed",
            ),
            ("reliability", {"CANCELLATION_BAND_LOWER_BOUNDS_DAYS": (7, 4, 2, 1)}, "end at 0"),
            ("reliability", {"CANCELLATION_BAND_LOWER_BOUNDS_DAYS": (6, 4, 2, 1, 0)}, "free"),
            ("reliability", {"PENALTY_EXCUSED": 1}, "PENALTY_EXCUSED"),
            ("reliability", {"PENALTY_DEACTIVATION_AUTO_CANCEL": 5}, "DEACTIVATION"),
            ("reliability", {"PENALTY_DECLINE_LAST_MINUTE_ASSIGNMENT": 5}, "DECLINE"),
            ("reliability", {"INITIAL_SCORE": 101}, "initial score"),
            ("credentials", {"CREDENTIAL_EXPIRY_ALERT_DAYS": (7, 30, 60)}, "credential"),
            (
                "requester_access",
                {"SURVEY_REMINDER_AFTER_COMPLETION": RULES.requester_access.SURVEY_LINK_LIFETIME},
                "survey",
            ),
            (
                "auth",
                {"SESSION_IDLE_LIFETIME_MFA_ROLES": RULES.auth.SESSION_ABSOLUTE_LIFETIME_MFA_ROLES},
                "MFA idle",
            ),
        ]
        for group, changes, expected_fragment in cases:
            with self.subTest(group=group, changes=changes):
                problems = check_invariants(self._with(group, **changes))
                self.assertTrue(
                    any(expected_fragment in p for p in problems), (expected_fragment, problems)
                )

    def test_decided_reliability_numbers_are_validated_once_filled_in(self) -> None:
        good = self._with(
            "reliability",
            PENALTY_CANCEL_4_TO_6_DAYS=3,
            PENALTY_CANCEL_2_TO_3_DAYS=6,
            PENALTY_CANCEL_1_DAY=10,
            PENALTY_CANCEL_SAME_DAY=16,
            PENALTY_NO_SHOW=20,
            RECOVERY_PER_FULFILLED_COMMITMENT=2,
        )
        self.assertEqual(check_invariants(good), ())
        bad = self._with(
            "reliability",
            PENALTY_CANCEL_4_TO_6_DAYS=3,
            PENALTY_CANCEL_2_TO_3_DAYS=6,
            PENALTY_CANCEL_1_DAY=10,
            PENALTY_CANCEL_SAME_DAY=20,
            PENALTY_NO_SHOW=20,
            RECOVERY_PER_FULFILLED_COMMITMENT=2,
        )
        self.assertTrue(check_invariants(bad))


if __name__ == "__main__":
    unittest.main()
