"""PRD §77 "Core Acceptance Criteria" harness skeleton (foundation.md §9.8).

V1 is not production-ready until all 30 steps of the end-to-end scenario in
`docs/HAM_PRD_V1.md` §77 pass together, in order, against one running system. This module is
that harness: as each step's feature slice lands, replace its placeholder body with a real
assertion (still calling through `client`/`live_server`/fixtures below, not a shortcut), and
flip its status in the CHECKLIST comment. Never delete a step or renumber -- the PRD's
numbering is the source of truth and other docs (agent memory, ADRs) may reference "§77 step
N".

CHECKLIST (update alongside the PRD trace table each time a step is implemented):
    1.  done     -- requests: public intake form                  (step 2 (Intake) slice)
    2.  done     -- requester_portal: email verification           (step 2 (Intake) slice;
        mobile/SMS verification is out of V1 scope, Q-019 decided: email codes only)
    3.  done     -- requests: submit with photos/video             (step 2 (Intake) slice;
        photo fully processed; video degrades to "processing_unavailable" in this sandbox,
        which has no ffmpeg/ffprobe installed -- see tests/media/test_processing.py)
    4.  done     -- requests: pastor/Board approval route          (real HTTP POSTs through
        `request_approve`: pastoral route, Board route, and the urgent "Certify and approve"
        one-step path; asserts the immediate, never-held `RequestUrgentApproval` alert to
        Director/AD is PII-free and the held `RequestApproved` effects only release at
        `effective_at`, approvals.md/approvals-contracts.md §4, Q-153/Q-160/Q-161/Q-176)
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
    28. done     -- audit records every consequential actor         (generic proof:
        tests/authz + tests/audit, unchanged since step 1; PLUS, now that step 2 (Intake)
        gives it a real request to attach to, a request-scoped assertion in this file:
        actor+UTC time on every request.* AuditEvent, no PII in before/after/context/reason,
        and project_id = request id from intake onward. PLUS (step 3, Approvals): the
        decision actors themselves -- a real pastoral `request.approve`/`request.reject`
        HTTP POST each get their own `request.approved`/`request.rejected` AuditEvent with
        `actor_user_id` = the deciding pastor and no PII, including the rejection's own kind
        message (Q-050). Extend again, don't just mark done again, once step 4 (projects)
        adds a real Project row.)
    29. pending  -- ai: post-project report                        (needs: ai, reporting)
    30. pending  -- privacy: no unauthorized exposure end-to-end   (needs: all of the above;
        this step re-checks §68 threading through every module, not just step 1's slice --
        see tests/web/test_no_hardcoded_church_or_colors.py and tests/audit/* for the pieces
        already enforced generically)

Steps 1-3 (step 2 (Intake): the public form, email verification, submit-with-media) are now
real, live-through-the-HTTP-client assertions -- not shortcuts into the service layer -- so
they exercise the same request/response cycle a browser would. None of steps 4-27, 29 have a
built feature yet (later build-order steps). They stay `pytest.skip` placeholders, not
`xfail`, because there is no code to fail against yet -- `xfail` is for a built feature
behaving wrongly (see `tests/web/test_audit_export_stepup_redirect_bug.py` for that pattern),
not for an unbuilt one.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.core import mail

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


# ------------------------------------------------------------------------------------------
# Steps 1-3 (step 2 (Intake)): a distinctive, seeded requester identity so step 28's
# PII-in-audit assertion has something unambiguous to search for (never a value that could
# innocently appear elsewhere, e.g. "Smith" or "Main St").
# ------------------------------------------------------------------------------------------
DISTINCTIVE_NAME = "Fenwick Okonkwo-Baptiste"
DISTINCTIVE_STREET = "7731 Windmere Cypress Trail"
DISTINCTIVE_PHONE = "(305) 555-0199"
DISTINCTIVE_EMAIL = "fenwick.ob@example.org"


@pytest.fixture(autouse=True)
def _real_portal_lookups(real_portal_lookups):
    """Shared fixture (`tests/conftest.py::real_portal_lookups`): registers the real
    `ham.requester_portal.services` lookups needed by steps 1-3's actual view/service calls."""


@pytest.fixture
def local_storage(tmp_path, settings):
    settings.HAM_LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.HAM_OBJECT_STORE_BACKEND = "ham.integrations.storage.local.LocalObjectStore"
    return tmp_path


def _step_payload(**overrides) -> dict:
    """Mirrors `tests/web/test_requester_portal_screens.py::_step_payload`, but with the
    distinctive identity above instead of that file's "Doris Palmer" so this module's own
    PII-leak assertions (step 28/30) can't accidentally pass against a stray match left by a
    different test file's fixtures."""
    steps = {
        "need": {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        "home": {
            "relationship_to_property": "owner",
            "line1": DISTINCTIVE_STREET,
            "city": "Miami",
            "state": "FL",
            "postal_code": "33125",
            "property_type": "house",
        },
        "safety": {"hazards": ["none_known"]},
        "reaching-you": {
            "full_name": DISTINCTIVE_NAME,
            "phone": DISTINCTIVE_PHONE,
            "email": DISTINCTIVE_EMAIL,
            "contact_preference": "email",
            "availability": ["any_time"],
        },
    }
    steps.update(overrides)
    return steps


def _backdate_form_opened_at(client) -> None:
    """See `tests/web/test_requester_portal_screens.py`'s identical helper: the anti-abuse
    min-fill-time check is keyed off session state, not real elapsed wall-clock time."""
    import datetime as dt

    from ham.platform.clock import now as clock_now
    from ham.requester_portal import antiabuse
    from ham.rules import RULES
    from ham.web.views_requester import _SESSION_FORM_OPENED_AT

    opened_at = clock_now() - RULES.intake.INTAKE_MIN_FILL_TIME - dt.timedelta(seconds=1)
    session = client.session
    session[_SESSION_FORM_OPENED_AT] = antiabuse.sign_form_opened_at(now=opened_at)
    session.save()


def _fill_and_submit_form(client, *, reaching_you_overrides: dict | None = None) -> None:
    """Steps R1-R6 of the public wizard, ending on the review step ready to submit -- the
    shared setup for both step 1 (opening the form) and step 2/3 (verifying + submitting)."""
    from django.urls import reverse

    resp = client.get(reverse("web:request_help_start"))
    assert resp.status_code == 200
    resp = client.post(reverse("web:request_help_begin"), follow=True)
    assert resp.status_code == 200
    assert resp.redirect_chain[-1][0] == reverse("web:request_help_step", kwargs={"step": "need"})
    _backdate_form_opened_at(client)

    steps = _step_payload()
    if reaching_you_overrides:
        steps["reaching-you"] = {**steps["reaching-you"], **reaching_you_overrides}
    for step_name in ("need", "home", "safety", "reaching-you"):
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": step_name}),
            steps[step_name],
            follow=True,
        )
        assert resp.status_code == 200, resp.content


class TestAcceptance77:
    """One test per PRD §77 step, in order. `test_NN_...` names sort correctly."""

    def test_01_public_intake_form(self, client):
        """PRD §77 step 1: "A non-member requester opens the public form." No account, no
        sign-in -- every screen here is a `PUBLIC_ROUTES` entry
        (`ham/web/views_requester.py` module docstring)."""
        from django.urls import reverse

        resp = client.get(reverse("web:request_help_start"))
        assert resp.status_code == 200
        assert b"Ask for help with your home" in resp.content

        _fill_and_submit_form(client)

        # The review step renders back everything just entered, ready to send -- still no
        # account/session identity beyond the plain Django session used to carry draft state.
        resp = client.get(reverse("web:request_help_step", kwargs={"step": "review"}))
        assert resp.status_code == 200
        assert b"Send request" in resp.content

    def test_02_requester_verifies_contact(self, client, mailbox, run_due_jobs_now):
        """PRD §77 step 2: "Requester verifies email or mobile." (Q-019, decided: email
        codes only in V1 -- mobile/SMS verification is out of scope; see the CHECKLIST
        note.) Submitting the review step sends a 6-digit email code; only the *correct*
        code moves the requester on to their secure page."""
        from django.urls import reverse

        _fill_and_submit_form(client)

        mail.outbox.clear()
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        assert resp.status_code == 200, resp.content
        assert resp.redirect_chain[-1][0] == reverse("web:request_help_verify")
        run_due_jobs_now()
        assert len(mail.outbox) == 1
        # §68/§63: the code email itself never carries the requester's own PII back at them
        # in a way that would leak into e.g. a shared inbox preview -- a neutral subject.
        assert DISTINCTIVE_NAME not in mail.outbox[0].subject
        assert DISTINCTIVE_STREET not in mail.outbox[0].subject

        from ham.platform import otp
        from ham.requester_portal.models import RequesterVerificationChallenge

        challenge = RequesterVerificationChallenge.objects.get(
            purpose="intake", email_key=otp.hash_value(DISTINCTIVE_EMAIL)
        )

        # A wrong code is refused and the requester stays on the verify screen (answers are
        # not lost -- Q-100: "answers survive errors").
        wrong_resp = client.post(
            reverse("web:request_help_verify"), {"code": "000000"}, follow=True
        )
        assert wrong_resp.status_code == 422  # re-rendered verify screen, not a redirect
        assert b"HAM #" not in wrong_resp.content

        challenge.code_hash = otp.hash_value("246810")
        challenge.save(update_fields=["code_hash"])
        resp = client.post(reverse("web:request_help_verify"), {"code": "246810"}, follow=True)
        assert resp.status_code == 200, resp.content
        secure_url = resp.redirect_chain[-1][0]
        assert secure_url.startswith("/request-help/r/")
        assert b"HAM #" in resp.content
        # The request only reaches leaders after this step (Q-100 "verify before submit"):
        from ham.requests.models import AssistanceRequest
        from ham.requests.states import RequestStatus

        request = AssistanceRequest.objects.get(requester__email=DISTINCTIVE_EMAIL)
        assert request.status == RequestStatus.SUBMITTED.value

    def test_03_submit_with_media(self, client, mailbox, run_due_jobs_now, local_storage):
        """PRD §77 step 3: "Requester submits a legitimate assistance request with photos/
        video." Exercises R9 (reserve/PUT/complete) for one photo and one video through the
        real object-store + processing pipeline. This sandbox has no ffmpeg/ffprobe
        installed (see `tests/media/test_processing.py`'s module docstring), so the video
        item degrades to `processing_unavailable` rather than `ready` -- asserted precisely,
        not skipped, since that is the correct, safe behaviour for this environment (Q-120:
        never serve an unprocessed original). Also covers the automatic duplicate check
        (§9/Q-115) that runs right after submission: a second request sharing this one's
        phone number gets flagged against it."""
        import json

        from django.urls import reverse

        from ham.media.models import (
            FAILURE_PROCESSING_UNAVAILABLE,
            STATUS_READY,
            STATUS_REJECTED,
            RequestMedia,
        )
        from ham.platform import otp
        from ham.requester_portal.models import RequesterVerificationChallenge
        from ham.requests.models import AssistanceRequest, RequestMatch
        from ham.requests.states import RequestStatus

        _fill_and_submit_form(client)
        mail.outbox.clear()
        client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        run_due_jobs_now()
        challenge = RequesterVerificationChallenge.objects.get(
            purpose="intake", email_key=otp.hash_value(DISTINCTIVE_EMAIL)
        )
        challenge.code_hash = otp.hash_value("135791")
        challenge.save(update_fields=["code_hash"])
        resp = client.post(reverse("web:request_help_verify"), {"code": "135791"}, follow=True)
        secure_url = resp.redirect_chain[-1][0]
        token = secure_url.split("/request-help/r/")[1].split("?")[0]

        # Drains the duplicate-check job `submit_request` deferred for *this* request before
        # its own media reservation, so a later `run_due_jobs_now()` in this same test can't
        # accidentally double-process it.
        run_due_jobs_now()
        request = AssistanceRequest.objects.get(requester__email=DISTINCTIVE_EMAIL)
        assert request.status == RequestStatus.AWAITING_APPROVAL.value

        def _reserve_upload(media_kind: str, content_type: str, data: bytes) -> dict:
            reserve_resp = client.post(
                reverse("web:request_help_media_reserve", kwargs={"token": token}),
                data=json.dumps(
                    {
                        "files": [
                            {
                                "media_kind": media_kind,
                                "content_type": content_type,
                                "declared_bytes": len(data),
                            }
                        ]
                    }
                ),
                content_type="application/json",
            )
            assert reserve_resp.status_code == 200, reserve_resp.content
            reserved = json.loads(reserve_resp.content)["files"][0]
            put_path = reserved["put_url"].split("http://testserver", 1)[-1]
            put_resp = client.put(put_path, data=data, content_type=content_type)
            assert put_resp.status_code == 204
            complete_resp = client.post(reserved["complete_url"])
            assert complete_resp.status_code == 200, complete_resp.content
            return reserved

        import io

        from PIL import Image

        photo_buf = io.BytesIO()
        Image.new("RGB", (400, 300), color=(120, 40, 40)).save(photo_buf, format="JPEG")
        photo = _reserve_upload("photo", "image/jpeg", photo_buf.getvalue())
        video = _reserve_upload("video", "video/mp4", b"fake video bytes" * 10)

        run_due_jobs_now()  # runs both deferred media.process_item jobs

        photo_item = RequestMedia.objects.get(id=photo["item_id"])
        assert photo_item.status == STATUS_READY

        video_item = RequestMedia.objects.get(id=video["item_id"])
        assert video_item.status == STATUS_REJECTED
        assert video_item.failure_code == FAILURE_PROCESSING_UNAVAILABLE

        secure_resp = client.get(reverse("web:request_help_secure_page", kwargs={"token": token}))
        assert secure_resp.status_code == 200
        assert b"Photos" in secure_resp.content

        # --- duplicate detection (§9/Q-115): a second submission sharing this one's phone
        # number and street address gets flagged against it -- a different email (so the
        # per-address resend cooldown on DISTINCTIVE_EMAIL, hit if the same address requested
        # a second code moments later, never comes into it) and a different name (so the
        # match is proven on phone/address, not name_zip), purely on the keyed match, no
        # description/AI matching. ---
        second_email = "second." + DISTINCTIVE_EMAIL
        second_client = client.__class__()
        _fill_and_submit_form(
            second_client,
            reaching_you_overrides={"full_name": "Someone Else Entirely", "email": second_email},
        )
        mail.outbox.clear()
        second_client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        run_due_jobs_now()
        second_challenge = RequesterVerificationChallenge.objects.get(
            purpose="intake", email_key=otp.hash_value(second_email)
        )
        second_challenge.code_hash = otp.hash_value("975319")
        second_challenge.save(update_fields=["code_hash"])
        second_client.post(reverse("web:request_help_verify"), {"code": "975319"}, follow=True)
        run_due_jobs_now()  # the second request's own duplicate-check job

        second_request = AssistanceRequest.objects.get(requester__email=second_email)
        match = RequestMatch.objects.get(request=second_request, prior_request=request)
        assert "phone" in match.reasons
        assert "address" in match.reasons
        assert "email" not in match.reasons  # different emails: only phone/address matched

    @pytest.mark.django_db(transaction=True)
    def test_04_pastor_or_board_approves(self, client, run_due_jobs_now, make_user):
        """PRD §77 step 4: "A pastor or Board route approves it." Real HTTP-driven (POSTs
        through `ham/web/views_requests.py::request_approve`, the same view a browser hits),
        not a service-layer shortcut, per approvals.md/approvals-contracts.md (owner box
        Q-153-Q-161). Covers both routes plus the urgent path in one pass:
          1. a normal pastoral-route approval;
          2. a Board-route approval (Board rep records the Board's own decision);
          3. an urgent request, "Certify and approve" in one step -- the held
             `RequestApproved` fires only after `Approval.effective_at` runs
             (approvals-contracts.md §4), while the immediate, never-held
             `RequestUrgentApproval` alert reaches Director/AD's Inbox right away, PII-free
             (§68/Q-132: HAM # + category only, never the distinctive requester identity).
        """
        from django.urls import reverse

        from ham.identity.models import RoleAssignment, SharedIdentityProfile
        from ham.notifications.models import Notification
        from ham.platform import otp
        from ham.platform.clock import now as clock_now
        from ham.requester_portal.models import RequesterVerificationChallenge
        from ham.requests.models import Approval, ApprovalOutcome, ApprovalRoute, AssistanceRequest
        from ham.requests.states import RequestStatus

        def _login(role: str, *, email: str, full_name: str):
            user = make_user(email)
            SharedIdentityProfile.objects.create(user=user, full_name=full_name)
            RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())
            c = client.__class__()
            c.force_login(user)
            session = c.session
            session["ham_mfa_satisfied"] = True
            session.save()
            return c, user

        def _submit_via_http(email: str, *, urgent: bool = False) -> AssistanceRequest:
            c = client.__class__()
            overrides = {"email": email}
            _fill_and_submit_form(c, reaching_you_overrides=overrides)
            if urgent:
                # Re-post the "need" step with the urgency fields set, mirroring the R1-R6
                # wizard's own field names (ham/web/views_requester.py).
                need = _step_payload()["need"]
                c.post(
                    reverse("web:request_help_step", kwargs={"step": "need"}),
                    {
                        **need,
                        "urgent_requested": "on",
                        "urgency_reason": "water_or_damage",
                        "urgency_justification": "It is getting worse every hour.",
                    },
                    follow=True,
                )
            mail.outbox.clear()
            c.post(
                reverse("web:request_help_step", kwargs={"step": "review"}),
                {"attested_statements": ["owner_authority", "responsibility"]},
                follow=True,
            )
            run_due_jobs_now()
            challenge = RequesterVerificationChallenge.objects.get(
                purpose="intake", email_key=otp.hash_value(email)
            )
            code = "".join(str((hash(email) + i) % 10) for i in range(6))
            challenge.code_hash = otp.hash_value(code)
            challenge.save(update_fields=["code_hash"])
            c.post(reverse("web:request_help_verify"), {"code": code}, follow=True)
            run_due_jobs_now()  # the duplicate-check job -> AWAITING_APPROVAL
            request = AssistanceRequest.objects.get(requester__email=email)
            assert request.status == RequestStatus.AWAITING_APPROVAL.value
            return request

        # --- 1. Pastoral route -----------------------------------------------------------
        pastoral_request = _submit_via_http("step4.pastoral." + DISTINCTIVE_EMAIL)
        pastor_client, pastor = _login(
            "PASTOR", email="ruth.step4@example.org", full_name="Ruth Alvarez"
        )
        resp = pastor_client.post(
            reverse("web:request_approve", args=[pastoral_request.id]), {"route": "pastoral"}
        )
        assert resp.status_code == 302
        pastoral_request.refresh_from_db()
        assert pastoral_request.status == RequestStatus.APPROVED.value
        pastoral_approval = Approval.objects.get(request_id=pastoral_request.id)
        assert pastoral_approval.route == ApprovalRoute.PASTORAL.value
        assert pastoral_approval.outcome == ApprovalOutcome.APPROVED.value
        assert pastoral_approval.decided_by_user_id == pastor.id

        # --- 2. Board route ----------------------------------------------------------------
        board_request = _submit_via_http("step4.board." + DISTINCTIVE_EMAIL)
        board_client, board_rep = _login(
            "BOARD_REPRESENTATIVE", email="samuel.step4@example.org", full_name="Samuel Okafor"
        )
        resp = board_client.post(
            reverse("web:request_approve", args=[board_request.id]), {"route": "board"}
        )  # board_decided_on omitted -- the service itself prefills "today" (Q-163)
        assert resp.status_code == 302
        board_request.refresh_from_db()
        assert board_request.status == RequestStatus.APPROVED.value
        board_approval = Approval.objects.get(request_id=board_request.id)
        assert board_approval.route == ApprovalRoute.BOARD.value
        assert board_approval.decided_by_user_id == board_rep.id

        # --- 3. Urgent: "Certify and approve" in one step (§10, Q-160/Q-161) --------------
        urgent_request = _submit_via_http("step4.urgent." + DISTINCTIVE_EMAIL, urgent=True)
        urgent_request.refresh_from_db()
        director_client, director = _login(
            "HAM_DIRECTOR", email="marcus.step4@example.org", full_name="Marcus Bell"
        )
        _login("ASSISTANT_DIRECTOR", email="andre.step4@example.org", full_name="Andre Whitfield")
        resp = pastor_client.post(
            reverse("web:request_approve", args=[urgent_request.id]),
            {"route": "pastoral", "mode": "urgent"},
        )
        assert resp.status_code == 302
        urgent_approval = Approval.objects.get(request_id=urgent_request.id)
        assert urgent_approval.urgent_approval is True
        # `transaction=True` (real commits) is required for this test so the outbox's
        # `transaction.on_commit`-deferred dispatch (`ham/outbox/api.py::emit`) actually
        # enqueues a job at all -- under the ordinary rolled-back `django_db` transaction the
        # other §77 steps use, `on_commit` callbacks never fire, so nothing would ever be
        # there for `run_due_jobs_now` to find.
        run_due_jobs_now()

        # The urgent-approval alert to Director/AD is never held (approvals-contracts.md §4):
        # it must already be in the Inbox right now, before the undo window/held-effects job
        # ever runs, and it must never leak the distinctive requester identity.
        director_notices = Notification.objects.filter(
            recipient_user_id=director.id, kind__icontains="urgent"
        )
        assert director_notices.exists(), "Director got no immediate urgent-approval alert"
        for notice in director_notices:
            assert DISTINCTIVE_NAME not in notice.title
            assert "step4.urgent" not in notice.title
            assert urgent_request.display_number in notice.title

        # `request.status` itself moves to APPROVED synchronously, inside the deciding
        # command's own transaction -- only the *outbox* `RequestApproved` event (and the
        # side effects that ride on it: the requester email, closing photo batches,
        # withdrawing open questions, the "decision" in-app update to other leaders) is held
        # until `Approval.effective_at` (approvals-contracts.md §4). `RequestUrgentApproval`
        # above is the one, deliberately different, exception to that hold.
        urgent_request.refresh_from_db()
        assert urgent_request.status == RequestStatus.APPROVED.value
        from ham.outbox.models import OutboxEvent

        assert not OutboxEvent.objects.filter(
            event_type="RequestApproved", aggregate_id=urgent_request.id
        ).exists(), "RequestApproved must stay held until effective_at, not fire at decide time"

        # The actual release is a Procrastinate job row scheduled for exactly
        # `Approval.effective_at` and only `run_due_jobs_now` picks it up once real wall-clock
        # time (`WHERE scheduled_at <= now()`, `ham/jobs/__init__.py`) reaches it -- a
        # `FixedClock` in this Python process can't move Postgres's own `now()`. This mirrors
        # `tests/requests/test_s32_decisions.py::TestHeldEffects`'s own pattern: call the
        # held-effects function directly, the same body the deferred job itself runs at
        # `effective_at`, rather than trying to fast-forward Postgres's clock.
        from ham.requests.services_decisions import run_held_decision_effects

        run_held_decision_effects(urgent_approval.id)
        assert OutboxEvent.objects.filter(
            event_type="RequestApproved", aggregate_id=urgent_request.id
        ).exists()

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

    def test_28_audit_records_every_consequential_actor(
        self, client, mailbox, run_due_jobs_now, make_user
    ):
        """PRD §77 step 28: "The audit trail records every consequential actor." Generic
        step-1 coverage (`tests/authz/test_commands.py`, `tests/authz/test_expected_matrix.py`,
        `tests/audit/test_command_registry.py`) already proves every `@command` site is
        wired. This is the first module with real request/project rows to attach a
        *request-scoped* check to (intake.md's module boundary table: "Audit `project_id` =
        request id from intake onward, so the audit 'project' filter shows the full history
        [once step-3 projects exist]" -- `project_id` is set on request-stage events already,
        even though no `Project` row exists yet). Still NOT "done" in the full sense the
        docstring above warns about: once step 3 (projects) lands, add a second assertion
        here (or a sibling one) that a *Project*-stage event also carries the same
        `project_id`, continuing the same audit trail."""
        from django.urls import reverse

        from ham.audit.models import AuditEvent
        from ham.platform import otp
        from ham.requester_portal.models import RequesterVerificationChallenge
        from ham.requests.models import AssistanceRequest

        step28_email = "step28." + DISTINCTIVE_EMAIL
        _fill_and_submit_form(client, reaching_you_overrides={"email": step28_email})
        client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        run_due_jobs_now()
        challenge = RequesterVerificationChallenge.objects.get(
            purpose="intake", email_key=otp.hash_value(step28_email)
        )
        challenge.code_hash = otp.hash_value("112233")
        challenge.save(update_fields=["code_hash"])
        client.post(reverse("web:request_help_verify"), {"code": "112233"}, follow=True)
        run_due_jobs_now()  # the duplicate-check job -> request.status_changed

        request = AssistanceRequest.objects.get(requester__email=step28_email)
        events = list(AuditEvent.objects.filter(target_id=str(request.id), target_type="request"))
        assert events, "no AuditEvent rows for this request at all"
        assert {e.action for e in events} >= {"request.submitted", "request.status_changed"}

        for event in events:
            # actor + UTC time (foundation.md §9.2/CLAUDE.md priority 3).
            assert event.actor_type in {"requester", "system", "user"}
            assert event.occurred_at.tzinfo is not None
            assert event.occurred_at.utcoffset() == dt.timedelta(0)
            # PRD §68/§63: never requester name/address/phone/email in the audit trail.
            for blob in (event.before, event.after, event.context, event.reason):
                text = str(blob)
                assert DISTINCTIVE_NAME not in text
                assert DISTINCTIVE_STREET not in text
                assert DISTINCTIVE_PHONE not in text
                assert step28_email not in text
            # intake.md: project_id = request id from intake onward, even pre-Project.
            if event.action in {"request.submitted", "request.status_changed"}:
                assert event.project_id == request.id

        # --- step 3 (Approvals) extension: the decision actors themselves. Not "re-marking
        # done" -- a genuinely new assertion, per the module docstring's own instruction,
        # now that step 3 gives this harness a real decider to check (still pending the
        # matching *Project*-stage extension once step 4/projects lands). Covers a pastoral
        # approval and a rejection, both real HTTP POSTs, and both actors must show up with
        # their own `actor_user_id`, never a PII value, and the rejection's kind message must
        # never leak into audit rows either (Q-050). ---
        from ham.identity.models import RoleAssignment, SharedIdentityProfile

        pastor = make_user("ruth.step28@example.org")
        SharedIdentityProfile.objects.create(user=pastor, full_name="Ruth Step28")
        RoleAssignment.objects.create(
            user=pastor, role="PASTOR", granted_at=dt.datetime.now(dt.UTC)
        )
        approve_client = client.__class__()
        approve_client.force_login(pastor)
        session = approve_client.session
        session["ham_mfa_satisfied"] = True
        session.save()
        resp = approve_client.post(
            reverse("web:request_approve", args=[request.id]), {"route": "pastoral"}
        )
        assert resp.status_code == 302

        decision_events = list(
            AuditEvent.objects.filter(
                target_id=str(request.id), target_type="request", action="request.approved"
            )
        )
        assert decision_events, "no request.approved AuditEvent for the pastoral decision"
        for event in decision_events:
            assert event.actor_type == "user"
            assert event.actor_user_id == pastor.id
            assert event.occurred_at.tzinfo is not None
            assert event.occurred_at.utcoffset() == dt.timedelta(0)
            for blob in (event.before, event.after, event.context, event.reason):
                text = str(blob)
                assert DISTINCTIVE_NAME not in text
                assert DISTINCTIVE_STREET not in text
                assert DISTINCTIVE_PHONE not in text
                assert step28_email not in text
            assert event.project_id == request.id

        # A second, freshly submitted request, declined this time -- the rejection message
        # itself (a **C** field, Q-050) must never appear in audit `before`/`after` either.
        step28_reject_email = "step28-reject." + DISTINCTIVE_EMAIL
        _fill_and_submit_form(client, reaching_you_overrides={"email": step28_reject_email})
        client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
            follow=True,
        )
        run_due_jobs_now()
        reject_challenge = RequesterVerificationChallenge.objects.get(
            purpose="intake", email_key=otp.hash_value(step28_reject_email)
        )
        reject_challenge.code_hash = otp.hash_value("445566")
        reject_challenge.save(update_fields=["code_hash"])
        client.post(reverse("web:request_help_verify"), {"code": "445566"}, follow=True)
        run_due_jobs_now()
        reject_request_row = AssistanceRequest.objects.get(requester__email=step28_reject_email)

        distinctive_reject_message = "This is a kind but distinctive decline sentence for §77."
        resp = approve_client.post(
            reverse("web:request_reject", args=[reject_request_row.id]),
            {
                "route": "pastoral",
                "reason_code": "couldnt_confirm",
                "message": distinctive_reject_message,
            },
        )
        assert resp.status_code == 302

        reject_events = list(
            AuditEvent.objects.filter(
                target_id=str(reject_request_row.id),
                target_type="request",
                action="request.rejected",
            )
        )
        assert reject_events, "no request.rejected AuditEvent for the pastoral decline"
        for event in reject_events:
            assert event.actor_type == "user"
            assert event.actor_user_id == pastor.id
            for blob in (event.before, event.after, event.context, event.reason):
                text = str(blob)
                assert distinctive_reject_message not in text
                assert DISTINCTIVE_NAME not in text
                assert step28_reject_email not in text

    def test_29_ai_generates_post_project_report(self):
        _pending(29, "AI generates post-project report.", "ai, reporting")

    def test_30_privacy_restrictions_hold_end_to_end(self):
        _pending(
            30,
            "Privacy restrictions prevent unauthorized exposure throughout.",
            "all modules (partially covered generically today; see module docstring)",
        )
