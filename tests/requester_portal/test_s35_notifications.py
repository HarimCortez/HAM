"""S3.5: `ham.requester_portal.notifications` -- E8-E15 requester email builders
(docs/ux/approvals.md, approvals-contracts.md §4/§6, Q-102/Q-154/Q-171/Q-174/Q-175).

Every builder is exercised directly against a hand-built `OutboxEvent` (same style as
`tests/requester_portal/test_notifications.py`), plus one end-to-end test through the real
`approve_request`/`reject_request` -> held-effects job -> outbox -> email path to prove
"nothing is sent to the requester for an undone decision" for real, not just at the builder
level.
"""

from __future__ import annotations

import re
import uuid

import pytest
from django.test import Client

from ham.outbox.models import OutboxEvent
from ham.requester_portal import services
from ham.requester_portal.models import RequesterAccessLink
from ham.requester_portal.notifications import (
    _build_approved_email,
    _build_question_asked_email,
    _build_reconsideration_received_email,
    _build_rejected_email,
)
from ham.requests.models import Approval
from ham.requests.services import complete_intake_checks, submit_request
from ham.requests.services_decisions import (
    approve_request,
    decide_reconsideration,
    reject_request,
    request_reconsideration,
    run_held_decision_effects,
    undo_decision,
)
from ham.requests.services_questions import ask_question
from tests.requests.conftest import actor_ctx, make_payload

pytestmark = pytest.mark.django_db

DISTINCTIVE_NAME = "Zbigniew Kowalczyk"
DISTINCTIVE_STREET = "8842 Windswept Hollow Terrace"
DISTINCTIVE_PHONE = "+13055559981"
DISTINCTIVE_EMAIL = "zbigniew.kowalczyk@example.org"

_URL_RE = re.compile(r"https?://\S+")


@pytest.fixture
def requester_ctx():
    from ham.authz.context import RequesterContext

    return RequesterContext(request_id=None)


@pytest.fixture
def director_ctx():
    return actor_ctx(roles=frozenset({"HAM_DIRECTOR"}))


@pytest.fixture
def pastor_ctx():
    return actor_ctx(roles=frozenset({"PASTOR"}))


@pytest.fixture
def board_rep_ctx():
    return actor_ctx(roles=frozenset({"BOARD_REPRESENTATIVE"}))


@pytest.fixture
def system_ctx():
    from ham.authz.context import SystemContext

    return SystemContext()


@pytest.fixture(autouse=True)
def _real_portal_lookups(real_portal_lookups):
    """See `tests/requester_portal/test_notifications.py`'s identical fixture."""


def _submit(ctx, **overrides):
    payload = make_payload(
        full_name=DISTINCTIVE_NAME,
        phone=DISTINCTIVE_PHONE,
        email=DISTINCTIVE_EMAIL,
        line1=DISTINCTIVE_STREET,
        **overrides,
    )
    return submit_request(ctx, draft_id=uuid.uuid4(), verification_id=uuid.uuid4(), payload=payload)


def _awaiting(requester_ctx, system_ctx, **overrides):
    req = _submit(requester_ctx, **overrides)
    services.issue_link(request_id=req.id, kind=RequesterAccessLink.KIND_INITIAL)
    complete_intake_checks(system_ctx, request_id=req.id)
    req.refresh_from_db()
    return req


def _event(event_type: str, *, aggregate_id, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type, aggregate_type="request", aggregate_id=aggregate_id, payload=payload
    )


def _extract_url(text_body: str) -> str:
    urls = _URL_RE.findall(text_body)
    assert urls, f"no URL found in email body: {text_body!r}"
    return urls[0].rstrip(".")


def _assert_resolves(url: str) -> None:
    path = url.split("://", 1)[1].split("/", 1)[1]
    resp = Client().get(f"/{path}")
    assert resp.status_code == 200, f"{url} did not resolve (got {resp.status_code})"


class TestApprovedEmail:
    def test_keeps_the_section_11_line(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        event = _event(
            "RequestApproved",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "stage": approval.stage,
                "route": approval.route,
                "urgent_approval": False,
            },
        )
        email = _build_approved_email(event)
        assert email is not None
        assert "doesn't yet promise the work can be done" in email.text_body
        url = _extract_url(email.text_body)
        assert "/request-help/r/" in url
        _assert_resolves(url)
        assert email.subject == f"Update on your {req.display_number}"

    def test_urgent_line_and_section_11_line_both_present(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = _awaiting(
            requester_ctx,
            system_ctx,
            urgent_requested=True,
            urgency_reason="someone_could_get_hurt",
        )
        req.refresh_from_db()
        approve_request(pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True)
        event = _event(
            "RequestApproved",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "stage": "initial",
                "route": "pastoral",
                "urgent_approval": True,
            },
        )
        email = _build_approved_email(event)
        assert email is not None
        assert "911" in email.text_body
        assert "doesn't yet promise the work can be done" in email.text_body

    def test_reconsideration_stage_wording(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="couldnt_confirm",
            message="We could not confirm the details.",
        )
        req.refresh_from_db()
        from ham.authz.context import RequesterContext

        recon_ctx = RequesterContext(request_id=req.id)
        request_reconsideration(recon_ctx, note="Please look again")
        decide_reconsideration(
            pastor_ctx, request_id=req.id, approve=True, reason="Looks fine after all"
        )
        event = _event(
            "RequestApproved",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "stage": "reconsideration",
                "route": "pastoral",
                "urgent_approval": False,
            },
        )
        email = _build_approved_email(event)
        assert email is not None
        assert "after taking another look" in email.text_body

    def test_no_email_on_file_means_nothing(self, requester_ctx, system_ctx, pastor_ctx):
        from ham.requests.services import verify_by_phone
        from tests.requests.conftest import no_email_payload

        payload = no_email_payload(full_name=DISTINCTIVE_NAME, phone=DISTINCTIVE_PHONE)
        req = submit_request(
            requester_ctx, draft_id=uuid.uuid4(), verification_id=None, payload=payload
        )
        verify_by_phone(actor_ctx(roles=frozenset({"HAM_DIRECTOR"})), request_id=req.id)
        complete_intake_checks(system_ctx, request_id=req.id)
        req.refresh_from_db()
        approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        event = _event(
            "RequestApproved",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "stage": "initial",
                "route": "pastoral",
                "urgent_approval": False,
            },
        )
        assert _build_approved_email(event) is None


class TestRejectedEmail:
    def test_not_final_has_message_and_deadline(self, requester_ctx, system_ctx, pastor_ctx):
        # No `set_clock`/`FixedClock` here on purpose: `reject_request` defers a real
        # Procrastinate job for the held-effects window (`ham.jobs.defer_later`, a write on
        # its own connection that a rolled-back Django test transaction can't undo) -- a
        # fake *past* `now()` would schedule that job's real `scheduled_at` in the past,
        # making it immediately "due" for every later test's `run_due_jobs_now()` and
        # leaking a phantom job against a request no other test knows about. Instead, this
        # asserts the deadline text is correct by independently formatting whatever real
        # `reconsideration_deadline_at` the command actually stored, in church time.
        req = _awaiting(requester_ctx, system_ctx)
        reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="couldnt_confirm",
            message="We could not confirm what was needed.",
        )
        req.refresh_from_db()
        from zoneinfo import ZoneInfo

        expected_deadline = req.reconsideration_deadline_at.astimezone(
            ZoneInfo("America/New_York")
        ).strftime("%a, %b %-d")
        event = _event(
            "RequestRejected",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "stage": "initial",
                "route": "pastoral",
                "reason_code": "couldnt_confirm",
                "final": False,
            },
        )
        email = _build_rejected_email(event)
        assert email is not None
        assert "We could not confirm what was needed." in email.text_body
        assert expected_deadline in email.text_body
        url = _extract_url(email.text_body)
        _assert_resolves(url)

    def test_final_wording_no_deadline_clause(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="couldnt_confirm",
            message="We could not confirm what was needed.",
        )
        req.refresh_from_db()
        from ham.authz.context import RequesterContext

        request_reconsideration(
            RequesterContext(request_id=req.id),
            note="Please look again",
        )
        decide_reconsideration(
            pastor_ctx,
            request_id=req.id,
            approve=False,
            reason="Still can't help with this one.",
            reason_code="couldnt_confirm",
        )
        event = _event(
            "RequestRejected",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "stage": "reconsideration",
                "route": "pastoral",
                "reason_code": "couldnt_confirm",
                "final": True,
            },
        )
        email = _build_rejected_email(event)
        assert email is not None
        assert "Still can't help with this one." in email.text_body
        assert "welcome to send a new request" in email.text_body
        assert "reconsider until" not in email.text_body


class TestQuestionAskedEmail:
    def test_question_text_in_body_neutral_subject_is_not_used(
        self, requester_ctx, system_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        question = ask_question(director_ctx, request_id=req.id, question="Only when it rains?")
        event = _event(
            "RequesterQuestionAsked",
            aggregate_id=req.id,
            payload={"request_id": str(req.id), "question_id": str(question.id)},
        )
        email = _build_question_asked_email(event)
        assert email is not None
        assert "Only when it rains?" in email.text_body
        assert email.subject == f"A question about your {req.display_number}"
        url = _extract_url(email.text_body)
        _assert_resolves(url)

    def test_phone_answered_in_same_step_sends_nothing(
        self, requester_ctx, system_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        question = ask_question(
            director_ctx,
            request_id=req.id,
            question="Any pets at the home?",
            phone_answer="No pets.",
        )
        event = _event(
            "RequesterQuestionAsked",
            aggregate_id=req.id,
            payload={"request_id": str(req.id), "question_id": str(question.id)},
        )
        assert _build_question_asked_email(event) is None


class TestReconsiderationReceivedEmail:
    def test_confirmation_email(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="couldnt_confirm",
            message="We could not confirm what was needed.",
        )
        req.refresh_from_db()
        from ham.authz.context import RequesterContext

        result = request_reconsideration(
            RequesterContext(request_id=req.id),
            note="Please look again",
        )
        event = _event(
            "ReconsiderationRequested",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "reconsideration_id": str(result.id),
                "route": "pastoral",
                "via": "secure_page",
            },
        )
        email = _build_reconsideration_received_email(event)
        assert email is not None
        assert "we'll take" in email.text_body
        url = _extract_url(email.text_body)
        _assert_resolves(url)


class TestUndoneDecisionSendsNothing:
    """Drive a real decide -> undo through the held-effects job: nothing goes out.

    Deliberately *not* `transaction=True`: `approve_request` defers a real Procrastinate job
    for the held-effects window (`ham.jobs.defer_later`, via the same Django connection --
    see `ham/jobs/__init__.py`'s own docstring), and this test calls `run_held_decision_
    effects` directly rather than through the job queue, leaving that deferred job row
    un-consumed. Under the default (non-`transaction=True`) `django_db` mark the whole test
    runs inside one rolled-back transaction, so that orphaned job row (and the request/
    approval rows it would reference) never actually reaches Postgres; under
    `transaction=True` it would really commit and could later be picked up as "due" by an
    unrelated test's `run_due_jobs_now()`, once the DB has been flushed out from under it
    (confirmed: this was a real, reproducible cross-test pollution bug before this fix).
    """

    def test_undo_before_effective_at_suppresses_the_email(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        from django.core import mail

        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        undo_decision(pastor_ctx, approval_id=approval.id)

        mail.outbox.clear()
        run_held_decision_effects(approval.id)

        approval = Approval.objects.get(pk=approval.id)
        assert approval.undone_at is not None
        assert approval.effects_ran_at is not None
        assert not OutboxEvent.objects.filter(event_type="RequestApproved").exists()
        assert mail.outbox == []


class TestPIIFreeSubjects:
    def test_no_pii_in_any_s35_requester_email_subject(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = _awaiting(requester_ctx, system_ctx)
        approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        approved_event = _event(
            "RequestApproved",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "stage": "initial",
                "route": "pastoral",
                "urgent_approval": False,
            },
        )

        req2 = _awaiting(requester_ctx, system_ctx, need_category="electrical")
        reject_request(
            pastor_ctx,
            request_id=req2.id,
            route="pastoral",
            reason_code="couldnt_confirm",
            message="message",
        )
        rejected_event = _event(
            "RequestRejected",
            aggregate_id=req2.id,
            payload={
                "request_id": str(req2.id),
                "stage": "initial",
                "route": "pastoral",
                "reason_code": "couldnt_confirm",
                "final": False,
            },
        )

        req3 = _awaiting(requester_ctx, system_ctx, need_category="roof_or_ceiling")
        question = ask_question(director_ctx, request_id=req3.id, question="Detail?")
        question_event = _event(
            "RequesterQuestionAsked",
            aggregate_id=req3.id,
            payload={"request_id": str(req3.id), "question_id": str(question.id)},
        )

        emails = [
            e
            for e in (
                _build_approved_email(approved_event),
                _build_rejected_email(rejected_event),
                _build_question_asked_email(question_event),
            )
            if e is not None
        ]
        assert len(emails) == 3
        forbidden = (DISTINCTIVE_NAME, DISTINCTIVE_STREET, DISTINCTIVE_PHONE)
        for email in emails:
            for bad in forbidden:
                assert bad not in email.subject
