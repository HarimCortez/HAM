"""The read-only data behind the Admin "Rules" screen (action ``rules.view``)."""

import dataclasses
import unittest
from datetime import timedelta

from ham.rules import RULES, RULES_HASH, RULES_VERSION, RuleRow, rules_view
from ham.rules.v1 import iter_rules
from ham.rules.view import format_duration


def _row(key: str) -> RuleRow:
    return next(r for r in rules_view().rows if r.key == key)


class RulesViewTest(unittest.TestCase):
    def test_header(self) -> None:
        view = rules_view()
        self.assertEqual(view.version, RULES_VERSION)
        self.assertEqual(view.content_hash, RULES_HASH)

    def test_one_row_per_rule_in_declaration_order(self) -> None:
        keys = [r.key for r in rules_view().rows]
        self.assertEqual(keys, [f"{g.name}.{r.name}" for g, r, _ in iter_rules(RULES)])
        self.assertEqual(len(keys), len(set(keys)))

    def test_read_only(self) -> None:
        view = rules_view()
        self.assertIsInstance(view.rows, tuple)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            view.rows[0].value = "changed"  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            view.version = "x"  # type: ignore[misc]

    def test_every_row_is_human_labelled(self) -> None:
        for row in rules_view().rows:
            with self.subTest(rule=row.key):
                self.assertTrue(row.group and row.label and row.value and row.sources)
                self.assertNotIn("timedelta", row.value)
                self.assertNotIn("Pending(", row.value)
                self.assertNotIn("_", row.value)  # no raw codes like HAM_DIRECTOR shown

    def test_display_values(self) -> None:
        cases = {
            "staffing.INVITATION_RESPONSE_WINDOW": "48 hours",
            "staffing.WAITLIST_PROMOTION_CONFIRM_WINDOW": "24 hours",
            "staffing.UNDERSTAFFED_ALERT_BEFORE_START": "96 hours",
            "staffing.RECONFIRMATION_REMINDER_DAYS_BEFORE": "7, 6 and 5 days before the project",
            "staffing.UNCONFIRMED_RELEASE_DAYS_BEFORE": "5 days before the project",
            "credentials.CREDENTIAL_EXPIRY_ALERT_DAYS": "60, 30 and 7 days before expiration",
            "attendance.LATE_GRACE_PERIOD": "15 minutes",
            "attendance.LEADER_PHONE_VISIBLE_FROM_DAYS_BEFORE": "1 calendar day before the project (church time zone)",
            "requester_access.REGENERATED_REQUESTER_LINK_LIFETIME": "14 days",
            "requester_access.SURVEY_REMINDER_COUNT": "1 reminder",
            "media.PHOTO_RETENTION_AFTER_CLOSE": "90 days",
            "media.REQUESTER_MEDIA_MAX_VIDEO_DURATION": "2 minutes",
            "retention.AUDIT_RETENTION": "1 year",
            "retention.INCIDENT_RETENTION": "7 years",
            "auth.MFA_REQUIRED_ROLES": "Administrator, HAM Director, Assistant Director, "
            "Pastor and Board representative",
            "auth.SESSION_IDLE_LIFETIME_MFA_ROLES": "8 hours",
            "auth.SESSION_ABSOLUTE_LIFETIME_MFA_ROLES": "7 days",
            "outbox.OUTBOX_BACKOFF_INITIAL": "1 minute",
            "reliability.PENALTY_EXCUSED": "0 points",
            "reliability.PENALTY_NO_SHOW": "20 points",
            "reliability.RECOVERY_PER_FULFILLED_COMMITMENT": "2 points",
            "auth.SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR": "5 emails",
            "auth.SIGN_IN_RESEND_COOLDOWN": "30 seconds",
            "auth.ACCOUNT_INVITATION_LIFETIME": "7 days",
            "auth.MFA_CODE_MAX_ATTEMPTS": "5 tries",
            "operations.HEALTH_MAX_QUEUE_LAG": "5 minutes",
            "reporting.PUBLIC_EMBED_MIN_GROUP_SIZE": "Not decided yet: waiting for the product "
            "owner (Q-027)",
        }
        for key, expected in cases.items():
            with self.subTest(rule=key):
                self.assertEqual(_row(key).value, expected)

    def test_step_up_actions_are_shown_as_plain_language(self) -> None:
        value = _row("auth.STEP_UP_ACTIONS").value
        self.assertIn("Export the audit log", value)
        self.assertNotIn("audit.export", value)

    def test_pending_rows_are_marked(self) -> None:
        row = _row("reporting.PUBLIC_EMBED_MIN_GROUP_SIZE")
        self.assertFalse(row.decided)
        self.assertEqual(row.pending_questions, ("Q-027",))
        decided = _row("staffing.INVITATION_RESPONSE_WINDOW")
        self.assertTrue(decided.decided)
        self.assertEqual(decided.pending_questions, ())
        self.assertEqual(decided.sources, ("PRD §28", "Q-002"))
        self.assertFalse(decided.provisional)

    def test_proposed_default_rows_are_marked(self) -> None:
        row = _row("reliability.PENALTY_NO_SHOW")
        self.assertTrue(row.decided)  # a real value, in use
        self.assertTrue(row.provisional)
        self.assertEqual(row.provisional_questions, ("Q-001", "Q-075"))
        self.assertIn("proposed default in use", row.note)
        self.assertEqual(_row("operations.HEALTH_MAX_QUEUE_LAG").provisional_questions, ("Q-056",))

    def test_format_duration(self) -> None:
        cases = [
            (timedelta(minutes=1), "1 minute"),
            (timedelta(minutes=90), "90 minutes"),
            (timedelta(hours=1), "1 hour"),
            (timedelta(hours=48), "48 hours"),
            (timedelta(days=6), "144 hours"),
            (timedelta(days=7), "7 days"),
            (timedelta(days=7, hours=1), "169 hours"),
            (timedelta(seconds=30), "30 seconds"),
        ]
        for td, expected in cases:
            with self.subTest(td=td):
                self.assertEqual(format_duration(td), expected)
        with self.assertRaises(ValueError):
            format_duration(timedelta(microseconds=1))


if __name__ == "__main__":
    unittest.main()
