"""HAM rules, major version 1: every fixed business number in one place.

PRD §34 and §76 say these values are fixed system rules: deterministic, versioned, and
NOT administrator-configurable. There is no database and no Admin editing here.

How to change a value:
1. Change it here (with its PRD section / Q-id in ``sources``).
2. Bump ``RULES_VERSION`` (``YYYY.MM.DD-N``).
3. Add an entry to ``docs/rules-changelog.md``.
4. Pin the new content hash in ``tests/rules/test_version_hash.py``.
The version/hash test fails if a value changes without steps 2-4.

Every consequential record that depends on these rules (audit events, reliability score
changes) stores ``RULES_VERSION`` so history stays explainable (§34, §58).

Conventions (see ``types.py``): ``timedelta`` = elapsed UTC time; ``CalendarYears`` =
calendar retention; ``int`` fields state their unit in ``unit=``; ``Pending`` = PRD-GAP,
raises ``RuleNotDecidedError`` if used.

Proposed defaults in use: some open questions (``docs/prd-open-questions.md``) are still
"Open" but the product owner told us to run on the proposed default for now (2026-09-28).
Those rules carry real values, list the Q-id in ``provisional=`` and say
"PRD-GAP Q-NNN: proposed default in use; owner may change" in their note. The Admin
"Rules" screen marks them as proposed defaults. When the owner confirms a value unchanged,
drop the Q-id from ``provisional=`` (metadata only: no version bump). When the owner picks a
different value, that is a value change: follow the four steps above.

Pure Python. Must never import Django (it is imported by the DB layer, jobs and tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import timedelta
from typing import Any

from .types import CalendarYears, Pending

RULES_VERSION = "2026.09.28-6"


def rule(
    value: Any,
    *,
    label: str,
    sources: tuple[str, ...],
    unit: str = "",
    unit_one: str = "",
    note: str = "",
    provisional: tuple[str, ...] = (),
) -> Any:
    """Declare one rule: its value plus the human label and PRD/decision sources.

    ``provisional`` lists open questions whose *proposed default* this value is (the owner
    said to use it for now but has not closed the question). Each Q-id must also appear in
    ``sources``.

    The metadata is exposed read-only through ``dataclasses.fields(...)[i].metadata`` and is
    what the Admin "Rules" screen shows (see ``view.py``).
    """
    return field(
        default=value,
        metadata={
            "label": label,
            "sources": sources,
            "unit": unit,
            "unit_one": unit_one,
            "note": note,
            "provisional": provisional,
        },
    )


def proposed(q: str, detail: str = "") -> str:
    """Standard note text for a rule running on an open question's proposed default."""
    text = f"PRD-GAP {q}: proposed default in use; owner may change."
    return f"{text} {detail}" if detail else text


def group(factory: type, *, label: str) -> Any:
    return field(default_factory=factory, metadata={"label": label})


# --------------------------------------------------------------------------------------
# Staffing, invitations, waitlist and reconfirmation (PRD §28–§32, §76)
# --------------------------------------------------------------------------------------
# PRD-GAP Q-073: proposed default in use; owner may change. Day-based rules count calendar
# days in the church time zone; hour-based rules use elapsed UTC time.
_Q073_NOTE = proposed(
    "Q-073",
    "'Days before' means calendar days in the church time zone (reminders at 09:00 local; "
    "the release happens at the end of day 5); hour-based rules use elapsed time.",
)


@dataclass(frozen=True, slots=True)
class StaffingRules:
    INVITATION_RESPONSE_WINDOW: timedelta = rule(
        timedelta(hours=48),
        label="Time a volunteer has to answer an invitation",
        sources=("PRD §28", "Q-002"),
    )
    WAITLIST_PROMOTION_CONFIRM_WINDOW: timedelta = rule(
        timedelta(hours=24),
        label="Time a promoted waitlisted volunteer has to confirm (Pending Confirmation)",
        sources=("PRD §29", "PRD §32"),
    )
    AUTO_STAFFING_CUTOFF_BEFORE_START: timedelta = rule(
        timedelta(hours=48),
        label="Automatic invitations and waitlist cycling stop this long before the project; "
        "the Project Leader controls staffing after that",
        sources=("PRD §29", "PRD §30", "PRD §76"),
    )
    UNDERSTAFFED_ALERT_BEFORE_START: timedelta = rule(
        timedelta(hours=96),
        label="Leadership is alerted about an understaffed project this long before it starts",
        sources=("PRD §29", "PRD §30", "PRD §64", "Q-013"),
    )
    RECONFIRMATION_DAYS_BEFORE: int = rule(
        7,
        label="Accepted volunteers are asked to reconfirm",
        unit="days before the project",
        sources=("PRD §32", "Q-073"),
        note=_Q073_NOTE,
        provisional=("Q-073",),
    )
    RECONFIRMATION_REMINDER_DAYS_BEFORE: tuple[int, ...] = rule(
        (7, 6, 5),
        label="Daily reconfirmation reminders while unconfirmed",
        unit="days before the project",
        sources=("PRD §32", "Q-011", "Q-073"),
        note=_Q073_NOTE,
        provisional=("Q-073",),
    )
    UNCONFIRMED_RELEASE_DAYS_BEFORE: int = rule(
        5,
        label="A still-unconfirmed slot is released and the first qualified waitlisted "
        "volunteer is promoted",
        unit="days before the project",
        sources=("PRD §32", "PRD §76", "Q-073"),
        note=_Q073_NOTE,
        provisional=("Q-073",),
    )
    AGREEMENT_UNACCEPTED_LEADER_ALERT_BEFORE_START: timedelta = rule(
        timedelta(hours=48),
        label="Project Leader is alerted this long before start if an assigned volunteer has "
        "not accepted a changed agreement (the slot is kept; check-in is blocked)",
        sources=("PRD §42", "Q-014"),
    )


# --------------------------------------------------------------------------------------
# Reliability score (PRD §21, §30, §33, §34)
# --------------------------------------------------------------------------------------
# PRD-GAP Q-001: proposed default in use; owner may change. §34.1 only says
# small < moderate < larger < major < largest and "recovers gradually". Proposal (rationale):
# - 3 / 6 / 10 / 16 / 20: roughly doubling toward the project day, because a later
#   cancellation leaves less time to backfill; same-day (16) is "substantial but slightly
#   less than a no-show" (§33), and a no-show (20) is the largest.
# - +2 per commitment fulfilled as committed: one no-show takes 10 fulfilled commitments to
#   earn back, one 4-6-day cancellation takes 2 -- "gradual" but not permanent.
# - The score is clamped to [SCORE_MIN, SCORE_MAX] = [0, 100].
_Q001 = proposed(
    "Q-001",
    "Penalties 3 / 6 / 10 / 16 / 20 (small to largest) and +2 recovery per fulfilled "
    "commitment, clamped to 0-100.",
)
# PRD-GAP Q-075: proposed default in use; owner may change. Cancelling on the project day
# after the start time counts as a no-show unless excused (applied by the staffing module).
_Q075 = proposed(
    "Q-075",
    "Cancelling on the project day after the start time counts as a no-show unless excused.",
)
# PRD-GAP Q-077: proposed default in use; owner may change. No reliability penalty in V1 for
# an unanswered invitation, an unconfirmed waitlist promotion, or a slot released for not
# reconfirming: §34.1 lists only cancellations and no-shows. There is deliberately no rule
# value for these; the reliability module must not invent one.


@dataclass(frozen=True, slots=True)
class ReliabilityRules:
    SCORE_MIN: int = rule(0, label="Lowest possible reliability score", sources=("PRD §34",))
    SCORE_MAX: int = rule(100, label="Highest possible reliability score", sources=("PRD §34",))
    INITIAL_SCORE: int = rule(
        100, label="Score a new volunteer starts with", sources=("PRD §34.1",)
    )
    CANCELLATION_FREE_DAYS_BEFORE: int = rule(
        7,
        label="Cancelling at least this early carries no penalty",
        unit="days before the project",
        sources=("PRD §33", "PRD §34.1", "Q-073"),
        note=_Q073_NOTE,
        provisional=("Q-073",),
    )
    CANCELLATION_BAND_LOWER_BOUNDS_DAYS: tuple[int, ...] = rule(
        (7, 4, 2, 1, 0),
        label="Cancellation bands: 7+ days, 4–6 days, 2–3 days, 1 day, same day",
        unit="days before the project",
        sources=("PRD §34.1", "Q-073"),
        note=_Q073_NOTE,
        provisional=("Q-073",),
    )
    PENALTY_CANCEL_7_PLUS_DAYS: int = rule(
        0,
        label="Penalty: cancelled 7 or more days before",
        unit="points",
        sources=("PRD §33", "PRD §34.1"),
    )
    PENALTY_CANCEL_4_TO_6_DAYS: int = rule(
        3,
        label="Penalty: cancelled 4–6 days before (small)",
        unit="points",
        sources=("PRD §34.1", "Q-001"),
        note=_Q001,
        provisional=("Q-001",),
    )
    PENALTY_CANCEL_2_TO_3_DAYS: int = rule(
        6,
        label="Penalty: cancelled 2–3 days before (moderate)",
        unit="points",
        sources=("PRD §34.1", "Q-001"),
        note=_Q001,
        provisional=("Q-001",),
    )
    PENALTY_CANCEL_1_DAY: int = rule(
        10,
        label="Penalty: cancelled 1 day before (larger)",
        unit="points",
        sources=("PRD §34.1", "Q-001"),
        note=_Q001,
        provisional=("Q-001",),
    )
    PENALTY_CANCEL_SAME_DAY: int = rule(
        16,
        label="Penalty: same-day cancellation before the start time (major)",
        unit="points",
        sources=("PRD §33", "PRD §34.1", "Q-001", "Q-075"),
        note=f"{_Q001} {_Q075}",
        provisional=("Q-001", "Q-075"),
    )
    PENALTY_NO_SHOW: int = rule(
        20,
        label="Penalty: no-show, including cancelling after the start time on the project "
        "day (largest)",
        unit="points",
        sources=("PRD §33", "PRD §34.1", "Q-001", "Q-075"),
        note=f"{_Q001} {_Q075}",
        provisional=("Q-001", "Q-075"),
    )
    RECOVERY_PER_FULFILLED_COMMITMENT: int = rule(
        2,
        label="Gradual recovery for each commitment fulfilled as committed (the score never "
        "goes above the maximum)",
        unit="points",
        sources=("PRD §34.1", "Q-001"),
        note=_Q001,
        provisional=("Q-001",),
    )
    PENALTY_EXCUSED: int = rule(
        0,
        label="Penalty: cancellation or no-show marked excused (reason required)",
        unit="points",
        sources=("PRD §33", "PRD §34.1", "Q-022"),
    )
    PENALTY_DEACTIVATION_AUTO_CANCEL: int = rule(
        0,
        label="Penalty: assignment cancelled because the volunteer deactivated or the "
        "account was turned off",
        unit="points",
        sources=("PRD §21", "Q-052"),
    )
    PENALTY_DECLINE_LAST_MINUTE_ASSIGNMENT: int = rule(
        0,
        label="Penalty: declining an unsolicited assignment made inside the last 48 hours",
        unit="points",
        sources=("PRD §30",),
    )


# --------------------------------------------------------------------------------------
# Credentials (PRD §24.1)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class CredentialRules:
    CREDENTIAL_EXPIRY_ALERT_DAYS: tuple[int, ...] = rule(
        (60, 30, 7),
        label="Credential expiration alerts",
        unit="days before expiration",
        sources=("PRD §24.1", "PRD §76"),
    )


# --------------------------------------------------------------------------------------
# Attendance (PRD §37.2, §16, §68)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AttendanceRules:
    LATE_GRACE_PERIOD: timedelta = rule(
        timedelta(minutes=15),
        label="Check-in counts as Late after this grace period past the start time",
        sources=("PRD §37.2", "Q-020"),
    )
    LEADER_PHONE_VISIBLE_FROM_DAYS_BEFORE: int = rule(
        1,
        label="Assigned volunteers can see the Project Leader's phone from this many days "
        "before the project through the project day",
        unit="calendar days before the project (church time zone)",
        unit_one="calendar day before the project (church time zone)",
        sources=("PRD §16", "PRD §68", "Q-023", "Q-030"),
    )


# --------------------------------------------------------------------------------------
# Requester links and completion survey (PRD §7.3, §54)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RequesterAccessRules:
    REQUESTER_LINK_VALID_AFTER_COMPLETION: timedelta = rule(
        timedelta(days=7),
        label="Normal requester link keeps working this long after project completion",
        sources=("PRD §7.3",),
    )
    REGENERATED_REQUESTER_LINK_LIFETIME: timedelta = rule(
        timedelta(days=14),
        label="A self-regenerated requester link is valid for (and replaces the old link)",
        sources=("PRD §7.3", "PRD §76"),
    )
    SURVEY_LINK_LIFETIME: timedelta = rule(
        timedelta(days=30),
        label="Completion survey one-time link expires after",
        sources=("PRD §54",),
    )
    SURVEY_REMINDER_AFTER_COMPLETION: timedelta = rule(
        timedelta(days=7),
        label="One survey reminder is sent this long after completion, if not answered",
        sources=("PRD §54", "PRD §76"),
    )
    SURVEY_REMINDER_COUNT: int = rule(
        1,
        label="Number of survey reminders",
        unit="reminders",
        unit_one="reminder",
        sources=("PRD §54",),
    )
    SURVEY_RATING_MIN: int = rule(1, label="Lowest satisfaction rating", sources=("PRD §54",))
    SURVEY_RATING_MAX: int = rule(5, label="Highest satisfaction rating", sources=("PRD §54",))
    REQUESTER_ACCESS_AFTER_CLOSE: timedelta = rule(
        timedelta(days=7),
        label="Normal requester link keeps working this long after a request closes without "
        "being completed (Cancelled, Not Executable, or a final rejection); after that the "
        "requester can get a new 14-day link",
        sources=("PRD §7.3", "PRD §52", "Q-116"),
        note=proposed(
            "Q-116",
            "Mirrors the 7 days after completion. A rejection that can still be reconsidered "
            "is not a close.",
        ),
        provisional=("Q-116",),
    )
    EARLY_REGENERATED_LINK_FOLLOWS_NORMAL_ACCESS: bool = rule(
        True,
        label="A new link asked for before normal access ends (for example, a lost link) "
        "lasts as long as the normal link would, instead of a fixed 14 days; the old link "
        "stops working either way",
        sources=("PRD §7.3", "Q-117"),
        note=proposed(
            "Q-117",
            "'No' would mean every new link lasts exactly 14 days from when it is issued.",
        ),
        provisional=("Q-117",),
    )


# --------------------------------------------------------------------------------------
# Public request form, requester codes and abuse limits (PRD §6, §7.1; Q-100, Q-121, Q-127)
# --------------------------------------------------------------------------------------
# The requester's emailed code deliberately has its OWN names (same values as sign-in, Q-121
# "code limits as sign-in"), so tightening staff sign-in later cannot silently change what an
# older requester has to cope with, and vice versa.
_Q121 = proposed(
    "Q-121",
    "No CAPTCHA; a hidden trap field, a minimum fill time and these limits. Code limits "
    "match staff sign-in (Q-070).",
)


@dataclass(frozen=True, slots=True)
class IntakeRules:
    INTAKE_DRAFT_LIFETIME: timedelta = rule(
        timedelta(hours=24),
        label="An unfinished request form (not yet confirmed with the emailed code) is kept, "
        "encrypted, for this long and then erased",
        sources=("PRD §6", "PRD §68", "Q-100", "Q-127"),
    )
    REQUESTER_CODE_LENGTH: int = rule(
        6,
        label="Digits in the code emailed to a requester",
        unit="digits",
        sources=("PRD §7.1", "Q-100"),
    )
    REQUESTER_CODE_LIFETIME: timedelta = rule(
        timedelta(minutes=15),
        label="The code or link emailed to a requester is valid for (single use)",
        sources=("PRD §7.1", "Q-100", "Q-032"),
    )
    REQUESTER_CODE_MAX_ATTEMPTS: int = rule(
        5,
        label="Wrong code entries before the requester's emailed code stops working (their "
        "answers are kept; they can ask for a new code)",
        unit="tries",
        sources=("PRD §7.1", "Q-100", "Q-121"),
        note=_Q121,
        provisional=("Q-121",),
    )
    REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR: int = rule(
        5,
        label="Code emails to one requester email address in any rolling hour",
        unit="emails",
        sources=("PRD §7.1", "Q-121"),
        note=_Q121,
        provisional=("Q-121",),
    )
    REQUESTER_CODE_RESEND_COOLDOWN: timedelta = rule(
        timedelta(seconds=30),
        label="Wait before a requester can ask to resend the code",
        sources=("PRD §7.1", "Q-121"),
        note=_Q121,
        provisional=("Q-121",),
    )
    REQUESTER_CODE_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY: int = rule(
        20,
        label="Wrong codes for one requester email address in any rolling 24 hours before "
        "further tries for that address are refused for the day",
        unit="attempts",
        sources=("PRD §7.1", "Q-121"),
        note=_Q121,
        provisional=("Q-121",),
    )
    REQUESTER_CHALLENGE_RETENTION: timedelta = rule(
        timedelta(days=7),
        label="A used, expired or abandoned requester code/link record is erased after",
        sources=("PRD §68", "Q-121"),
        note=proposed(
            "Q-121",
            "Same as staff sign-in: kept only to enforce the daily limit, then erased.",
        ),
        provisional=("Q-121",),
    )
    INTAKE_FORMS_PER_IP_PER_HOUR: int = rule(
        10,
        label="New request forms started from one internet address in any rolling hour",
        unit="forms",
        sources=("PRD §6", "Q-121"),
        note=_Q121,
        provisional=("Q-121",),
    )
    INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY: int = rule(
        3,
        label="Requests sent with one email address in any rolling 24 hours (a helper can "
        "still send a few for different people)",
        unit="requests",
        sources=("PRD §5", "PRD §6", "Q-121"),
        note=_Q121,
        provisional=("Q-121",),
    )
    FIND_REQUEST_TRIES_PER_IP_PER_HOUR: int = rule(
        20,
        label="'Find my request' tries from one internet address in any rolling hour",
        unit="tries",
        sources=("PRD §7.3", "Q-121"),
        note=_Q121,
        provisional=("Q-121",),
    )
    INTAKE_MIN_FILL_TIME: timedelta = rule(
        timedelta(seconds=3),
        label="A form sent faster than this after it was opened is treated as a robot (the "
        "person sees the normal 'Check your email' page and nothing is sent)",
        sources=("PRD §6", "Q-121"),
        note=proposed(
            "Q-121",
            "Q-121 names a minimum fill time without a number; 3 seconds (architecture plan "
            "§9) is far below what any person needs to fill in the form.",
        ),
        provisional=("Q-121",),
    )


# --------------------------------------------------------------------------------------
# Media uploads and retention (PRD §45–§47)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MediaRules:
    REQUESTER_MEDIA_BATCH_MAX_PHOTOS: int = rule(
        10,
        label="Photos per requester upload batch (initial and each reopened batch)",
        unit="photos",
        sources=("PRD §45", "PRD §46"),
    )
    REQUESTER_MEDIA_BATCH_MAX_VIDEOS: int = rule(
        3,
        label="Videos per requester upload batch (initial and each reopened batch)",
        unit="videos",
        sources=("PRD §45", "PRD §46"),
    )
    REQUESTER_MEDIA_MAX_VIDEO_DURATION: timedelta = rule(
        timedelta(minutes=2),
        label="Longest video a requester may upload",
        sources=("PRD §45", "PRD §46"),
    )
    VIDEO_RETENTION_AFTER_CLOSE: timedelta = rule(
        timedelta(days=30),
        label="Project videos are deleted this long after the project is Completed or Rejected "
        "(unless approved for publication)",
        sources=("PRD §47.1", "PRD §47.4", "PRD §76"),
    )
    PHOTO_RETENTION_AFTER_CLOSE: timedelta = rule(
        timedelta(days=90),
        label="Project photos are deleted this long after the project is Completed or Rejected "
        "(unless approved for publication)",
        sources=("PRD §47.2", "PRD §47.4", "PRD §76"),
    )
    MEDIA_RETENTION_CLOCK_ON_CANCELLATION: bool = rule(
        True,
        label="Photos and videos of a Cancelled request or project are deleted on the same "
        "90-day / 30-day clock, counted from cancellation",
        sources=("PRD §47", "PRD §68", "Q-128"),
        note=proposed(
            "Q-128",
            "§47 names only Completed and Rejected; without this, media on a cancelled "
            "request would never be deleted.",
        ),
        provisional=("Q-128",),
    )
    REQUESTER_PHOTO_MAX_BYTES: int = rule(
        25 * 1024 * 1024,
        label="Largest photo file a requester may upload",
        unit="bytes",
        sources=("PRD §45", "PRD §69", "Q-119"),
        note=proposed(
            "Q-119",
            "Counted in binary megabytes (1 MB = 1,048,576 bytes), the generous reading, so a "
            "file a phone shows as 25 MB is never refused.",
        ),
        provisional=("Q-119",),
    )
    REQUESTER_VIDEO_MAX_BYTES: int = rule(
        500 * 1024 * 1024,
        label="Largest video file a requester may upload (still at most 2 minutes long)",
        unit="bytes",
        sources=("PRD §45", "PRD §69", "Q-119"),
        note=proposed("Q-119", "Binary megabytes, as for photos."),
        provisional=("Q-119",),
    )
    REQUESTER_PHOTO_TYPES: tuple[str, ...] = rule(
        ("image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"),
        label="Photo formats a requester may upload",
        sources=("PRD §45", "PRD §69", "Q-119"),
        note=proposed(
            "Q-119",
            "Types are detected from the file's content, not its name. HEIF is listed with "
            "HEIC because iPhones report either.",
        ),
        provisional=("Q-119",),
    )
    REQUESTER_VIDEO_TYPES: tuple[str, ...] = rule(
        ("video/mp4", "video/quicktime"),
        label="Video formats a requester may upload",
        sources=("PRD §45", "PRD §69", "Q-119"),
        note=proposed("Q-119", "MP4 and MOV (QuickTime)."),
        provisional=("Q-119",),
    )
    MEDIA_UPLOAD_INTENT_LIFETIME: timedelta = rule(
        timedelta(hours=1),
        label="An unconfirmed upload reservation (a slot taken but never completed) is "
        "released after",
        sources=("PRD §45",),
        note="Engineering value (architecture plan §9's rules table), not a Q-numbered open "
        "question.",
    )
    PRESIGNED_UPLOAD_URL_LIFETIME: timedelta = rule(
        timedelta(minutes=15),
        label="A presigned upload (PUT) URL handed to a requester's browser stays valid for",
        sources=("PRD §45", "PRD §69"),
        note="Engineering value (architecture plan §9's rules table), not a Q-numbered open "
        "question.",
    )
    PRESIGNED_VIEW_URL_LIFETIME: timedelta = rule(
        timedelta(seconds=60),
        label="A presigned view (GET) URL for a thumbnail/photo/video stays valid for",
        sources=("PRD §69",),
        note="Engineering value (architecture plan §9's rules table), not a Q-numbered open "
        "question.",
    )
    MEDIA_PROCESSING_TIMEOUT: timedelta = rule(
        timedelta(hours=1),
        label="An item stuck in 'processing' (the worker died mid-job) is treated as failed after",
        sources=("PRD §45",),
        note="Engineering value, fix-round M3 (security review): without this an item that "
        "never finishes processing holds its slot forever. Not a Q-numbered open question.",
    )


# --------------------------------------------------------------------------------------
# Record retention (PRD §41, §42, §56, §58)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RetentionRules:
    AUDIT_RETENTION: CalendarYears = rule(
        CalendarYears(1),
        label="Audit events are purged after",
        sources=("PRD §58", "Q-036"),
    )
    INCIDENT_RETENTION: CalendarYears = rule(
        CalendarYears(7),
        label="Incident reports and their amendments are kept for",
        sources=("PRD §56", "Q-074"),
        note=proposed("Q-074", "The 7 years count from the last amendment."),
        provisional=("Q-074",),
    )
    HOMEOWNER_AGREEMENT_RETENTION: CalendarYears = rule(
        CalendarYears(7),
        label="Signed homeowner service agreements are kept for",
        sources=("PRD §41", "Q-074"),
        note=proposed("Q-074", "The 7 years count from the later of signing and project close."),
        provisional=("Q-074",),
    )
    VOLUNTEER_AGREEMENT_RETENTION_AFTER_INACTIVE: CalendarYears = rule(
        CalendarYears(7),
        label="Volunteer agreement records are kept this long after the volunteer becomes inactive",
        sources=("PRD §42",),
    )
    REQUEST_RECORD_RETENTION_AFTER_CLOSE: CalendarYears = rule(
        CalendarYears(7),
        label="Requester name, email, phone and street address are kept this long after a "
        "request closes, then erased (ZIP code, category and outcome are kept for reports)",
        sources=("PRD §58", "PRD §68", "Q-127"),
    )
    SPAM_REQUEST_RETENTION: timedelta = rule(
        timedelta(days=90),
        label="A request closed as spam or a test is erased completely this long after it "
        "was closed",
        sources=("PRD §68", "Q-107", "Q-127"),
    )


# --------------------------------------------------------------------------------------
# Sign-in, MFA, step-up, sessions, impersonation (PRD §59, §60)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AuthRules:
    MFA_REQUIRED_ROLES: tuple[str, ...] = rule(
        ("ADMINISTRATOR", "HAM_DIRECTOR", "ASSISTANT_DIRECTOR", "PASTOR", "BOARD_REPRESENTATIVE"),
        label="Roles that must use two-step sign-in (authenticator app); the role's "
        "permissions start only after enrollment",
        sources=("PRD §60.1", "Q-045"),
    )
    MFA_TRUSTED_DEVICE_LIFETIME: timedelta = rule(
        timedelta(days=30),
        label="'Trust this device' skips the authenticator step for (unchecked by default)",
        sources=("PRD §60.1", "Q-010"),
    )
    MFA_RECOVERY_CODE_COUNT: int = rule(
        10,
        label="Recovery codes issued at enrollment or regeneration",
        unit="codes",
        sources=("PRD §60.1", "Q-035", "Q-044"),
    )
    STEP_UP_ACTIONS: tuple[tuple[str, str], ...] = rule(
        (
            ("role.grant_global", "role_change"),
            ("role.revoke_global", "role_change"),
            ("audit.export", "audit_export"),
            ("user.mfa_reset", "mfa_reset"),
            ("impersonation.start", "impersonation_start"),
            ("me.recovery_codes.regenerate", "recovery_codes_regenerate"),
            ("me.sign_in_email.change", "sign_in_email_change"),
        ),
        label="Actions that need a fresh authenticator code ('Confirm it's you'), as "
        "(action, step-up kind)",
        sources=("PRD §60.1", "Q-010", "Q-031", "Q-046", "Q-051", "Q-076"),
        note=proposed(
            "Q-076",
            "Grant and revoke share one kind ('role changes'), so one step-up covers both.",
        ),
        provisional=("Q-076",),
    )
    STEP_UP_WINDOW: timedelta = rule(
        timedelta(minutes=5),
        label="One step-up covers the same kind of action in the same session for",
        sources=("Q-010", "Q-031", "Q-046"),
    )
    SIGN_IN_CODE_LENGTH: int = rule(
        6,
        label="Digits in the emailed sign-in code",
        unit="digits",
        sources=("PRD §60.2", "foundation.md §2"),
    )
    SIGN_IN_CODE_LIFETIME: timedelta = rule(
        timedelta(minutes=15),
        label="Emailed sign-in code and link are valid for (single use)",
        sources=("PRD §60.2", "Q-032"),
    )
    SIGN_IN_CODE_MAX_ATTEMPTS: int = rule(
        5,
        label="Wrong code entries before the emailed code stops working",
        unit="tries",
        sources=("PRD §60.2", "Q-032"),
    )
    SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR: int = rule(
        5,
        label="Sign-in emails per email address in any rolling hour",
        unit="emails",
        sources=("PRD §60.2", "Q-070"),
        note=proposed("Q-070"),
        provisional=("Q-070",),
    )
    SIGN_IN_RESEND_COOLDOWN: timedelta = rule(
        timedelta(seconds=30),
        label="Wait before 'Resend email' is allowed",
        sources=("PRD §60.2", "Q-070"),
        note=proposed("Q-070"),
        provisional=("Q-070",),
    )
    SIGN_IN_REQUESTS_PER_IP_PER_HOUR: int = rule(
        20,
        label="Sign-in requests from any one IP address in any rolling hour (security "
        "review M3: a per-address limit alone doesn't stop one visitor from cycling "
        "through many addresses)",
        unit="requests",
        sources=("PRD §60.2", "Q-070"),
        note=proposed("Q-070"),
        provisional=("Q-070",),
    )
    SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY: int = rule(
        20,
        label="Wrong sign-in codes for one email address in any rolling 24 hours before "
        "every further attempt for that address is refused for the day (security review "
        "M3: on top of the 5-per-challenge limit, which a fresh challenge would otherwise "
        "reset)",
        unit="attempts",
        sources=("PRD §60.2", "Q-070"),
        note=proposed("Q-070"),
        provisional=("Q-070",),
    )
    ACCOUNT_INVITATION_LIFETIME: timedelta = rule(
        timedelta(days=7),
        label="An emailed HAM account invitation ('Join HAM') is valid for",
        sources=("Q-037", "Q-071", "Q-084"),
        note=proposed(
            "Q-071",
            "Not enforced yet: invitations currently reuse ordinary sign-in (PRD-GAP Q-084).",
        ),
        provisional=("Q-071",),
    )
    MFA_CODE_MAX_ATTEMPTS: int = rule(
        5,
        label="Wrong authenticator or recovery codes before the person must start again from "
        "a new email sign-in",
        unit="tries",
        sources=("PRD §60.1", "Q-072"),
        note=proposed("Q-072"),
        provisional=("Q-072",),
    )
    SESSION_IDLE_LIFETIME_STANDARD: timedelta = rule(
        timedelta(days=30),
        label="Sign-in lasts this long without activity (roles without two-step sign-in)",
        sources=("PRD §60.2", "Q-032"),
    )
    SESSION_IDLE_LIFETIME_MFA_ROLES: timedelta = rule(
        timedelta(hours=8),
        label="Sign-in ends after this long without activity (two-step sign-in roles)",
        sources=("PRD §60.1", "Q-032"),
    )
    SESSION_ABSOLUTE_LIFETIME_MFA_ROLES: timedelta = rule(
        timedelta(days=7),
        label="Sign-in always ends after this long (two-step sign-in roles)",
        sources=("PRD §60.1", "Q-032"),
    )
    IMPERSONATION_IDLE_TIMEOUT: timedelta = rule(
        timedelta(minutes=15),
        label="Troubleshooting as another user ends after this long without activity; the "
        "Administrator returns to their own account",
        sources=("PRD §59", "Q-053"),
    )
    SIGN_IN_CHALLENGE_RETENTION: timedelta = rule(
        timedelta(days=7),
        label="A used, expired or abandoned sign-in code/link row is purged after this long "
        "(security review L5: rows exist purely to rate-limit/lock out by address, not to be "
        "kept — a generous margin past the rolling per-day failed-attempt window)",
        sources=("PRD §60.2",),
    )


# --------------------------------------------------------------------------------------
# Public reporting (PRD §63, §68)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ReportingRules:
    PUBLIC_EMBED_MIN_GROUP_SIZE: int | Pending = rule(
        Pending("Q-027", "5; below it show 'Fewer than 5' and hide cost and satisfaction"),
        label="Public scoreboard hides any breakdown smaller than",
        unit="projects",
        sources=("PRD §63", "PRD §68", "Q-005", "Q-027"),
    )


# --------------------------------------------------------------------------------------
# Integration outbox (PRD §70.3; engineering values from the architecture plan)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OutboxRules:
    OUTBOX_MAX_ATTEMPTS: int = rule(
        8,
        label="Delivery attempts before an integration message is dead-lettered",
        unit="attempts",
        sources=("PRD §70.3", "foundation.md §5"),
    )
    OUTBOX_BACKOFF_INITIAL: timedelta = rule(
        timedelta(minutes=1),
        label="First retry delay (doubles each attempt)",
        sources=("PRD §70.3", "foundation.md §5"),
    )
    OUTBOX_BACKOFF_MAX: timedelta = rule(
        timedelta(hours=6),
        label="Longest retry delay",
        sources=("PRD §70.3", "foundation.md §5"),
    )
    JOB_PAYLOAD_ENCRYPTION_TTL: timedelta = rule(
        timedelta(days=1),
        label="An encrypted background-job payload (e.g. a queued transactional email) may "
        "be decrypted for",
        sources=("PRD §70.3", "foundation.md §5"),
        note="Defense in depth: bounds how long a payload stays decryptable if a "
        "`procrastinate_jobs` row (or a backup of it) is ever exfiltrated, on top of "
        "`HAM_FIELD_ENCRYPTION_KEY` rotation.",
    )


# --------------------------------------------------------------------------------------
# Operations and health (PRD §70.2, §78)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OperationsRules:
    HEALTH_MAX_QUEUE_LAG: timedelta = rule(
        timedelta(minutes=5),
        label="The health check reports 'degraded' when the oldest due background job has "
        "waited longer than",
        sources=("PRD §70.2", "PRD §78", "Q-056"),
        note=proposed(
            "Q-056",
            "A generous margin so a busy worker is not mistaken for a stuck one.",
        ),
        provisional=("Q-056",),
    )
    RECENT_ACTIVITY_WINDOW: timedelta = rule(
        timedelta(hours=24),
        label="The Administrator Home summary (e.g. recent sign-in failures) covers the last",
        sources=("PRD §70.2", "foundation.md §10"),
        note="Security review round 3, M9: was a bare `timedelta(hours=24)` literal in "
        "`ham.web.views._recent_sign_in_failures`.",
    )


# --------------------------------------------------------------------------------------
# The whole rule set
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Rules:
    staffing: StaffingRules = group(StaffingRules, label="Staffing, waitlist and reconfirmation")
    reliability: ReliabilityRules = group(ReliabilityRules, label="Reliability score")
    credentials: CredentialRules = group(CredentialRules, label="Licenses and certifications")
    attendance: AttendanceRules = group(AttendanceRules, label="Project day and attendance")
    requester_access: RequesterAccessRules = group(
        RequesterAccessRules, label="Requester links and completion survey"
    )
    intake: IntakeRules = group(IntakeRules, label="Public request form and requester codes")
    media: MediaRules = group(MediaRules, label="Media uploads and retention")
    retention: RetentionRules = group(RetentionRules, label="Record retention")
    auth: AuthRules = group(AuthRules, label="Sign-in and security")
    reporting: ReportingRules = group(ReportingRules, label="Public reporting")
    outbox: OutboxRules = group(OutboxRules, label="Integrations")
    operations: OperationsRules = group(OperationsRules, label="Operations and health")


RULES = Rules()


# --------------------------------------------------------------------------------------
# Pure helpers over the values
# --------------------------------------------------------------------------------------
CANCELLATION_BAND_CODES = ("free", "days_4_to_6", "days_2_to_3", "day_1", "same_day")


def cancellation_band(days_before: int, rules: Rules = RULES) -> str:
    """Classify a cancellation by whole days before the project (§33, §34.1).

    ``days_before`` is the already-measured whole number of days (0 = same day). How it is
    measured from clock times is PRD-GAP Q-073 and belongs to the staffing module.
    A negative value (after the project day) is not a cancellation and raises.
    """
    if isinstance(days_before, bool) or not isinstance(days_before, int):
        raise TypeError("days_before must be an int")
    if days_before < 0:
        raise ValueError("days_before < 0 is not a cancellation (see no-show rules)")
    bounds = rules.reliability.CANCELLATION_BAND_LOWER_BOUNDS_DAYS
    for code, lower in zip(CANCELLATION_BAND_CODES, bounds, strict=True):
        if days_before >= lower:
            return code
    raise AssertionError("unreachable: last band has lower bound 0")  # pragma: no cover


MEDIA_KINDS = ("photo", "video")
# Statuses whose entry starts the §47 media clock. COMPLETED and REJECTED come from §47;
# CANCELLED from Q-128. Anything else (e.g. NOT_EXECUTABLE) has no decided clock yet and
# is refused rather than guessed.
MEDIA_RETENTION_CLOSING_STATUSES = ("COMPLETED", "REJECTED", "CANCELLED")


def media_retention_period(
    media_kind: str, closing_status: str, rules: Rules = RULES
) -> timedelta | None:
    """How long after ``closing_status`` was entered a photo/video is deleted (§47, Q-128).

    Returns ``None`` when no deletion clock applies (only possible for CANCELLED if the
    Q-128 rule is ever switched off). The §47.4 publication exception is per item and is the
    caller's job. Raises ``ValueError`` for an unknown kind or a status without a rule.
    """
    m = rules.media
    if media_kind not in MEDIA_KINDS:
        raise ValueError(f"unknown media kind {media_kind!r}")
    if closing_status not in MEDIA_RETENTION_CLOSING_STATUSES:
        raise ValueError(f"no media retention rule for status {closing_status!r}")
    if closing_status == "CANCELLED" and not m.MEDIA_RETENTION_CLOCK_ON_CANCELLATION:
        return None
    return m.PHOTO_RETENTION_AFTER_CLOSE if media_kind == "photo" else m.VIDEO_RETENTION_AFTER_CLOSE


def check_reliability_penalties(
    *,
    days_4_to_6: int,
    days_2_to_3: int,
    day_1: int,
    same_day: int,
    no_show: int,
    recovery: int,
    score_max: int = 100,
) -> tuple[str, ...]:
    """Problems with a candidate set of Q-001 numbers, or ``()`` if it satisfies the PRD.

    PRD §33/§34.1: penalty increases as the project approaches; same-day is substantial but
    slightly less than a no-show; no-show is the largest; the score recovers gradually.
    """
    problems: list[str] = []
    ladder = [
        ("4-6 days", days_4_to_6),
        ("2-3 days", days_2_to_3),
        ("1 day", day_1),
        ("same day", same_day),
        ("no-show", no_show),
    ]
    for name, value in ladder:
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{name}: penalty must be an int")
        elif not 0 < value <= score_max:
            problems.append(f"{name}: penalty must be between 1 and {score_max}")
    if problems:
        return tuple(problems)
    for (lo_name, lo), (hi_name, hi) in zip(ladder, ladder[1:], strict=False):
        if not lo < hi:
            problems.append(f"{lo_name} ({lo}) must be less than {hi_name} ({hi})")
    if isinstance(recovery, bool) or not isinstance(recovery, int) or not 0 < recovery:
        problems.append("recovery must be a positive int")
    elif recovery >= no_show:
        problems.append("recovery must be gradual: less than the no-show penalty")
    return tuple(problems)


def check_invariants(rules: Rules = RULES) -> tuple[str, ...]:
    """Cross-rule consistency checks. Returns problems; ``()`` means consistent.

    Still-``Pending`` values (Q-027) are not checked; add a check when one is decided.
    """
    p: list[str] = []
    s, r, a = rules.staffing, rules.reliability, rules.auth

    if not s.RECONFIRMATION_DAYS_BEFORE > s.UNCONFIRMED_RELEASE_DAYS_BEFORE:
        p.append("reconfirmation must start before the release day")
    reminders = s.RECONFIRMATION_REMINDER_DAYS_BEFORE
    if list(reminders) != sorted(set(reminders), reverse=True):
        p.append("reconfirmation reminder days must be distinct and descending")
    if reminders and not (
        reminders[0] <= s.RECONFIRMATION_DAYS_BEFORE
        and reminders[-1] >= s.UNCONFIRMED_RELEASE_DAYS_BEFORE
    ):
        p.append("reconfirmation reminders must fall between reconfirmation and release")
    if not s.UNDERSTAFFED_ALERT_BEFORE_START > s.AUTO_STAFFING_CUTOFF_BEFORE_START:
        p.append("understaffed alert must come before the 48-hour cutoff")
    if (
        not s.UNCONFIRMED_RELEASE_DAYS_BEFORE * timedelta(days=1)
        - (s.WAITLIST_PROMOTION_CONFIRM_WINDOW)
        > s.AUTO_STAFFING_CUTOFF_BEFORE_START
    ):
        p.append("a slot released at day 5 must be confirmable before the 48-hour cutoff")

    if not r.SCORE_MIN <= r.INITIAL_SCORE <= r.SCORE_MAX:
        p.append("initial score must be within the score range")
    bounds = r.CANCELLATION_BAND_LOWER_BOUNDS_DAYS
    if list(bounds) != sorted(set(bounds), reverse=True) or bounds[-1] != 0:
        p.append("cancellation band bounds must be distinct, descending and end at 0")
    if len(bounds) != len(CANCELLATION_BAND_CODES):
        p.append("one band code per band bound")
    if bounds and bounds[0] != r.CANCELLATION_FREE_DAYS_BEFORE:
        p.append("first band must start at the free-cancellation threshold")
    for name in (
        "PENALTY_CANCEL_7_PLUS_DAYS",
        "PENALTY_EXCUSED",
        "PENALTY_DEACTIVATION_AUTO_CANCEL",
        "PENALTY_DECLINE_LAST_MINUTE_ASSIGNMENT",
    ):
        if getattr(r, name) != 0:
            p.append(f"{name} must be 0 (PRD §21/§30/§33/§34.1)")
    p.extend(
        check_reliability_penalties(
            days_4_to_6=r.PENALTY_CANCEL_4_TO_6_DAYS,
            days_2_to_3=r.PENALTY_CANCEL_2_TO_3_DAYS,
            day_1=r.PENALTY_CANCEL_1_DAY,
            same_day=r.PENALTY_CANCEL_SAME_DAY,
            no_show=r.PENALTY_NO_SHOW,
            recovery=r.RECOVERY_PER_FULFILLED_COMMITMENT,
            score_max=r.SCORE_MAX,
        )
    )

    alerts = rules.credentials.CREDENTIAL_EXPIRY_ALERT_DAYS
    if list(alerts) != sorted(set(alerts), reverse=True) or min(alerts) <= 0:
        p.append("credential alert days must be distinct, descending and positive")

    ra = rules.requester_access
    if not ra.SURVEY_REMINDER_AFTER_COMPLETION < ra.SURVEY_LINK_LIFETIME:
        p.append("survey reminder must be sent before the survey link expires")
    if not ra.SURVEY_RATING_MIN < ra.SURVEY_RATING_MAX:
        p.append("survey rating range is empty")

    if not a.SESSION_IDLE_LIFETIME_MFA_ROLES < a.SESSION_ABSOLUTE_LIFETIME_MFA_ROLES:
        p.append("MFA idle lifetime must be shorter than the absolute lifetime")
    actions = [action for action, _kind in a.STEP_UP_ACTIONS]
    if len(actions) != len(set(actions)):
        p.append("step-up actions must be unique")
    if len(set(a.MFA_REQUIRED_ROLES)) != len(a.MFA_REQUIRED_ROLES):
        p.append("MFA roles must be unique")

    if not timedelta(0) < a.SIGN_IN_RESEND_COOLDOWN < timedelta(hours=1):
        p.append("sign-in resend cooldown must be positive and shorter than the hourly window")
    for name in (
        "SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR",
        "MFA_CODE_MAX_ATTEMPTS",
        "SIGN_IN_REQUESTS_PER_IP_PER_HOUR",
        "SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY",
    ):
        if getattr(a, name) < 1:
            p.append(f"{name} must be at least 1")
    if not a.ACCOUNT_INVITATION_LIFETIME > a.SIGN_IN_CODE_LIFETIME:
        p.append("an account invitation must outlive a single sign-in code")

    it = rules.intake
    if not ra.REQUESTER_ACCESS_AFTER_CLOSE > timedelta(0):
        p.append("requester access after close must be positive")
    if not it.INTAKE_DRAFT_LIFETIME > it.REQUESTER_CODE_LIFETIME:
        p.append("an unfinished form must outlive the requester code sent for it")
    if not timedelta(0) < it.REQUESTER_CODE_RESEND_COOLDOWN < timedelta(hours=1):
        p.append("requester resend cooldown must be positive and shorter than the hourly window")
    if not timedelta(0) < it.INTAKE_MIN_FILL_TIME < it.INTAKE_DRAFT_LIFETIME:
        p.append("minimum fill time must be positive and shorter than the draft lifetime")
    for name in (
        "REQUESTER_CODE_LENGTH",
        "REQUESTER_CODE_MAX_ATTEMPTS",
        "REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR",
        "INTAKE_FORMS_PER_IP_PER_HOUR",
        "INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY",
        "FIND_REQUEST_TRIES_PER_IP_PER_HOUR",
    ):
        if getattr(it, name) < 1:
            p.append(f"{name} must be at least 1")
    if not it.REQUESTER_CODE_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY >= it.REQUESTER_CODE_MAX_ATTEMPTS:
        p.append("the daily wrong-code cap must allow at least one full code's tries")
    if not it.REQUESTER_CHALLENGE_RETENTION > timedelta(days=1):
        p.append("requester code records must outlive the rolling 24-hour wrong-code window")

    m = rules.media
    if not 0 < m.REQUESTER_PHOTO_MAX_BYTES <= m.REQUESTER_VIDEO_MAX_BYTES:
        p.append("upload size limits must be positive, photos no larger than videos")
    if not timedelta(0) < m.PRESIGNED_UPLOAD_URL_LIFETIME <= m.MEDIA_UPLOAD_INTENT_LIFETIME:
        p.append("presigned upload URL must not outlive the reservation it belongs to")
    if not timedelta(0) < m.PRESIGNED_VIEW_URL_LIFETIME:
        p.append("presigned view URL lifetime must be positive")
    if not timedelta(0) < m.MEDIA_PROCESSING_TIMEOUT:
        p.append("media processing timeout must be positive")
    for name, prefix in (("REQUESTER_PHOTO_TYPES", "image/"), ("REQUESTER_VIDEO_TYPES", "video/")):
        types = getattr(m, name)
        if not types or len(set(types)) != len(types):
            p.append(f"{name} must be non-empty and unique")
        if any(not t.startswith(prefix) or t != t.lower() for t in types):
            p.append(f"{name} must be lower-case {prefix}* media types")
    if not timedelta(0) < rules.retention.SPAM_REQUEST_RETENTION:
        p.append("spam retention must be positive")
    if not rules.retention.REQUEST_RECORD_RETENTION_AFTER_CLOSE.years >= 1:
        p.append("request record retention must be at least a year")

    o = rules.outbox
    if not (o.OUTBOX_MAX_ATTEMPTS >= 1 and o.OUTBOX_BACKOFF_INITIAL <= o.OUTBOX_BACKOFF_MAX):
        p.append("outbox retry settings are inconsistent")
    if not rules.operations.HEALTH_MAX_QUEUE_LAG > timedelta(0):
        p.append("health queue-lag threshold must be positive")
    return tuple(p)


def iter_rules(rules: Rules = RULES) -> Any:
    """Yield ``(group_field, rule_field, value)`` in declaration order."""
    for gf in fields(rules):
        grp = getattr(rules, gf.name)
        for rf in fields(grp):
            yield gf, rf, getattr(grp, rf.name)


_problems = check_invariants(RULES)
if _problems:  # pragma: no cover - guarded by tests; fail fast rather than run wrong rules
    raise RuntimeError("HAM rules are inconsistent: " + "; ".join(_problems))
