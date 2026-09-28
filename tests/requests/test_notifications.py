"""S2.6: `ham.requests.notifications` -- leadership email + in-app builders (intake.md §6
"Who is notified"; docs/ux/intake.md §7 rows L-E1/L-E2/L-E3; Q-123/Q-133 urgent overrides).
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.notifications.models import Notification
from ham.outbox.models import OutboxEvent
from ham.platform.clock import now as clock_now
from ham.requests.notifications import (
    _build_awaiting_approval_emails,
    _build_awaiting_approval_notices,
    _build_cancelled_notices,
    _build_needs_phone_check_emails,
    _build_needs_phone_check_notices,
)
from ham.requests.services import submit_request

from .conftest import make_payload, no_email_payload

pytestmark = pytest.mark.django_db

DISTINCTIVE_NAME = "Zbigniew Kowalczyk"
DISTINCTIVE_STREET = "8842 Windswept Hollow Terrace"
DISTINCTIVE_PHONE = "+13055559981"
DISTINCTIVE_EMAIL = "zbigniew.kowalczyk@example.org"


def _grant(user, role):
    return RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


def _event(event_type: str, *, aggregate_id, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type, aggregate_type="request", aggregate_id=aggregate_id, payload=payload
    )


def _submitted_request(requester_ctx, **overrides):
    payload = make_payload(
        full_name=DISTINCTIVE_NAME,
        phone=DISTINCTIVE_PHONE,
        email=DISTINCTIVE_EMAIL,
        line1=DISTINCTIVE_STREET,
        **overrides,
    )
    return submit_request(
        requester_ctx, draft_id=uuid.uuid4(), verification_id=uuid.uuid4(), payload=payload
    )


def _no_email_request(requester_ctx):
    payload = no_email_payload(full_name=DISTINCTIVE_NAME, phone=DISTINCTIVE_PHONE)
    return submit_request(
        requester_ctx, draft_id=uuid.uuid4(), verification_id=None, payload=payload
    )


class TestAwaitingApprovalNormal:
    def test_email_only_to_those_who_want_it_all_four_get_inapp(self, requester_ctx, make_user):
        pastor = make_user("ruth@example.org")
        board = make_user("marcus@example.org")
        director = make_user("nadia@example.org")
        assistant = make_user("owen@example.org")
        for u, role in (
            (pastor, roles.PASTOR),
            (board, roles.BOARD_REPRESENTATIVE),
            (director, roles.HAM_DIRECTOR),
            (assistant, roles.ASSISTANT_DIRECTOR),
        ):
            _grant(u, role)
        SharedIdentityProfile.objects.create(user=board, notify_email=False)

        request = _submitted_request(requester_ctx)
        event = _event(
            "RequestAwaitingApproval", aggregate_id=request.id, payload={"urgent": False}
        )

        emails = _build_awaiting_approval_emails(event)
        assert emails is not None
        assert {e.to for e in emails} == {
            "ruth@example.org",
            "nadia@example.org",
            "owen@example.org",
        }

        notices = _build_awaiting_approval_notices(event)
        assert notices is not None
        assert {n.recipient_user_id for n in notices} == {
            pastor.id,
            board.id,
            director.id,
            assistant.id,
        }
        assert all(not n.urgent and not n.requires_ack for n in notices)


class TestAwaitingApprovalUrgent:
    def test_pastors_get_email_regardless_of_preference_dir_ad_do_not(
        self, requester_ctx, make_user
    ):
        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)
        SharedIdentityProfile.objects.create(user=pastor, notify_email=False)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        SharedIdentityProfile.objects.create(user=director, notify_email=True)

        request = _submitted_request(
            requester_ctx, urgent_requested=True, urgency_justification="x"
        )
        event = _event("RequestAwaitingApproval", aggregate_id=request.id, payload={"urgent": True})

        emails = _build_awaiting_approval_emails(event)
        assert emails is not None
        assert {e.to for e in emails} == {"ruth@example.org"}  # Director never emailed here

        notices = _build_awaiting_approval_notices(event)
        assert notices is not None
        pastor_notice = next(n for n in notices if n.recipient_user_id == pastor.id)
        assert pastor_notice.urgent and pastor_notice.requires_ack
        director_notice = next(n for n in notices if n.recipient_user_id == director.id)
        assert not director_notice.urgent and not director_notice.requires_ack


class TestNeedsPhoneCheck:
    def test_director_and_ad_only_email_per_preference(self, requester_ctx, make_user):
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        assistant = make_user("owen@example.org")
        _grant(assistant, roles.ASSISTANT_DIRECTOR)
        SharedIdentityProfile.objects.create(user=assistant, notify_email=False)
        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)

        request = _no_email_request(requester_ctx)
        event = _event("RequestSubmitted", aggregate_id=request.id, payload={"urgent": False})

        notices = _build_needs_phone_check_notices(event)
        assert notices is not None
        assert {n.recipient_user_id for n in notices} == {director.id, assistant.id}

        emails = _build_needs_phone_check_emails(event)
        assert emails is not None
        assert {e.to for e in emails} == {"nadia@example.org"}  # assistant opted out

    def test_urgent_overrides_the_preference(self, requester_ctx, make_user):
        assistant = make_user("owen@example.org")
        _grant(assistant, roles.ASSISTANT_DIRECTOR)
        SharedIdentityProfile.objects.create(user=assistant, notify_email=False)

        request = _no_email_request(requester_ctx)
        event = _event("RequestSubmitted", aggregate_id=request.id, payload={"urgent": True})

        emails = _build_needs_phone_check_emails(event)
        assert emails is not None
        assert {e.to for e in emails} == {"owen@example.org"}

        notices = _build_needs_phone_check_notices(event)
        assert notices is not None
        assert all(n.urgent and n.requires_ack for n in notices)

    def test_email_path_submission_yields_no_phone_check_notice(self, requester_ctx, make_user):
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        request = _submitted_request(requester_ctx)
        event = _event("RequestSubmitted", aggregate_id=request.id, payload={"urgent": False})

        assert _build_needs_phone_check_notices(event) is None
        assert _build_needs_phone_check_emails(event) is None


class TestCancelledInApp:
    def test_director_and_ad_get_an_update(self, requester_ctx, make_user):
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)

        request = _submitted_request(requester_ctx)
        event = _event(
            "RequestCancelled",
            aggregate_id=request.id,
            payload={"reason_code": "requester_withdrew"},
        )
        notices = _build_cancelled_notices(event)
        assert notices is not None
        assert {n.recipient_user_id for n in notices} == {director.id}


class TestAdministratorNeverIncluded:
    def test_administrator_role_never_appears_among_recipients(self, requester_ctx, make_user):
        admin = make_user("kevin@example.org")
        _grant(admin, roles.ADMINISTRATOR)

        request = _submitted_request(requester_ctx)
        event = _event(
            "RequestAwaitingApproval", aggregate_id=request.id, payload={"urgent": False}
        )
        notices = _build_awaiting_approval_notices(event)
        recipients = {n.recipient_user_id for n in notices} if notices else set()
        assert admin.id not in recipients

        emails = _build_awaiting_approval_emails(event)
        assert emails in (None, [])


class TestPIIFreeSubjectsAndTitles:
    def test_no_pii_in_subjects_or_titles(self, requester_ctx, make_user):
        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        request = _submitted_request(
            requester_ctx, urgent_requested=True, urgency_justification="x"
        )
        awaiting_event = _event(
            "RequestAwaitingApproval", aggregate_id=request.id, payload={"urgent": True}
        )
        emails = _build_awaiting_approval_emails(awaiting_event) or []
        notices = _build_awaiting_approval_notices(awaiting_event) or []

        no_email_req = _no_email_request(requester_ctx)
        phone_event = _event(
            "RequestSubmitted", aggregate_id=no_email_req.id, payload={"urgent": False}
        )
        phone_emails = _build_needs_phone_check_emails(phone_event) or []
        phone_notices = _build_needs_phone_check_notices(phone_event) or []

        forbidden = (DISTINCTIVE_NAME, DISTINCTIVE_STREET, DISTINCTIVE_PHONE, DISTINCTIVE_EMAIL)
        for text in [e.subject for e in emails + phone_emails] + [
            n.title for n in notices + phone_notices
        ]:
            for bad in forbidden:
                assert bad not in text


class TestInAppRowsActuallyPersist:
    """The full outbox -> `ham.notifications.inapp` path, not just the builder in isolation."""

    @pytest.mark.django_db(transaction=True)
    def test_awaiting_approval_creates_notification_rows(self, requester_ctx, make_user):
        from ham.jobs import run_due_jobs_now

        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)

        request = _submitted_request(requester_ctx)
        # Three deferred hops: the duplicate-check job -> complete_intake_checks emits
        # RequestAwaitingApproval -> its own dispatch job -> the `inapp` subscriber. Each hop
        # is only enqueued once the previous one's transaction commits, so it takes more than
        # one `run_due_jobs_now()` pass to settle (it only runs jobs already `todo` when it
        # started -- see its own docstring).
        for _ in range(4):
            run_due_jobs_now()
        request.refresh_from_db()

        assert Notification.objects.filter(
            recipient_user_id=pastor.id, kind="request_awaiting_approval"
        ).exists()
