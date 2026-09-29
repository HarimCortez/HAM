"""Regression (step-3 test pass, fixed in FIX-3A): the Director/AD "urgent approval was undone"
follow-up for a standalone urgency certification must not depend on the request's *current*
status. FIX-3A stores `UrgencyReview.urgent_approval_emitted` at review time, and
`_build_urgency_review_undone_notices` keys on that stored fact (Q-176).

Scenario: a Board-approved urgent request is certified by a pastor (the urgent alert fires),
then cancelled as "requester withdrew" (Q-165), then the pastor undoes the certification
within its window. The request is no longer APPROVED, yet Director/AD must still be told the
urgent approval was undone.
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.platform.clock import now as clock_now
from ham.requests.models import UrgencyReview
from ham.requests.notifications import _build_urgency_review_undone_notices
from ham.requests.services import cancel_request, complete_intake_checks, submit_request
from ham.requests.services_decisions import approve_request, review_urgency, undo_decision
from ham.rules import RULES

from .conftest import actor_ctx, make_payload

pytestmark = pytest.mark.django_db


def _grant(user, role):
    return RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


def _event(event_type: str, *, aggregate_id, payload: dict):
    from ham.outbox.models import OutboxEvent
    from ham.platform.ids import uuid7

    return OutboxEvent.objects.create(
        id=uuid7(),
        event_type=event_type,
        schema_version=1,
        occurred_at=clock_now(),
        aggregate_type="request",
        aggregate_id=aggregate_id,
        payload=payload,
    )


def test_status_change_between_review_and_undo_swallows_the_urgent_follow_up(make_user):
    from ham.authz.context import RequesterContext, SystemContext

    requester_ctx = RequesterContext(request_id=None)
    system_ctx = SystemContext()

    board = make_user("marcus.weakspot@example.org")
    _grant(board, roles.BOARD_REPRESENTATIVE)
    board_ctx = actor_ctx(roles=frozenset({roles.BOARD_REPRESENTATIVE}), user_id=board.id)

    pastor = make_user("ruth.weakspot@example.org")
    _grant(pastor, roles.PASTOR)
    pastor_ctx = actor_ctx(roles=frozenset({roles.PASTOR}), user_id=pastor.id)

    director = make_user("nadia.weakspot@example.org")
    _grant(director, roles.HAM_DIRECTOR)
    SharedIdentityProfile.objects.create(user=director)
    director_ctx = actor_ctx(roles=frozenset({roles.HAM_DIRECTOR}), user_id=director.id)

    req = submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(urgent_requested=True, urgency_reason="someone_could_get_hurt"),
    )
    complete_intake_checks(system_ctx, request_id=req.id)
    req.refresh_from_db()

    # Board approves (urgency stays "awaiting certification", Q-160/Q-161).
    board_approval = approve_request(board_ctx, request_id=req.id, route="board")

    # A pastor certifies later, once the *Board approval's own* undo window has already
    # elapsed (a real church workflow: certification can happen any time while Approved,
    # Q-177) -- this is what makes the later cancel legal (`cancel_request` refuses while any
    # decision can still be undone).
    from ham.platform.clock import FixedClock, set_clock

    set_clock(FixedClock(board_approval.decided_at + RULES.approvals.DECISION_UNDO_WINDOW * 2))
    review_urgency(pastor_ctx, request_id=req.id, certify=True)
    review = UrgencyReview.objects.get(request_id=req.id)
    req.refresh_from_db()
    assert req.status == "APPROVED"

    # Something else changes the request's status before the pastor undoes the
    # certification -- here, a legitimate Q-165 "requester withdrew" cancel, still comfortably
    # inside the certification's own 30-minute undo window.
    cancel_request(director_ctx, request_id=req.id, reason_code="requester_withdrew")
    req.refresh_from_db()
    assert req.status == "CANCELLED"

    # The pastor undoes the certification -- a genuine undo of a real, already-alerted urgent
    # approval (Q-176: "on undo they get an in-app ... follow-up").
    undo_decision(pastor_ctx, review_id=review.id)

    event = _event(
        "RequestUrgencyReviewUndone",
        aggregate_id=req.id,
        payload={"request_id": str(req.id), "review_id": str(review.id)},
    )
    notices = _build_urgency_review_undone_notices(event)

    # This is the bug: Director/AD get NO follow-up at all, because the builder's own
    # "was this an urgent approval" check re-reads the request's *current* status (now
    # CANCELLED) instead of a fact stored on the review at certification time.
    assert notices is not None, (
        "false negative confirmed: the undo of a genuinely-alerted urgent certification "
        "produced no Director/AD follow-up notice once the request's status changed "
        "between the certification and the undo (ham/requests/notifications.py "
        "_build_urgency_review_undone_notices, ~line 453)"
    )
    assert {n.recipient_user_id for n in notices} == {director.id}
