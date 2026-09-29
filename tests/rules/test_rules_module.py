"""Structure of the rules module: sources on every value, immutability, and purity."""

import ast
import dataclasses
import re
import subprocess
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from typing import Any

from ham.rules import RULES, CalendarYears, Pending, check_invariants
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
                "reporting.PUBLIC_EMBED_MIN_GROUP_SIZE": ("Q-027",),
            },
        )

    def test_exactly_these_rules_run_on_a_proposed_default(self) -> None:
        """Owner, 2026-09-28: use the proposed defaults for these open questions for now."""
        provisional = {
            f"{gf.name}.{rf.name}": rf.metadata["provisional"]
            for gf, rf, _v in iter_rules(RULES)
            if rf.metadata["provisional"]
        }
        q073 = ("Q-073",)
        self.assertEqual(
            provisional,
            {
                "staffing.RECONFIRMATION_DAYS_BEFORE": q073,
                "staffing.RECONFIRMATION_REMINDER_DAYS_BEFORE": q073,
                "staffing.UNCONFIRMED_RELEASE_DAYS_BEFORE": q073,
                "reliability.CANCELLATION_FREE_DAYS_BEFORE": q073,
                "reliability.CANCELLATION_BAND_LOWER_BOUNDS_DAYS": q073,
                "reliability.PENALTY_CANCEL_4_TO_6_DAYS": ("Q-001",),
                "reliability.PENALTY_CANCEL_2_TO_3_DAYS": ("Q-001",),
                "reliability.PENALTY_CANCEL_1_DAY": ("Q-001",),
                "reliability.PENALTY_CANCEL_SAME_DAY": ("Q-001", "Q-075"),
                "reliability.PENALTY_NO_SHOW": ("Q-001", "Q-075"),
                "reliability.RECOVERY_PER_FULFILLED_COMMITMENT": ("Q-001",),
                "retention.INCIDENT_RETENTION": ("Q-074",),
                "retention.HOMEOWNER_AGREEMENT_RETENTION": ("Q-074",),
                "auth.STEP_UP_ACTIONS": ("Q-076",),
                "auth.SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR": ("Q-070",),
                "auth.SIGN_IN_RESEND_COOLDOWN": ("Q-070",),
                "auth.SIGN_IN_REQUESTS_PER_IP_PER_HOUR": ("Q-070",),
                "auth.SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY": ("Q-070",),
                "auth.ACCOUNT_INVITATION_LIFETIME": ("Q-071",),
                "auth.MFA_CODE_MAX_ATTEMPTS": ("Q-072",),
                "operations.HEALTH_MAX_QUEUE_LAG": ("Q-056",),
                # Step 2 (intake), owner 2026-09-28: proposed defaults in use.
                "requester_access.REQUESTER_ACCESS_AFTER_CLOSE": ("Q-116",),
                "requester_access.EARLY_REGENERATED_LINK_FOLLOWS_NORMAL_ACCESS": ("Q-117",),
                "intake.REQUESTER_CODE_MAX_ATTEMPTS": ("Q-121",),
                "intake.REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR": ("Q-121",),
                "intake.REQUESTER_CODE_RESEND_COOLDOWN": ("Q-121",),
                "intake.REQUESTER_CODE_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY": ("Q-121",),
                "intake.REQUESTER_CHALLENGE_RETENTION": ("Q-121",),
                "intake.INTAKE_FORMS_PER_IP_PER_HOUR": ("Q-121",),
                "intake.INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY": ("Q-121",),
                "intake.FIND_REQUEST_TRIES_PER_IP_PER_HOUR": ("Q-121",),
                "intake.INTAKE_MIN_FILL_TIME": ("Q-121",),
                "intake.REQUESTER_CODE_EMAILS_PER_IP_PER_HOUR": ("Q-121",),
                "intake.NO_EMAIL_SUBMISSIONS_PER_PHONE_PER_DAY": ("Q-146",),
                "intake.FIND_REQUEST_EMAILS_PER_ADDRESS_PER_DAY": ("Q-121",),
                # Step 3 (approvals): 14 days is decided (Q-155); the end-of-church-day
                # reading of it is Q-174's proposed default.
                "approvals.RECONSIDERATION_REQUEST_WINDOW": ("Q-174",),
                "media.MEDIA_RETENTION_CLOCK_ON_CANCELLATION": ("Q-128",),
                "media.REQUESTER_PHOTO_MAX_BYTES": ("Q-119",),
                "media.REQUESTER_VIDEO_MAX_BYTES": ("Q-119",),
                "media.REQUESTER_PHOTO_TYPES": ("Q-119",),
                "media.REQUESTER_VIDEO_TYPES": ("Q-119",),
            },
        )

    def test_provisional_rules_cite_and_explain_their_open_question(self) -> None:
        for gf, rf, value in iter_rules(RULES):
            for q in rf.metadata["provisional"]:
                with self.subTest(rule=f"{gf.name}.{rf.name}", question=q):
                    self.assertFalse(contains_pending(value), "a proposed default is a value")
                    self.assertIn(q, rf.metadata["sources"])
                    self.assertIn(
                        f"PRD-GAP {q}: proposed default in use; owner may change",
                        rf.metadata["note"],
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

    def test_q001_proposed_numbers_are_in_use_and_valid(self) -> None:
        r = RULES.reliability
        self.assertEqual(
            (
                r.PENALTY_CANCEL_4_TO_6_DAYS,
                r.PENALTY_CANCEL_2_TO_3_DAYS,
                r.PENALTY_CANCEL_1_DAY,
                r.PENALTY_CANCEL_SAME_DAY,
                r.PENALTY_NO_SHOW,
                r.RECOVERY_PER_FULFILLED_COMMITMENT,
            ),
            (3, 6, 10, 16, 20, 2),
        )

    def test_new_auth_and_ops_invariants(self) -> None:
        cases: list[tuple[str, dict[str, Any], str]] = [
            ("auth", {"SIGN_IN_RESEND_COOLDOWN": timedelta(0)}, "cooldown"),
            ("auth", {"SIGN_IN_RESEND_COOLDOWN": timedelta(hours=1)}, "cooldown"),
            ("auth", {"SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR": 0}, "SIGN_IN_EMAILS"),
            ("auth", {"MFA_CODE_MAX_ATTEMPTS": 0}, "MFA_CODE_MAX_ATTEMPTS"),
            ("auth", {"ACCOUNT_INVITATION_LIFETIME": timedelta(minutes=15)}, "invitation"),
            ("operations", {"HEALTH_MAX_QUEUE_LAG": timedelta(0)}, "queue-lag"),
            ("reliability", {"PENALTY_CANCEL_SAME_DAY": 20}, "same day"),
            ("reliability", {"RECOVERY_PER_FULFILLED_COMMITMENT": 20}, "gradual"),
        ]
        for group, changes, expected_fragment in cases:
            with self.subTest(group=group, changes=changes):
                problems = check_invariants(self._with(group, **changes))
                self.assertTrue(
                    any(expected_fragment in p for p in problems), (expected_fragment, problems)
                )

    def test_intake_media_and_retention_invariants(self) -> None:
        it, m = RULES.intake, RULES.media
        cases: list[tuple[str, dict[str, Any], str]] = [
            ("requester_access", {"REQUESTER_ACCESS_AFTER_CLOSE": timedelta(0)}, "after close"),
            ("intake", {"INTAKE_DRAFT_LIFETIME": it.REQUESTER_CODE_LIFETIME}, "unfinished form"),
            ("intake", {"REQUESTER_CODE_RESEND_COOLDOWN": timedelta(0)}, "requester resend"),
            ("intake", {"REQUESTER_CODE_RESEND_COOLDOWN": timedelta(hours=1)}, "requester resend"),
            ("intake", {"INTAKE_MIN_FILL_TIME": timedelta(0)}, "fill time"),
            ("intake", {"REQUESTER_CODE_LENGTH": 0}, "REQUESTER_CODE_LENGTH"),
            ("intake", {"INTAKE_FORMS_PER_IP_PER_HOUR": 0}, "INTAKE_FORMS_PER_IP"),
            ("intake", {"INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY": 0}, "SUBMISSIONS_PER_EMAIL"),
            ("intake", {"FIND_REQUEST_TRIES_PER_IP_PER_HOUR": 0}, "FIND_REQUEST"),
            ("intake", {"REQUESTER_CODE_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY": 4}, "daily"),
            ("intake", {"REQUESTER_CHALLENGE_RETENTION": timedelta(hours=24)}, "24-hour"),
            ("media", {"REQUESTER_PHOTO_MAX_BYTES": 0}, "upload size"),
            ("media", {"REQUESTER_PHOTO_MAX_BYTES": m.REQUESTER_VIDEO_MAX_BYTES + 1}, "upload"),
            ("media", {"REQUESTER_PHOTO_TYPES": ()}, "REQUESTER_PHOTO_TYPES"),
            ("media", {"REQUESTER_PHOTO_TYPES": ("image/png", "image/png")}, "unique"),
            ("media", {"REQUESTER_VIDEO_TYPES": ("image/png",)}, "video/*"),
            ("media", {"REQUESTER_PHOTO_TYPES": ("image/PNG",)}, "lower-case"),
            ("retention", {"SPAM_REQUEST_RETENTION": timedelta(0)}, "spam"),
            (
                "retention",
                {"REQUEST_RECORD_RETENTION_AFTER_CLOSE": CalendarYears(0)},
                "record retention",
            ),
        ]
        for group, changes, expected_fragment in cases:
            with self.subTest(group=group, changes=changes):
                problems = check_invariants(self._with(group, **changes))
                self.assertTrue(
                    any(expected_fragment in p for p in problems), (expected_fragment, problems)
                )

    def test_approval_invariants(self) -> None:
        """Undo window < 1 day <= reconsideration window (Q-155, Q-156, Q-174, Q-176)."""
        ap = RULES.approvals
        self.assertLess(ap.DECISION_UNDO_WINDOW, timedelta(days=1))
        self.assertLessEqual(timedelta(days=1), timedelta(days=ap.RECONSIDERATION_REQUEST_WINDOW))
        cases: list[tuple[dict[str, Any], str]] = [
            ({"RECONSIDERATION_REQUEST_WINDOW": 0}, "reconsideration window"),
            ({"RECONSIDERATION_REQUEST_WINDOW": -14}, "reconsideration window"),
            ({"RECONSIDERATION_REQUEST_WINDOW": True}, "reconsideration window"),
            ({"RECONSIDERATION_REQUEST_WINDOW": timedelta(days=14)}, "whole number of days"),
            ({"DECISION_UNDO_WINDOW": timedelta(0)}, "undo window"),
            ({"DECISION_UNDO_WINDOW": timedelta(days=1)}, "undo window"),
            ({"DECISION_UNDO_WINDOW": timedelta(days=20)}, "undo window"),
        ]
        for changes, expected_fragment in cases:
            with self.subTest(changes=changes):
                problems = check_invariants(self._with("approvals", **changes))
                self.assertTrue(
                    any(expected_fragment in p for p in problems), (expected_fragment, problems)
                )
        # The smallest consistent set still passes: a 1-day window, a just-under-a-day undo.
        ok = self._with(
            "approvals",
            RECONSIDERATION_REQUEST_WINDOW=1,
            DECISION_UNDO_WINDOW=timedelta(days=1) - timedelta(seconds=1),
        )
        self.assertEqual(check_invariants(ok), ())

    def test_requester_codes_match_sign_in_values(self) -> None:
        """Q-121: requester code limits are 'as sign-in' -- separate names, same numbers."""
        it, a = RULES.intake, RULES.auth
        self.assertEqual(it.REQUESTER_CODE_LENGTH, a.SIGN_IN_CODE_LENGTH)
        self.assertEqual(it.REQUESTER_CODE_LIFETIME, a.SIGN_IN_CODE_LIFETIME)
        self.assertEqual(it.REQUESTER_CODE_MAX_ATTEMPTS, a.SIGN_IN_CODE_MAX_ATTEMPTS)
        self.assertEqual(
            it.REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR, a.SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR
        )
        self.assertEqual(it.REQUESTER_CODE_RESEND_COOLDOWN, a.SIGN_IN_RESEND_COOLDOWN)
        self.assertEqual(
            it.REQUESTER_CODE_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY,
            a.SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY,
        )
        self.assertEqual(it.REQUESTER_CHALLENGE_RETENTION, a.SIGN_IN_CHALLENGE_RETENTION)

    def test_no_per_household_request_limit(self) -> None:
        """PRD §5 'no fixed limit': no rule may cap requests per household or address."""
        for gf, rf, _v in iter_rules(RULES):
            with self.subTest(rule=f"{gf.name}.{rf.name}"):
                self.assertNotRegex(rf.name, r"HOUSEHOLD|REQUESTS_PER_ADDRESS|PER_PROPERTY")

    def test_days_ham_serves_is_not_a_rule(self) -> None:
        """Q-112: the days offered on the form are a church-profile setting, not a rule."""
        for gf, rf, _v in iter_rules(RULES):
            with self.subTest(rule=f"{gf.name}.{rf.name}"):
                self.assertNotIn("SERVE", rf.name)

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
