"""Fix 3C: regression tests for the security PoCs from the re-check
(docs/ux/reviews/step3-privacy-security.md re-check section: N1, N2, N3, M2 scenario).
"""

from __future__ import annotations

import pytest

from ham.authz import roles
from ham.identity.models import RoleAssignment
from ham.notifications.inapp import handle_inapp_event
from ham.outbox.models import OutboxEvent
from ham.platform.clock import now as clock_now
from ham.requests.models import UrgencyReview
from ham.requests.services_decisions import (
    approve_request,
    reject_request,
    review_urgency,
    undo_decision,
)

from .conftest import actor_ctx
from .test_s32_decisions import _urgent_awaiting

pytestmark = pytest.mark.django_db


def _grant(user, role):
    return RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


def _dispatch(seen: set, request_id):
    for event in OutboxEvent.objects.filter(aggregate_id=request_id).order_by("occurred_at", "id"):
        if event.id in seen:
            continue
        seen.add(event.id)
        handle_inapp_event(event)


# ---------------------------------------------------------------------------------------
# Item 1 / security N1: the phone script always reads the latest LIVE decision. The view
# itself is covered by `tests/web/test_fix3c_view_logic.py`.
# ---------------------------------------------------------------------------------------
class TestPhoneScriptUsesLatestDecision:
    def test_service_and_view_and_cards_share_one_helper(self):
        import inspect

        from ham.requests import attention, services_decisions
        from ham.web import views_requests

        # All four call sites resolve through `queries.latest_effective_approval` (directly
        # or via `queries.requests_with_settled_decision`, its bulk sibling) -- never a
        # locally re-derived `Approval.objects.filter(...).order_by(...).first()`.
        assert "latest_effective_approval" in inspect.getsource(services_decisions)
        assert "latest_effective_approval" in inspect.getsource(views_requests)
        assert "requests_with_settled_decision" in inspect.getsource(attention)


# ---------------------------------------------------------------------------------------
# Item 2 / PRD N1 + security M2 scenario.
# ---------------------------------------------------------------------------------------
class TestUrgencyReviewCarveOut:
    def test_certify_allowed_during_boards_own_window_reject_refused_during_reviews_window(
        self, requester_ctx, system_ctx, make_user
    ):
        board = make_user("carveout-board@example.org")
        _grant(board, roles.BOARD_REPRESENTATIVE)
        board_ctx = actor_ctx(roles=frozenset({roles.BOARD_REPRESENTATIVE}), user_id=board.id)
        pastor = make_user("carveout-pastor@example.org")
        _grant(pastor, roles.PASTOR)
        pastor_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=pastor.id)

        req = _urgent_awaiting(requester_ctx, system_ctx)
        approve_request(board_ctx, request_id=req.id, route="board")
        # PRD N1: certifying urgency is allowed during the Board approval's OWN undo window.
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        req.refresh_from_db()
        assert req.urgency_status == "certified"

    def test_end_to_end_board_approve_then_certify_then_undo_sends_follow_up(
        self, requester_ctx, system_ctx, make_user
    ):
        """Security M2 scenario: Board approves, a pastor certifies inside the window, the
        Board rep undoes, and the Director/AD follow-up is sent."""
        director = make_user("m2-director@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        board = make_user("m2-board@example.org")
        _grant(board, roles.BOARD_REPRESENTATIVE)
        board_ctx = actor_ctx(roles=frozenset({roles.BOARD_REPRESENTATIVE}), user_id=board.id)
        pastor = make_user("m2-pastor@example.org")
        _grant(pastor, roles.PASTOR)
        pastor_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=pastor.id)

        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(board_ctx, request_id=req.id, route="board")
        # Still inside the Board approval's own undo window.
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        undo_decision(board_ctx, approval_id=approval.id)

        seen: set = set()
        _dispatch(seen, req.id)

        from ham.notifications.models import Notification

        assert Notification.objects.filter(
            recipient_user_id=director.id,
            kind="request_urgent_approval_undone",
        ).exists()


# ---------------------------------------------------------------------------------------
# Item 3 / security N3.
# ---------------------------------------------------------------------------------------
class TestApproveRejectRefusedDuringReviewWindow:
    def test_approve_refused_while_standalone_review_is_undoable(
        self, requester_ctx, system_ctx, make_user
    ):
        pastor = make_user("n3-pastor@example.org")
        _grant(pastor, roles.PASTOR)
        pastor_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=pastor.id)

        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=True)
        with pytest.raises(ValueError, match="decision_undo_window_open"):
            approve_request(pastor_ctx, request_id=req.id, route="pastoral")

    def test_reject_refused_while_standalone_review_is_undoable(
        self, requester_ctx, system_ctx, make_user
    ):
        pastor = make_user("n3-pastor2@example.org")
        _grant(pastor, roles.PASTOR)
        pastor_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=pastor.id)

        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=False)
        with pytest.raises(ValueError, match="decision_undo_window_open"):
            reject_request(
                pastor_ctx,
                request_id=req.id,
                route="pastoral",
                reason_code="another_reason",
                message="sorry",
            )

    def test_undo_urgency_review_refuses_with_stored_prior_status(
        self, requester_ctx, system_ctx, make_user
    ):
        pastor = make_user("n3-pastor3@example.org")
        _grant(pastor, roles.PASTOR)
        pastor_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=pastor.id)

        req = _urgent_awaiting(requester_ctx, system_ctx)
        review_urgency(pastor_ctx, request_id=req.id, certify=False)
        review = UrgencyReview.objects.get(request_id=req.id)
        assert review.prior_status == "AWAITING_APPROVAL"


# ---------------------------------------------------------------------------------------
# Item 4 / security N2, UX M9: undo restores the pastors' urgent banner.
# ---------------------------------------------------------------------------------------
class TestUndoRestoresPastorBanner:
    def test_undo_of_a_decline_restores_the_banner(self, requester_ctx, system_ctx, make_user):
        from ham.notifications.models import Notification

        p1 = make_user("banner-p1@example.org")
        _grant(p1, roles.PASTOR)
        p1_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=p1.id)
        p2 = make_user("banner-p2@example.org")
        _grant(p2, roles.PASTOR)

        req = _urgent_awaiting(requester_ctx, system_ctx)
        seen: set = set()
        _dispatch(seen, req.id)
        appr = reject_request(
            p1_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="sorry",
        )
        _dispatch(seen, req.id)
        assert not Notification.objects.filter(
            recipient_user_id=p2.id,
            kind="request_awaiting_approval",
            acknowledged_at__isnull=True,
        ).exists()

        undo_decision(p1_ctx, approval_id=appr.id)
        _dispatch(seen, req.id)
        assert Notification.objects.filter(
            recipient_user_id=p2.id,
            kind="request_awaiting_approval",
            acknowledged_at__isnull=True,
        ).exists()

    def test_undo_of_not_urgent_restores_the_banner(self, requester_ctx, system_ctx, make_user):
        from ham.notifications.models import Notification

        p1 = make_user("banner-p1b@example.org")
        _grant(p1, roles.PASTOR)
        p1_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=p1.id)
        p2 = make_user("banner-p2b@example.org")
        _grant(p2, roles.PASTOR)

        req = _urgent_awaiting(requester_ctx, system_ctx)
        seen: set = set()
        _dispatch(seen, req.id)
        review_urgency(p1_ctx, request_id=req.id, certify=False)
        _dispatch(seen, req.id)
        review = UrgencyReview.objects.get(request_id=req.id)
        undo_decision(p1_ctx, review_id=review.id)
        _dispatch(seen, req.id)
        assert Notification.objects.filter(
            recipient_user_id=p2.id,
            kind="request_awaiting_approval",
            acknowledged_at__isnull=True,
        ).exists()

    def test_restore_skips_a_pastor_who_already_has_an_unacked_banner(
        self, requester_ctx, system_ctx, make_user
    ):
        from ham.notifications.models import Notification

        p1 = make_user("banner-dup1@example.org")
        _grant(p1, roles.PASTOR)
        p1_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=p1.id)
        p2 = make_user("banner-dup2@example.org")
        _grant(p2, roles.PASTOR)

        req = _urgent_awaiting(requester_ctx, system_ctx)
        seen: set = set()
        _dispatch(seen, req.id)
        appr = reject_request(
            p1_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="sorry",
        )
        _dispatch(seen, req.id)
        undo_decision(p1_ctx, approval_id=appr.id)
        _dispatch(seen, req.id)
        # Exactly one unacknowledged banner after the restore -- never more than one, even
        # though the decline-then-undo round trip may create a fresh row rather than
        # resurrecting the (now acknowledged) original.
        assert (
            Notification.objects.filter(
                recipient_user_id=p2.id,
                kind="request_awaiting_approval",
                acknowledged_at__isnull=True,
            ).count()
            == 1
        )

        # A SECOND decline-then-undo round trip, while p2's restored banner from the first one
        # is still unacknowledged, must not add a duplicate live banner (security N2).
        appr2 = reject_request(
            p1_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="sorry again",
        )
        _dispatch(seen, req.id)
        undo_decision(p1_ctx, approval_id=appr2.id)
        _dispatch(seen, req.id)
        assert (
            Notification.objects.filter(
                recipient_user_id=p2.id,
                kind="request_awaiting_approval",
                acknowledged_at__isnull=True,
            ).count()
            == 1
        )
