"""PRD §77 "Core Acceptance Criteria" harness skeleton (foundation.md §9.8).

V1 is not production-ready until all 30 steps of the end-to-end scenario in
`docs/HAM_PRD_V1.md` §77 pass together, in order, against one running system. This module is
that harness: as each step's feature slice lands, replace its placeholder body with a real
assertion (still calling through `client`/`live_server`/fixtures below, not a shortcut), and
flip its status in the CHECKLIST comment. Never delete a step or renumber -- the PRD's
numbering is the source of truth and other docs (agent memory, ADRs) may reference "§77 step
N".

CHECKLIST (update alongside the PRD trace table each time a step is implemented):
    1.  pending  -- requests: public intake form                  (needs: requests module)
    2.  pending  -- requester_portal: email/mobile verification    (needs: requester_portal)
    3.  pending  -- requests: submit with photos/video             (needs: requests, media)
    4.  pending  -- requests: pastor/Board approval route          (needs: requests)
    5.  pending  -- projects: site assessment scheduling+complete  (needs: projects)
    6.  pending  -- projects: assessment captures skills/tools/... (needs: projects)
    7.  pending  -- projects: Director approves/refines scope      (needs: projects)
    8.  pending  -- ai: draft plan                                 (needs: ai, projects)
    9.  pending  -- projects/tasks: leadership accepts tasks+budget(needs: tasks, finance)
    10. pending  -- staffing: identifies qualified volunteers      (needs: staffing, volunteers)
    11. pending  -- staffing: automatic invitations                (needs: staffing)
    12. pending  -- staffing: first-come/first-served acceptance   (needs: staffing)
    13. pending  -- staffing: waitlist for excess qualified        (needs: staffing)
    14. pending  -- staffing: 7-day reconfirmation                 (needs: staffing)
    15. pending  -- staffing: staffing-gap handling                (needs: staffing)
    16. pending  -- integrations: privacy-conscious calendar event (needs: calendar adapter)
    17. pending  -- attendance: Project Leader safety checklist    (needs: attendance)
    18. pending  -- attendance: QR/GPS check-in                   (needs: attendance)
    19. pending  -- tasks: execution progression                  (needs: tasks)
    20. pending  -- attendance: hours captured                     (needs: attendance)
    21. pending  -- tasks: unexpected work documented safely       (needs: tasks)
    22. pending  -- incidents: workflow                            (needs: incidents)
    23. pending  -- projects: completion + follow-up tasks         (needs: projects, tasks)
    24. pending  -- projects: final follow-up auto-closes project  (needs: projects, tasks, jobs)
    25. pending  -- requester_portal: immediate survey              (needs: requester_portal)
    26. pending  -- feedback: private volunteer feedback capture   (needs: feedback)
    27. pending  -- reporting: scorecard updates                   (needs: reporting)
    28. **covered by tests/authz + tests/audit (this step 1 slice)** -- audit records every
        consequential actor (foundation.md §9.2's command-registry/audit-coverage tests are
        the ongoing proof for this step; no separate §77 placeholder needed once a real
        request/project exists, since this step's *claim* is already continuously tested)
    29. pending  -- ai: post-project report                        (needs: ai, reporting)
    30. pending  -- privacy: no unauthorized exposure end-to-end   (needs: all of the above;
        this step re-checks §68 threading through every module, not just step 1's slice --
        see tests/web/test_no_hardcoded_church_or_colors.py and tests/audit/* for the pieces
        already enforced generically)

None of steps 1-27, 29 have a built feature yet (build-order step 1 is skeleton/roles/
permissions/audit/outbox/auth only, per CLAUDE.md's Deferred/Scope). They are `pytest.skip`
placeholders, not `xfail`, because there is no code to fail against yet -- `xfail` is for a
built feature behaving wrongly (see `tests/web/test_audit_export_stepup_redirect_bug.py` for
that pattern), not for an unbuilt one.
"""

from __future__ import annotations

import datetime as dt

import pytest

from ham.platform.clock import FixedClock, set_clock

# A fixed "project day" instant so every step that reasons about "N days/hours before" can
# share one anchor once real projects exist (Q-030: church-local time zone, America/New_York).
PROJECT_START = dt.datetime(2026, 11, 14, 14, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock():
    """A controllable Clock, already set to `PROJECT_START` minus two weeks so a step can
    `clock.advance(...)`/`clock.set(...)` to walk forward through reconfirmation/release/
    cutoff boundaries (RECONFIRMATION_DAYS_BEFORE, UNCONFIRMED_RELEASE_DAYS_BEFORE, etc. --
    `ham/rules/`) without depending on wall-clock time."""
    fixed = FixedClock(PROJECT_START - dt.timedelta(days=14))
    set_clock(fixed)
    yield fixed
    set_clock(fixed)  # tests/conftest.py's autouse fixture restores SystemClock after the test


@pytest.fixture
def mailbox():
    """The captured mailbox (locmem backend, `django.core.mail.outbox`), cleared per test so
    step assertions ("the requester got a survey email") aren't polluted by earlier steps'
    mail. Run `ham.jobs.run_due_jobs_now()` after triggering a send -- it is deferred, not
    synchronous (see `ham.integrations.email.service.send_transactional_email`)."""
    from django.core import mail

    mail.outbox = []
    yield mail.outbox
    mail.outbox = []


@pytest.fixture
def run_due_jobs_now():
    """Runs every currently-due background job in-process (no worker needed) -- reminders,
    waitlist promotion, retention, calendar sync, the final-follow-up auto-close (step 24),
    etc. all go through this once their jobs exist."""
    from ham.jobs import run_due_jobs_now as _run

    return _run


@pytest.fixture
def fake_calendar():
    """A fake Google Calendar adapter recording every event it was asked to create/update, so
    step 16 can assert the payload never carries requester name/address/circumstances (§51.1,
    §68) without a real Google API call. Placeholder until `ham.integrations.calendar` exists
    (foundation.md module boundaries: step 1 only ships stub subscribers)."""
    events: list[dict] = []

    class _FakeCalendar:
        def create_event(self, **kwargs):
            events.append(kwargs)
            return {"id": f"fake-event-{len(events)}"}

        @property
        def created(self):
            return events

    return _FakeCalendar()


pytestmark = pytest.mark.django_db


def _pending(step: int, text: str, needs: str) -> None:
    pytest.skip(f"§77 step {step} ({needs}): {text}")


class TestAcceptance77:
    """One test per PRD §77 step, in order. `test_NN_...` names sort correctly."""

    def test_01_public_intake_form(self):
        _pending(1, "A non-member requester opens the public form.", "requests")

    def test_02_requester_verifies_contact(self):
        _pending(2, "Requester verifies email or mobile.", "requester_portal")

    def test_03_submit_with_media(self):
        _pending(
            3,
            "Requester submits a legitimate assistance request with photos/video.",
            "requests, media",
        )

    def test_04_pastor_or_board_approves(self):
        _pending(4, "A pastor or Board route approves it.", "requests")

    def test_05_site_assessment_scheduled_and_completed(self):
        _pending(5, "HAM schedules and completes mandatory site assessment.", "projects")

    def test_06_assessment_identifies_scope(self):
        _pending(
            6,
            "Assessment identifies skills, tools, materials, safety, cost, and scope.",
            "projects",
        )

    def test_07_director_approves_scope(self):
        _pending(7, "HAM Director approves/refines scope.", "projects (Q-054: not the AD/Admin)")

    def test_08_ai_prepares_draft_plan(self):
        _pending(8, "AI prepares a draft plan.", "ai, projects")

    def test_09_leadership_accepts_tasks_and_budget(self):
        _pending(9, "Leadership accepts/modifies tasks and budget.", "tasks, finance")

    def test_10_identifies_qualified_volunteers(self):
        _pending(10, "System identifies qualified volunteers.", "staffing, volunteers")

    def test_11_invitations_sent_automatically(self):
        _pending(11, "Invitations are sent automatically.", "staffing")

    def test_12_first_come_first_served_acceptance(self):
        _pending(12, "Volunteers accept first-come/first-served.", "staffing")

    def test_13_excess_volunteers_waitlisted(self):
        _pending(13, "Excess qualified volunteers enter waitlist.", "staffing")

    def test_14_reconfirmation_seven_days_before(self):
        _pending(14, "Volunteer reconfirmation occurs seven days before service.", "staffing")

    def test_15_staffing_gaps_handled(self):
        _pending(15, "Staffing gaps are handled correctly.", "staffing")

    def test_16_calendar_event_is_privacy_conscious(self, fake_calendar):
        _pending(
            16,
            "Leadership calendar receives privacy-conscious project event.",
            "integrations.calendar adapter",
        )

    def test_17_safety_checklist_completed(self):
        _pending(17, "Project Leader completes short safety checklist.", "attendance")

    def test_18_qr_or_location_checkin(self):
        _pending(18, "Volunteers check in by QR and/or location.", "attendance")

    def test_19_tasks_progress_through_execution(self):
        _pending(19, "Tasks progress through execution.", "tasks")

    def test_20_attendance_hours_captured(self):
        _pending(20, "Attendance/service hours are captured.", "attendance")

    def test_21_unexpected_work_documented_safely(self):
        _pending(21, "Unexpected work can be documented safely.", "tasks")

    def test_22_incident_workflow(self):
        _pending(22, "Incident workflow works if required.", "incidents")

    def test_23_project_completes_with_followup_tasks(self):
        _pending(23, "Project can complete with follow-up tasks.", "projects, tasks")

    def test_24_final_followup_autocloses_project(self, run_due_jobs_now):
        _pending(
            24, "Final follow-up completion automatically closes project.", "projects, tasks, jobs"
        )

    def test_25_requester_receives_survey_immediately(self, mailbox, run_due_jobs_now):
        _pending(25, "Requester immediately receives survey.", "requester_portal")

    def test_26_volunteer_feedback_captured_privately(self):
        _pending(26, "Volunteer feedback is privately captured.", "feedback")

    def test_27_scorecard_updates(self):
        _pending(
            27,
            "Balanced scorecard updates families served and volunteer hours.",
            "reporting",
        )

    def test_28_audit_records_every_consequential_actor(self):
        """Already continuously proven for step 1's own actions (no requests/projects exist
        yet to attach this claim to): see tests/authz/test_commands.py, tests/authz/
        test_expected_matrix.py and tests/audit/test_command_registry.py. This step's own
        placeholder becomes a real project-scoped assertion once requests/projects exist --
        it should NOT simply be marked "done"; it needs its own request/project-level
        AuditEvent check alongside every module landing above."""
        pytest.skip(
            "§77 step 28 (requests, projects, ...): generically covered for step 1's own "
            "actions by tests/authz + tests/audit; needs a request/project-scoped assertion "
            "once those modules exist"
        )

    def test_29_ai_generates_post_project_report(self):
        _pending(29, "AI generates post-project report.", "ai, reporting")

    def test_30_privacy_restrictions_hold_end_to_end(self):
        _pending(
            30,
            "Privacy restrictions prevent unauthorized exposure throughout.",
            "all modules (partially covered generically today; see module docstring)",
        )
