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
    # Q-001 proposed default in use (owner, 2026-09-28): small < ... < largest, +2 recovery
    "reliability.PENALTY_CANCEL_4_TO_6_DAYS": 3,
    "reliability.PENALTY_CANCEL_2_TO_3_DAYS": 6,
    "reliability.PENALTY_CANCEL_1_DAY": 10,
    "reliability.PENALTY_CANCEL_SAME_DAY": 16,
    "reliability.PENALTY_NO_SHOW": 20,
    "reliability.RECOVERY_PER_FULFILLED_COMMITMENT": 2,
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
    "requester_access.REQUESTER_ACCESS_AFTER_CLOSE": D(7),  # Q-116 proposed default
    "requester_access.EARLY_REGENERATED_LINK_FOLLOWS_NORMAL_ACCESS": True,  # Q-117
    # Public form and requester codes (§6, §7.1; Q-100, Q-121, Q-127)
    "intake.INTAKE_DRAFT_LIFETIME": H(24),  # Q-127 decided
    "intake.REQUESTER_CODE_LENGTH": 6,  # Q-100 "6-digit code"
    "intake.REQUESTER_CODE_LIFETIME": M(15),  # as sign-in (Q-032)
    "intake.REQUESTER_CODE_MAX_ATTEMPTS": 5,  # Q-121 = sign-in
    "intake.REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR": 5,  # Q-121 = Q-070
    "intake.REQUESTER_CODE_RESEND_COOLDOWN": timedelta(seconds=30),  # Q-121 = Q-070
    "intake.REQUESTER_CODE_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY": 20,  # Q-121 = Q-070
    "intake.REQUESTER_CHALLENGE_RETENTION": D(7),  # Q-121 = sign-in
    "intake.INTAKE_FORMS_PER_IP_PER_HOUR": 10,  # Q-121
    "intake.INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY": 3,  # Q-121
    "intake.FIND_REQUEST_TRIES_PER_IP_PER_HOUR": 20,  # Q-121
    "intake.INTAKE_MIN_FILL_TIME": timedelta(seconds=3),  # Q-121 (number from plan §9)
    # Media (§45–§47)
    "media.REQUESTER_MEDIA_BATCH_MAX_PHOTOS": 10,
    "media.REQUESTER_MEDIA_BATCH_MAX_VIDEOS": 3,
    "media.REQUESTER_MEDIA_MAX_VIDEO_DURATION": M(2),
    "media.VIDEO_RETENTION_AFTER_CLOSE": D(30),
    "media.PHOTO_RETENTION_AFTER_CLOSE": D(90),
    "media.MEDIA_RETENTION_CLOCK_ON_CANCELLATION": True,  # Q-128
    # Q-119: photos <= 25 MB, videos <= 500 MB (binary MB, the generous reading)
    "media.REQUESTER_PHOTO_MAX_BYTES": 25 * 1_048_576,
    "media.REQUESTER_VIDEO_MAX_BYTES": 500 * 1_048_576,
    "media.REQUESTER_PHOTO_TYPES": (
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
        "image/webp",
    ),
    "media.REQUESTER_VIDEO_TYPES": ("video/mp4", "video/quicktime"),
    # Retention (§41, §42, §56, §58)
    "retention.AUDIT_RETENTION": CalendarYears(1),  # Q-036
    "retention.INCIDENT_RETENTION": CalendarYears(7),
    "retention.HOMEOWNER_AGREEMENT_RETENTION": CalendarYears(7),
    "retention.VOLUNTEER_AGREEMENT_RETENTION_AFTER_INACTIVE": CalendarYears(7),
    "retention.REQUEST_RECORD_RETENTION_AFTER_CLOSE": CalendarYears(7),  # Q-127 decided
    "retention.SPAM_REQUEST_RETENTION": D(90),  # Q-127 decided
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
    # Proposed defaults in use (owner, 2026-09-28)
    "auth.SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR": 5,  # Q-070
    "auth.SIGN_IN_RESEND_COOLDOWN": timedelta(seconds=30),  # Q-070
    "auth.SIGN_IN_REQUESTS_PER_IP_PER_HOUR": 20,  # Q-070
    "auth.SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY": 20,  # Q-070
    "auth.ACCOUNT_INVITATION_LIFETIME": D(7),  # Q-071
    "auth.MFA_CODE_MAX_ATTEMPTS": 5,  # Q-072
    "auth.SESSION_IDLE_LIFETIME_STANDARD": D(30),
    "auth.SESSION_IDLE_LIFETIME_MFA_ROLES": H(8),
    "auth.SESSION_ABSOLUTE_LIFETIME_MFA_ROLES": D(7),
    "auth.IMPERSONATION_IDLE_TIMEOUT": M(15),  # §59
    "auth.SIGN_IN_CHALLENGE_RETENTION": D(7),
    # Reporting
    "reporting.PUBLIC_EMBED_MIN_GROUP_SIZE": Pending("Q-027", ""),
    # Outbox (engineering, foundation.md §5)
    "outbox.OUTBOX_MAX_ATTEMPTS": 8,
    "outbox.OUTBOX_BACKOFF_INITIAL": M(1),
    "outbox.OUTBOX_BACKOFF_MAX": H(6),
    "outbox.JOB_PAYLOAD_ENCRYPTION_TTL": D(1),  # security review round 3 N9
    # Operations
    "operations.HEALTH_MAX_QUEUE_LAG": M(5),  # Q-056 proposed default in use
    "operations.RECENT_ACTIVITY_WINDOW": H(24),  # security review round 3 M9
}

BOOL_RULES = {
    "requester_access.EARLY_REGENERATED_LINK_FOLLOWS_NORMAL_ACCESS",
    "media.MEDIA_RETENTION_CLOCK_ON_CANCELLATION",
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
            if key in BOOL_RULES:
                continue
            with self.subTest(rule=key):
                self.assertNotIsInstance(value, bool)

    def test_bool_rules_are_exactly_these(self) -> None:
        actual = {k for k, v in _actual().items() if isinstance(v, bool)}
        self.assertEqual(actual, BOOL_RULES)


if __name__ == "__main__":
    unittest.main()
