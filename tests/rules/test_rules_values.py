"""Every rule value, pinned independently of the module (foundation.md §5, §9.5).

This table is the oracle: it is written from the PRD and docs/prd-open-questions.md, not
copied from the code. A rule missing here, or a value that differs, fails.

Written as unittest so it runs under pytest and under ``python -m unittest``.
"""

import unittest
from datetime import timedelta

from ham.rules import RULES, CalendarYears, Pending, iter_rules

H = lambda n: timedelta(hours=n)  # noqa: E731
D = lambda n: timedelta(days=n)  # noqa: E731
M = lambda n: timedelta(minutes=n)  # noqa: E731

EXPECTED = {
    # Staffing (§28–§32, §76)
    "staffing.INVITATION_RESPONSE_WINDOW": H(48),  # Q-002
    "staffing.WAITLIST_PROMOTION_CONFIRM_WINDOW": H(24),  # §29, §32
    "staffing.AUTO_STAFFING_CUTOFF_BEFORE_START": H(48),  # §29, §30
    "staffing.UNDERSTAFFED_ALERT_BEFORE_START": H(96),  # Q-013
    "staffing.RECONFIRMATION_DAYS_BEFORE": 7,  # §32
    "staffing.RECONFIRMATION_REMINDER_DAYS_BEFORE": (7, 6, 5),  # Q-011
    "staffing.UNCONFIRMED_RELEASE_DAYS_BEFORE": 5,  # §32
    "staffing.AGREEMENT_UNACCEPTED_LEADER_ALERT_BEFORE_START": H(48),  # Q-014
    # Reliability (§21, §30, §33, §34)
    "reliability.SCORE_MIN": 0,
    "reliability.SCORE_MAX": 100,
    "reliability.INITIAL_SCORE": 100,
    "reliability.CANCELLATION_FREE_DAYS_BEFORE": 7,
    "reliability.CANCELLATION_BAND_LOWER_BOUNDS_DAYS": (7, 4, 2, 1, 0),
    "reliability.PENALTY_CANCEL_7_PLUS_DAYS": 0,
    "reliability.PENALTY_CANCEL_4_TO_6_DAYS": Pending("Q-001", ""),
    "reliability.PENALTY_CANCEL_2_TO_3_DAYS": Pending("Q-001", ""),
    "reliability.PENALTY_CANCEL_1_DAY": Pending("Q-001", ""),
    "reliability.PENALTY_CANCEL_SAME_DAY": Pending("Q-001", ""),
    "reliability.PENALTY_NO_SHOW": Pending("Q-001", ""),
    "reliability.RECOVERY_PER_FULFILLED_COMMITMENT": Pending("Q-001", ""),
    "reliability.PENALTY_EXCUSED": 0,  # §33
    "reliability.PENALTY_DEACTIVATION_AUTO_CANCEL": 0,  # §21
    "reliability.PENALTY_DECLINE_LAST_MINUTE_ASSIGNMENT": 0,  # §30
    # Credentials (§24.1)
    "credentials.CREDENTIAL_EXPIRY_ALERT_DAYS": (60, 30, 7),
    # Attendance
    "attendance.LATE_GRACE_PERIOD": M(15),  # Q-020
    "attendance.LEADER_PHONE_VISIBLE_FROM_DAYS_BEFORE": 1,  # Q-023
    # Requester links and survey (§7.3, §54)
    "requester_access.REQUESTER_LINK_VALID_AFTER_COMPLETION": D(7),
    "requester_access.REGENERATED_REQUESTER_LINK_LIFETIME": D(14),
    "requester_access.SURVEY_LINK_LIFETIME": D(30),
    "requester_access.SURVEY_REMINDER_AFTER_COMPLETION": D(7),
    "requester_access.SURVEY_REMINDER_COUNT": 1,
    "requester_access.SURVEY_RATING_MIN": 1,
    "requester_access.SURVEY_RATING_MAX": 5,
    # Media (§45–§47)
    "media.REQUESTER_MEDIA_BATCH_MAX_PHOTOS": 10,
    "media.REQUESTER_MEDIA_BATCH_MAX_VIDEOS": 3,
    "media.REQUESTER_MEDIA_MAX_VIDEO_DURATION": M(2),
    "media.VIDEO_RETENTION_AFTER_CLOSE": D(30),
    "media.PHOTO_RETENTION_AFTER_CLOSE": D(90),
    # Retention (§41, §42, §56, §58)
    "retention.AUDIT_RETENTION": CalendarYears(1),  # Q-036
    "retention.INCIDENT_RETENTION": CalendarYears(7),
    "retention.HOMEOWNER_AGREEMENT_RETENTION": CalendarYears(7),
    "retention.VOLUNTEER_AGREEMENT_RETENTION_AFTER_INACTIVE": CalendarYears(7),
    # Auth (§59, §60, Q-010, Q-032, Q-035, Q-046)
    "auth.MFA_REQUIRED_ROLES": (
        "ADMINISTRATOR",
        "HAM_DIRECTOR",
        "ASSISTANT_DIRECTOR",
        "PASTOR",
        "BOARD_REPRESENTATIVE",
    ),
    "auth.MFA_TRUSTED_DEVICE_LIFETIME": D(30),
    "auth.MFA_RECOVERY_CODE_COUNT": 10,
    "auth.STEP_UP_ACTIONS": (
        ("role.grant_global", "role_change"),
        ("role.revoke_global", "role_change"),
        ("audit.export", "audit_export"),
        ("user.mfa_reset", "mfa_reset"),
        ("impersonation.start", "impersonation_start"),
        ("me.recovery_codes.regenerate", "recovery_codes_regenerate"),
        ("me.sign_in_email.change", "sign_in_email_change"),
    ),
    "auth.STEP_UP_WINDOW": M(5),
    "auth.SIGN_IN_CODE_LENGTH": 6,
    "auth.SIGN_IN_CODE_LIFETIME": M(15),
    "auth.SIGN_IN_CODE_MAX_ATTEMPTS": 5,
    "auth.SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR": Pending("Q-070", ""),
    "auth.SIGN_IN_RESEND_COOLDOWN": Pending("Q-070", ""),
    "auth.ACCOUNT_INVITATION_LIFETIME": Pending("Q-071", ""),
    "auth.MFA_CODE_MAX_ATTEMPTS": Pending("Q-072", ""),
    "auth.SESSION_IDLE_LIFETIME_STANDARD": D(30),
    "auth.SESSION_IDLE_LIFETIME_MFA_ROLES": H(8),
    "auth.SESSION_ABSOLUTE_LIFETIME_MFA_ROLES": D(7),
    "auth.IMPERSONATION_IDLE_TIMEOUT": M(15),  # §59
    # Reporting
    "reporting.PUBLIC_EMBED_MIN_GROUP_SIZE": Pending("Q-027", ""),
    # Outbox (engineering, foundation.md §5)
    "outbox.OUTBOX_MAX_ATTEMPTS": 8,
    "outbox.OUTBOX_BACKOFF_INITIAL": M(1),
    "outbox.OUTBOX_BACKOFF_MAX": H(6),
}


def _actual() -> dict[str, object]:
    return {f"{g.name}.{r.name}": v for g, r, v in iter_rules(RULES)}


class PinnedValuesTest(unittest.TestCase):
    def test_every_rule_is_pinned_and_nothing_extra(self) -> None:
        actual = _actual()
        self.assertEqual(sorted(actual), sorted(EXPECTED))

    def test_each_value(self) -> None:
        actual = _actual()
        for key, expected in EXPECTED.items():
            with self.subTest(rule=key):
                value = actual[key]
                self.assertIs(type(value), type(expected), key)
                if isinstance(expected, Pending):
                    self.assertEqual(value.question, expected.question)  # type: ignore[attr-defined]
                else:
                    self.assertEqual(value, expected)

    def test_int_rules_are_not_bools(self) -> None:
        for key, value in _actual().items():
            with self.subTest(rule=key):
                self.assertNotIsInstance(value, bool)


if __name__ == "__main__":
    unittest.main()
