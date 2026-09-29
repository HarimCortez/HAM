"""Regression (step-3 test pass; FIX-3A then Fix 3C / security N3): a standalone urgency
review's undo must refuse once the request's status has changed since the review, instead of
silently restoring urgency onto a request that has since moved on entirely (e.g. been
cancelled). `UrgencyReview.prior_status` (Fix 3C) is exactly the stored fact `check_undo`
compares against, so this never depends on re-reading the request's *current* status at undo
time.

Scenario: a Board-approved urgent request is certified by a pastor (the urgent alert fires),
then cancelled as "requester withdrew" (Q-165), then the pastor tries to undo the
certification within its window.
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.platform.clock import now as clock_now
from ham.requests.models import UrgencyReview
from ham.requests.services import cancel_request, complete_intake_checks, submit_request
from ham.requests.services_decisions import approve_request, review_urgency, undo_decision
from ham.rules import RULES

from .conftest import actor_ctx, make_payload

pytestmark = pytest.mark.django_db


def _grant(user, role):
    return RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


def test_undo_refuses_once_status_changed_between_review_and_undo(make_user):
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

    # Fix 3C / security N3: the pastor's undo of the certification now refuses outright --
    # `UrgencyReview.prior_status` ("APPROVED") no longer matches the request's current
    # status ("CANCELLED"), so `check_undo` returns `state_changed_since_decision` instead of
    # silently restoring urgency onto a request that has since moved on entirely. (Before this
    # fix, the undo would have succeeded and the *notification builder* alone had the bug this
    # test used to document -- see the module docstring's history above; the state-change
    # guard now catches the scenario one layer earlier, at the undo itself.)
    with pytest.raises(ValueError, match="state_changed_since_decision"):
        undo_decision(pastor_ctx, review_id=review.id)
