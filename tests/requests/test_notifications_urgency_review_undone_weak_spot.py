"""Bug-pin (test-engineer pass, step 3): `ham/requests/notifications.py::
_build_urgency_review_undone_notices` (lines ~431-441) reconstructs "was this the
certification that made the request an urgent approval" at *undo* time, from `review.action`
plus the request's *current* status (`status is not RequestStatus.APPROVED -> return None`,
line 453) -- not from a fact stored on the `UrgencyReview` row itself at review time. The
function's own docstring already flags this as a `PRD-GAP Q-176` and predicts the exact
failure mode: "unless something else changed the request's status between the review and this
undo ... which would read as a false negative here."

This file proves that prediction for real: a Board-approved, later-certified urgent request,
cancelled (Q-165: "requester withdrew", allowed from Approved once the *Approval's own* undo
window has closed) *after* the certification but *before* the certifying pastor undoes it.
The undo is genuine -- the urgent alert really did fire, Director/AD really were paged -- but
because the request's status is no longer `APPROVED` by the time the undo happens, the
in-app "urgent approval was undone" follow-up silently never reaches them.

Severity: Medium. Not a security/privacy hole and not data corruption (the `UrgencyReview`
row itself is still recorded correctly, `undone_at` and all) -- but it is a silent notification
loss for a safety-relevant alert (§10, Q-176's "on undo they get an in-app ... follow-up" is
supposed to be unconditional on the undo itself, not on what happened to the request
afterward). A pastor could reasonably undo a mistaken urgent certification believing
Director/AD will be told "never mind", and they won't be.

Suggested fix (already named by the code's own docstring, not invented here): persist the
fact on `UrgencyReview` at review time, the same way `Approval.urgent_approval` is persisted
on the `Approval` row itself rather than re-derived later -- e.g. an
`UrgencyReview.became_urgent_approval` boolean, set once at insert in `review_urgency`
(`ham/requests/services_decisions.py`), so `_build_urgency_review_undone_notices` never needs
to re-read the request's current status at all.

This is a test file, not an app-code fix (ham-test-engineer may only add tests). Left as
`xfail(strict=True)` per `tests/web/test_audit_export_stepup_redirect_bug.py`'s established
pattern here -- delete this file's `xfail` marker (or the whole file, if superseded by a real
regression test) once `UrgencyReview` gains its own stored flag.
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


@pytest.mark.xfail(strict=True, reason="PRD-GAP Q-176 false negative, see module docstring")
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
