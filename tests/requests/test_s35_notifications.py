"""S3.5: `ham.requests.notifications` -- L-E5-L-E12 leadership email + in-app builders
(docs/ux/approvals.md, approvals-contracts.md §4/§6, Q-161/Q-168/Q-176).
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.authz.context import RequesterContext
from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.notifications.models import Notification
from ham.outbox.models import OutboxEvent
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now
from ham.requests.models import UrgencyReview
from ham.requests.notifications import (
    _build_decision_emails,
    _build_decision_notices,
    _build_decision_undone_notices,
    _build_question_answered_emails,
    _build_question_answered_notices,
    _build_reconsideration_emails,
    _build_reconsideration_notices,
    _build_urgency_not_certified_notices,
    _build_urgency_review_undone_notices,
    _build_urgent_approval_emails,
    _build_urgent_approval_notices,
)
from ham.requests.services import complete_intake_checks, submit_request
from ham.requests.services_decisions import (
    approve_request,
    reject_request,
    request_reconsideration,
    review_urgency,
    undo_decision,
)
from ham.requests.services_questions import answer_question, ask_question

from .conftest import actor_ctx, make_payload

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


def _submitted(requester_ctx, **overrides):
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


@pytest.fixture
def requester_ctx():
    return RequesterContext(request_id=None)


@pytest.fixture
def system_ctx():
    from ham.authz.context import SystemContext

    return SystemContext()


def _awaiting(requester_ctx, system_ctx, **overrides):
    req = _submitted(requester_ctx, **overrides)
    complete_intake_checks(system_ctx, request_id=req.id)
    req.refresh_from_db()
    return req


def _pastor_ctx_with_user(make_user, email="ruth@example.org"):
    user = make_user(email)
    _grant(user, roles.PASTOR)
    return user, actor_ctx(roles=frozenset({roles.PASTOR}), user_id=user.id)


class TestDecisionNoticesNotUrgent:
    def test_dir_ad_and_other_approvers_get_the_update_not_the_decider(
        self, requester_ctx, system_ctx, make_user
    ):
        deciding_pastor, pastor_ctx = _pastor_ctx_with_user(make_user, "ruth@example.org")
        other_pastor = make_user("ken@example.org")
        _grant(other_pastor, roles.PASTOR)
        board = make_user("marcus@example.org")
        _grant(board, roles.BOARD_REPRESENTATIVE)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

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
        notices = _build_decision_notices(event)
        assert notices is not None
        recipients = {n.recipient_user_id for n in notices}
        assert recipients == {other_pastor.id, board.id, director.id}
        assert deciding_pastor.id not in recipients
        assert all("Approved" in n.title for n in notices)

    def test_approval_email_goes_to_dir_ad_per_preference(
        self, requester_ctx, system_ctx, make_user
    ):
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        assistant = make_user("owen@example.org")
        _grant(assistant, roles.ASSISTANT_DIRECTOR)
        SharedIdentityProfile.objects.create(user=assistant, notify_email=False)

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
        emails = _build_decision_emails(event)
        assert emails is not None
        assert {e.to for e in emails} == {"nadia@example.org"}

    def test_rejection_gets_no_email(self, requester_ctx, system_ctx, make_user):
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        req = _awaiting(requester_ctx, system_ctx)
        reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="couldnt_confirm",
            message="message",
        )
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
        assert _build_decision_emails(event) is None
        notices = _build_decision_notices(event)
        assert notices is not None
        assert all("Not approved" in n.title for n in notices)


class TestUrgentApproval:
    def test_dir_ad_get_email_and_must_ack_banner_regardless_of_preference(
        self, requester_ctx, system_ctx, make_user
    ):
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        SharedIdentityProfile.objects.create(user=director, notify_email=False)

        req = _awaiting(
            requester_ctx,
            system_ctx,
            urgent_requested=True,
            urgency_reason="someone_could_get_hurt",
        )
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True
        )
        assert approval.urgent_approval is True
        event = _event(
            "RequestUrgentApproval",
            aggregate_id=req.id,
            payload={"request_id": str(req.id), "approval_id": str(approval.id)},
        )
        emails = _build_urgent_approval_emails(event)
        assert emails is not None
        assert {e.to for e in emails} == {"nadia@example.org"}  # regardless of notify_email

        notices = _build_urgent_approval_notices(event)
        assert notices is not None
        assert all(n.urgent and n.requires_ack for n in notices)
        assert {n.recipient_user_id for n in notices} == {director.id}

    def test_approve_request_emits_the_alert_exactly_once(
        self, requester_ctx, system_ctx, make_user
    ):
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)
        req = _awaiting(
            requester_ctx,
            system_ctx,
            urgent_requested=True,
            urgency_reason="someone_could_get_hurt",
        )
        approve_request(pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True)
        assert OutboxEvent.objects.filter(event_type="RequestUrgentApproval").count() == 1

    def test_certify_after_board_approval_emits_the_alert_exactly_once(
        self, requester_ctx, system_ctx, make_user
    ):
        board = make_user("marcus@example.org")
        _grant(board, roles.BOARD_REPRESENTATIVE)
        board_ctx = actor_ctx(roles=frozenset({roles.BOARD_REPRESENTATIVE}), user_id=board.id)
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)

        req = _awaiting(
            requester_ctx,
            system_ctx,
            urgent_requested=True,
            urgency_reason="someone_could_get_hurt",
        )
        approval = approve_request(board_ctx, request_id=req.id, route="board")
        assert not OutboxEvent.objects.filter(event_type="RequestUrgentApproval").exists()
        # Security M2: `review_urgency` refuses while the Board approval it's certifying is
        # still undoable.
        set_clock(FixedClock(approval.effective_at))
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        assert OutboxEvent.objects.filter(event_type="RequestUrgentApproval").count() == 1

    def test_undo_of_the_urgent_approval_gets_the_follow_up(
        self, requester_ctx, system_ctx, make_user
    ):
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        req = _awaiting(
            requester_ctx,
            system_ctx,
            urgent_requested=True,
            urgency_reason="someone_could_get_hurt",
        )
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True
        )
        undo_decision(pastor_ctx, approval_id=approval.id)
        event = _event(
            "RequestDecisionUndone",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "approval_id": str(approval.id),
                "stage": "initial",
            },
        )
        notices = _build_decision_undone_notices(event)
        assert notices is not None
        # UX M9: the Director/AD "undone" follow-up, PLUS the pastors' "needs a pastor"
        # banner restored -- the request is back to Awaiting Approval with urgency awaiting
        # certification again, exactly the state that banner describes.
        assert {n.recipient_user_id for n in notices} == {director.id, _deciding.id}
        undone_notices = [n for n in notices if n.kind == "request_urgent_approval_undone"]
        assert undone_notices and "undone" in undone_notices[0].title.lower()
        restored = [n for n in notices if n.kind == "request_awaiting_approval"]
        assert restored and restored[0].recipient_user_id == _deciding.id
        assert restored[0].urgent is True

    def test_undo_of_a_non_urgent_approval_gets_no_follow_up(
        self, requester_ctx, system_ctx, make_user
    ):
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        req = _awaiting(requester_ctx, system_ctx)
        approval = approve_request(pastor_ctx, request_id=req.id, route="pastoral")
        undo_decision(pastor_ctx, approval_id=approval.id)
        event = _event(
            "RequestDecisionUndone",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "approval_id": str(approval.id),
                "stage": "initial",
            },
        )
        assert _build_decision_undone_notices(event) is None

    def test_undo_of_a_standalone_certification_gets_the_follow_up(
        self, requester_ctx, system_ctx, make_user
    ):
        board = make_user("marcus@example.org")
        _grant(board, roles.BOARD_REPRESENTATIVE)
        board_ctx = actor_ctx(roles=frozenset({roles.BOARD_REPRESENTATIVE}), user_id=board.id)
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        req = _awaiting(
            requester_ctx,
            system_ctx,
            urgent_requested=True,
            urgency_reason="someone_could_get_hurt",
        )
        approval = approve_request(board_ctx, request_id=req.id, route="board")
        set_clock(FixedClock(approval.effective_at))
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        review = UrgencyReview.objects.get(request_id=req.id)
        undo_decision(pastor_ctx, review_id=review.id)

        event = _event(
            "RequestUrgencyReviewUndone",
            aggregate_id=req.id,
            payload={"request_id": str(req.id), "review_id": str(review.id)},
        )
        notices = _build_urgency_review_undone_notices(event)
        assert notices is not None
        assert {n.recipient_user_id for n in notices} == {director.id}


class TestReconsiderationRequested:
    def test_pastoral_route_goes_to_the_original_decider_plus_dir_ad(
        self, requester_ctx, system_ctx, make_user
    ):
        deciding_pastor, pastor_ctx = _pastor_ctx_with_user(make_user)
        other_pastor = make_user("ken@example.org")
        _grant(other_pastor, roles.PASTOR)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        req = _awaiting(requester_ctx, system_ctx)
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="couldnt_confirm",
            message="message",
        )
        req.refresh_from_db()
        # Security M1/Q-181: refused while the decline can still be undone.
        set_clock(FixedClock(approval.effective_at))
        result = request_reconsideration(RequesterContext(request_id=req.id), note="please")
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
        notices = _build_reconsideration_notices(event)
        assert notices is not None
        recipients = {n.recipient_user_id for n in notices}
        assert deciding_pastor.id in recipients
        assert director.id in recipients
        assert other_pastor.id not in recipients

    def test_pastoral_route_falls_back_to_every_pastor_when_original_lost_the_role(
        self, requester_ctx, system_ctx, make_user
    ):
        deciding_pastor, pastor_ctx = _pastor_ctx_with_user(make_user)
        other_pastor = make_user("ken@example.org")
        _grant(other_pastor, roles.PASTOR)

        req = _awaiting(requester_ctx, system_ctx)
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="couldnt_confirm",
            message="message",
        )
        req.refresh_from_db()
        RoleAssignment.objects.filter(user=deciding_pastor, role=roles.PASTOR).update(
            revoked_at=clock_now()
        )
        set_clock(FixedClock(approval.effective_at))
        result = request_reconsideration(RequesterContext(request_id=req.id), note="please")
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
        notices = _build_reconsideration_notices(event)
        assert notices is not None
        recipients = {n.recipient_user_id for n in notices}
        assert other_pastor.id in recipients

    def test_board_route_goes_to_every_board_rep(self, requester_ctx, system_ctx, make_user):
        board = make_user("marcus@example.org")
        _grant(board, roles.BOARD_REPRESENTATIVE)
        board_ctx = actor_ctx(roles=frozenset({roles.BOARD_REPRESENTATIVE}), user_id=board.id)

        req = _awaiting(requester_ctx, system_ctx)
        approval = reject_request(
            board_ctx,
            request_id=req.id,
            route="board",
            reason_code="couldnt_confirm",
            message="message",
        )
        req.refresh_from_db()
        set_clock(FixedClock(approval.effective_at))
        result = request_reconsideration(RequesterContext(request_id=req.id), note="please")
        event = _event(
            "ReconsiderationRequested",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "reconsideration_id": str(result.id),
                "route": "board",
                "via": "secure_page",
            },
        )
        notices = _build_reconsideration_notices(event)
        assert notices is not None
        assert board.id in {n.recipient_user_id for n in notices}
        emails = _build_reconsideration_emails(event)
        assert emails is not None
        assert {e.to for e in emails} == {"marcus@example.org"}


class TestQuestionAnswered:
    def test_asker_only(self, requester_ctx, system_ctx, make_user):
        asker = make_user("ruth@example.org")
        _grant(asker, roles.PASTOR)
        other = make_user("ken@example.org")
        _grant(other, roles.PASTOR)
        asker_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=asker.id)

        req = _awaiting(requester_ctx, system_ctx)
        question = ask_question(asker_ctx, request_id=req.id, question="Detail?")
        answer_question(RequesterContext(request_id=req.id), question_id=question.id, answer="Yes")
        event = _event(
            "RequesterQuestionAnswered",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "question_id": str(question.id),
                "via": "secure_page",
            },
        )
        notices = _build_question_answered_notices(event)
        assert notices is not None
        assert {n.recipient_user_id for n in notices} == {asker.id}

        emails = _build_question_answered_emails(event)
        assert emails is not None
        assert {e.to for e in emails} == {"ruth@example.org"}


class TestUrgentBannerClearing:
    def test_not_certified_clears_the_banner_for_every_pastor(
        self, requester_ctx, system_ctx, make_user
    ):
        pastor1 = make_user("ruth@example.org")
        _grant(pastor1, roles.PASTOR)
        pastor2 = make_user("ken@example.org")
        _grant(pastor2, roles.PASTOR)
        req = _awaiting(
            requester_ctx,
            system_ctx,
            urgent_requested=True,
            urgency_reason="someone_could_get_hurt",
        )
        for pastor in (pastor1, pastor2):
            Notification.objects.create(
                id=uuid.uuid4(),
                recipient_user_id=pastor.id,
                kind="request_awaiting_approval",
                subject_type="request",
                subject_id=req.id,
                title="Urgent request needs a pastor",
                urgent=True,
                requires_ack=True,
            )
        actor = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=pastor1.id)
        review_urgency(actor, request_id=req.id, certify=False)
        event = _event(
            "UrgencyNotCertified", aggregate_id=req.id, payload={"request_id": str(req.id)}
        )
        _build_urgency_not_certified_notices(event)

        for pastor in (pastor1, pastor2):
            notif = Notification.objects.get(recipient_user_id=pastor.id, subject_id=req.id)
            assert notif.acknowledged_at is not None


class TestAdministratorNeverIncluded:
    def test_administrator_role_never_appears(self, requester_ctx, system_ctx, make_user):
        admin = make_user("kevin@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)

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
        notices = _build_decision_notices(event) or []
        assert admin.id not in {n.recipient_user_id for n in notices}
        emails = _build_decision_emails(event) or []
        assert admin.id not in {getattr(e, "to", None) for e in emails}


class TestPIIFreeTitlesAndSubjects:
    def test_no_pii_in_leadership_titles_or_subjects(self, requester_ctx, system_ctx, make_user):
        _deciding, pastor_ctx = _pastor_ctx_with_user(make_user)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        req = _awaiting(
            requester_ctx,
            system_ctx,
            urgent_requested=True,
            urgency_reason="someone_could_get_hurt",
        )
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True
        )
        decided_event = _event(
            "RequestApproved",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "stage": approval.stage,
                "route": approval.route,
                "urgent_approval": True,
            },
        )
        urgent_event = _event(
            "RequestUrgentApproval",
            aggregate_id=req.id,
            payload={"request_id": str(req.id), "approval_id": str(approval.id)},
        )
        texts = []
        for notice in _build_decision_notices(decided_event) or []:
            texts.append(notice.title)
        for notice in _build_urgent_approval_notices(urgent_event) or []:
            texts.append(notice.title)
        for email in _build_urgent_approval_emails(urgent_event) or []:
            texts.append(email.subject)

        forbidden = (DISTINCTIVE_NAME, DISTINCTIVE_STREET, DISTINCTIVE_PHONE, DISTINCTIVE_EMAIL)
        for text in texts:
            for bad in forbidden:
                assert bad not in text
