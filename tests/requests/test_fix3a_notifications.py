"""FIX-3A notifications: H1 (`_clear_urgent_banner` scoping), security M2 (the
`urgent_approval_emitted` stored fact), and PRD guardian M8 (no in-app "Not urgent" update).
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.identity.models import RoleAssignment
from ham.notifications.models import Notification
from ham.outbox.models import OutboxEvent
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now
from ham.requests.models import UrgencyReview
from ham.requests.notifications import (
    _build_decision_undone_notices,
    _build_urgency_certified_notices,
    _build_urgency_not_certified_notices,
    _clear_urgent_banner,
)
from ham.requests.services_decisions import approve_request, review_urgency, undo_decision

from .test_s32_decisions import _urgent_awaiting

pytestmark = pytest.mark.django_db


def _grant(user, role):
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


def _event(event_type: str, *, aggregate_id, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type, aggregate_type="request", aggregate_id=aggregate_id, payload=payload
    )


class TestH1ClearUrgentBannerScoping:
    """Security H1: `_clear_urgent_banner` must clear only the pastors' own
    `request_awaiting_approval` must-ack banner -- never `request_urgent_approval` (the
    Director/AD alert), and never a non-pastor recipient."""

    def test_never_acknowledges_the_urgent_approval_banner(self, make_user):
        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        request_id = uuid.uuid4()

        pastor_banner = Notification.objects.create(
            recipient_user_id=pastor.id,
            kind="request_awaiting_approval",
            subject_type="request",
            subject_id=request_id,
            title="Urgent request needs a pastor",
            requires_ack=True,
        )
        director_banner = Notification.objects.create(
            recipient_user_id=director.id,
            kind="request_urgent_approval",
            subject_type="request",
            subject_id=request_id,
            title="Urgent request approved",
            requires_ack=True,
        )

        _clear_urgent_banner(request_id)

        pastor_banner.refresh_from_db()
        director_banner.refresh_from_db()
        assert pastor_banner.acknowledged_at is not None
        assert director_banner.acknowledged_at is None

    def test_never_clears_a_non_pastor_recipients_row_of_the_same_kind(self, make_user):
        # A row of the SAME kind but for someone who isn't a pastor (e.g. a stray/legacy row)
        # must not be touched either -- the scoping is by recipient, not just by kind.
        board = make_user("marcus@example.org")
        _grant(board, roles.BOARD_REPRESENTATIVE)
        request_id = uuid.uuid4()
        row = Notification.objects.create(
            recipient_user_id=board.id,
            kind="request_awaiting_approval",
            subject_type="request",
            subject_id=request_id,
            title="Request waiting for review",
            requires_ack=True,
        )
        _clear_urgent_banner(request_id)
        row.refresh_from_db()
        assert row.acknowledged_at is None

    def test_both_emit_orders_leave_the_urgent_approval_banner_intact(
        self, requester_ctx, system_ctx, pastor_ctx, board_rep_ctx, make_user
    ):
        """H1's own repro: whichever order `RequestUrgentApproval` and `UrgencyCertified`
        are dispatched in, the Director/AD alert must survive `_build_urgency_certified_
        notices`'s banner-clearing side effect."""
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        # Order A: certify bundled with the approval itself (`certify_urgent=True`) --
        # `RequestUrgentApproval` and `UrgencyCertified` both fire from the same call.
        req_a = _urgent_awaiting(requester_ctx, system_ctx)
        approval_a = approve_request(
            pastor_ctx, request_id=req_a.id, route="pastoral", certify_urgent=True
        )
        alert_event_a = _event(
            "RequestUrgentApproval",
            aggregate_id=req_a.id,
            payload={"request_id": str(req_a.id), "approval_id": str(approval_a.id)},
        )
        from ham.requests.notifications import _build_urgent_approval_notices

        alert_notices_a = _build_urgent_approval_notices(alert_event_a)
        assert alert_notices_a is not None
        Notification.objects.bulk_create(
            [
                Notification(
                    recipient_user_id=n.recipient_user_id,
                    kind=n.kind,
                    subject_type=n.subject_type,
                    subject_id=n.subject_id,
                    title=n.title,
                    requires_ack=n.requires_ack,
                )
                for n in alert_notices_a
            ]
        )
        certified_event_a = _event(
            "UrgencyCertified", aggregate_id=req_a.id, payload={"request_id": str(req_a.id)}
        )
        _build_urgency_certified_notices(certified_event_a)
        banner_a = Notification.objects.get(
            subject_id=req_a.id, kind="request_urgent_approval", recipient_user_id=director.id
        )
        assert banner_a.acknowledged_at is None

        # Order B: certify AFTER an earlier Board approval (`review_urgency` standalone) --
        # `RequestUrgentApproval` is hand-emitted before the decorator's own `UrgencyCertified`.
        req_b = _urgent_awaiting(requester_ctx, system_ctx)
        approval_b = approve_request(board_rep_ctx, request_id=req_b.id, route="board")
        set_clock(FixedClock(approval_b.effective_at))
        review_urgency(pastor_ctx, request_id=req_b.id, certify=True)
        alert_event_b = _event(
            "RequestUrgentApproval",
            aggregate_id=req_b.id,
            payload={"request_id": str(req_b.id), "approval_id": str(approval_b.id)},
        )
        alert_notices_b = _build_urgent_approval_notices(alert_event_b)
        assert alert_notices_b is not None
        Notification.objects.bulk_create(
            [
                Notification(
                    recipient_user_id=n.recipient_user_id,
                    kind=n.kind,
                    subject_type=n.subject_type,
                    subject_id=n.subject_id,
                    title=n.title,
                    requires_ack=n.requires_ack,
                )
                for n in alert_notices_b
            ]
        )
        certified_event_b = _event(
            "UrgencyCertified", aggregate_id=req_b.id, payload={"request_id": str(req_b.id)}
        )
        _build_urgency_certified_notices(certified_event_b)
        banner_b = Notification.objects.get(
            subject_id=req_b.id, kind="request_urgent_approval", recipient_user_id=director.id
        )
        assert banner_b.acknowledged_at is None


class TestSecurityM2StoredFact:
    """Security M2: the Q-176 "urgent approval was undone" follow-up is keyed on the stored
    `urgent_approval_emitted` fact, never on re-reading the request's live status."""

    def test_approval_stores_the_fact_at_creation(self, requester_ctx, system_ctx, pastor_ctx):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True
        )
        approval.refresh_from_db()
        assert approval.urgent_approval_emitted is True

    def test_standalone_review_stores_the_fact_at_creation(
        self, requester_ctx, system_ctx, pastor_ctx, board_rep_ctx
    ):
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(board_rep_ctx, request_id=req.id, route="board")
        set_clock(FixedClock(approval.effective_at))
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        review = UrgencyReview.objects.get(request_id=req.id)
        assert review.urgent_approval_emitted is True

    def test_undo_follow_up_fires_even_after_the_request_status_has_moved_on(
        self, requester_ctx, system_ctx, pastor_ctx, make_user
    ):
        """The exact gap the live-status version had: something else changes the request's
        status between the certification and the undo, and the old `_build_urgency_review_
        undone_notices` (which checked `request.status == APPROVED`) would then wrongly find
        nothing. The stored fact doesn't care what the status is now."""
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(
            pastor_ctx, request_id=req.id, route="pastoral", certify_urgent=True
        )
        undo_decision(pastor_ctx, approval_id=approval.id)
        # The request is no longer APPROVED at all -- back to AWAITING_APPROVAL.
        req.refresh_from_db()
        assert req.status != "APPROVED"
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
        assert any(n.recipient_user_id == director.id for n in notices)


class TestPRDGuardianM8NoInAppNotUrgentUpdate:
    """PRD guardian M8 (owner box): "Not urgent" sends no in-app update at all, beyond the
    silent pastors' banner clear."""

    def test_declining_urgency_sends_no_notice_to_anyone(
        self, requester_ctx, system_ctx, pastor_ctx, make_user
    ):
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=False)
        event = _event(
            "UrgencyNotCertified", aggregate_id=req.id, payload={"request_id": str(req.id)}
        )
        assert _build_urgency_not_certified_notices(event) is None
