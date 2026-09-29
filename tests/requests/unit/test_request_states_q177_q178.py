"""Q-177 and Q-178 (proposed defaults in use, step 3). Pure, no DB.

- Q-177: a pastor may decline urgency ("Not urgent") while Awaiting Approval OR Approved, so
  a Board-approved urgent request never waits for certification forever.
- Q-178: a pastor's "Approve, but not as urgent" records urgency not_certified in the same
  transaction as the approval; undoing the approval restores both.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ham.requests.states import (
    Refusal,
    RequestAction,
    RequestStatus,
    UrgencyAction,
    UrgencyStatus,
    becomes_urgent_approval,
    check_transition,
    check_undo,
    check_urgency_transition,
)

S = RequestStatus
A = RequestAction
U = UrgencyStatus
UA = UrgencyAction
PAS = {"PASTOR"}
BRD = {"BOARD_REPRESENTATIVE"}
PAS_BRD = PAS | BRD
DECIDED = datetime(2026, 10, 1, 18, 15, tzinfo=UTC)


# --- Q-177 ------------------------------------------------------------------------------------
def test_pastor_may_decline_urgency_after_a_board_approval() -> None:
    """Failed before Q-177: DECLINE was refused (WRONG_STATE) once the request was APPROVED."""
    d = check_urgency_transition(
        UA.DECLINE_URGENCY, U.AWAITING_CERTIFICATION, S.APPROVED, actor_roles=PAS
    )
    assert d.allowed, d
    assert d.target is U.NOT_CERTIFIED
    assert not d.becomes_urgent_approval


@pytest.mark.parametrize(
    ("urgency", "status", "roles", "refusal"),
    [
        (U.AWAITING_CERTIFICATION, S.AWAITING_APPROVAL, PAS, None),
        (U.AWAITING_CERTIFICATION, S.APPROVED, PAS, None),
        (U.AWAITING_CERTIFICATION, S.APPROVED, PAS_BRD, None),
        (U.AWAITING_CERTIFICATION, S.APPROVED, BRD, Refusal.ACTOR_NOT_ALLOWED),  # pastor only
        (U.CERTIFIED, S.APPROVED, PAS, Refusal.WRONG_URGENCY_STATE),  # never un-certify
        (U.NOT_CERTIFIED, S.APPROVED, PAS, Refusal.WRONG_URGENCY_STATE),
        (U.NONE, S.APPROVED, PAS, Refusal.WRONG_URGENCY_STATE),
        (U.AWAITING_CERTIFICATION, S.REJECTED, PAS, Refusal.WRONG_STATE),
        (U.AWAITING_CERTIFICATION, S.RECONSIDERATION_PENDING, PAS, Refusal.WRONG_STATE),
        (U.AWAITING_CERTIFICATION, S.CANCELLED, PAS, Refusal.WRONG_STATE),
        (U.AWAITING_CERTIFICATION, S.SUBMITTED, PAS, Refusal.WRONG_STATE),
    ],
)
def test_decline_urgency_guards(
    urgency: UrgencyStatus, status: RequestStatus, roles: set[str], refusal: Refusal | None
) -> None:
    d = check_urgency_transition(UA.DECLINE_URGENCY, urgency, status, actor_roles=roles)
    assert d.refusal is refusal


def test_decline_and_certify_now_share_the_request_statuses() -> None:
    from ham.requests.states import URGENCY_TRANSITIONS_BY_ACTION as by

    assert by[UA.DECLINE_URGENCY].request_statuses == by[UA.CERTIFY_URGENCY].request_statuses
    assert by[UA.DECLINE_URGENCY].request_statuses == {S.AWAITING_APPROVAL, S.APPROVED}


def test_declined_after_approval_can_still_be_certified_and_alerts_once() -> None:
    """Board approves, a pastor says "Not urgent", then another pastor certifies: one alert."""
    status, urgency, alerts = S.APPROVED, U.AWAITING_CERTIFICATION, 0
    for action in (UA.DECLINE_URGENCY, UA.CERTIFY_URGENCY):
        d = check_urgency_transition(action, urgency, status, actor_roles=PAS)
        assert d.allowed and d.target is not None
        alerts += d.becomes_urgent_approval
        urgency = d.target
    assert urgency is U.CERTIFIED
    assert alerts == 1


def test_undo_a_decline_made_after_approval() -> None:
    d = check_undo(
        UA.DECLINE_URGENCY,
        actor_id="p1",
        decided_by_id="p1",
        decided_at=DECIDED,
        now=DECIDED + timedelta(minutes=5),
        undone_at=None,
        current_status=S.APPROVED,
        current_urgency=U.NOT_CERTIFIED,
        prior_urgency=U.AWAITING_CERTIFICATION,
    )
    assert d.allowed, d
    assert (d.restore_status, d.restore_urgency) == (S.APPROVED, U.AWAITING_CERTIFICATION)
    assert not d.urgent_approval_undone


# --- Q-178 ------------------------------------------------------------------------------------
def _approve(roles: set[str], **facts: object):  # type: ignore[no-untyped-def]
    base: dict[str, object] = {"route": "pastoral", "urgency": U.AWAITING_CERTIFICATION}
    base.update(facts)
    return check_transition(A.APPROVE, S.AWAITING_APPROVAL, actor_roles=roles, **base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("roles", "facts", "refusal", "urgency_after", "urgent"),
    [
        # "Approve, but not as urgent" (pastor): urgency recorded not_certified.
        (PAS, {"decline_urgency": True}, None, U.NOT_CERTIFIED, False),
        (PAS_BRD, {"decline_urgency": True}, None, U.NOT_CERTIFIED, False),
        # "Approve as urgent": certified.
        (PAS, {"certify_urgent": True}, None, U.CERTIFIED, True),
        # A plain approval leaves urgency as it is (a Board approval stays awaiting, Q-160).
        (PAS, {}, None, U.AWAITING_CERTIFICATION, False),
        (BRD, {"route": "board"}, None, U.AWAITING_CERTIFICATION, False),
        (PAS, {"urgency": U.NONE}, None, U.NONE, False),
        # Only a pastor reviews urgency; the Board route can't decline it either.
        (BRD, {"route": "board", "decline_urgency": True}, Refusal.ACTOR_NOT_ALLOWED, None, False),
        (
            PAS_BRD,
            {"route": "board", "decline_urgency": True},
            Refusal.ACTOR_NOT_ALLOWED,
            None,
            False,
        ),
        # Only an urgency still awaiting review can be declined.
        (
            PAS,
            {"decline_urgency": True, "urgency": U.NONE},
            Refusal.WRONG_URGENCY_STATE,
            None,
            False,
        ),
        (
            PAS,
            {"decline_urgency": True, "urgency": U.NOT_CERTIFIED},
            Refusal.WRONG_URGENCY_STATE,
            None,
            False,
        ),
        (
            PAS,
            {"decline_urgency": True, "urgency": U.CERTIFIED},
            Refusal.WRONG_URGENCY_STATE,
            None,
            False,
        ),
        # Both at once is a contradiction.
        (
            PAS,
            {"decline_urgency": True, "certify_urgent": True},
            Refusal.URGENCY_CHOICE_CONFLICT,
            None,
            False,
        ),
    ],
)
def test_approve_with_an_urgency_outcome(
    roles: set[str],
    facts: dict[str, object],
    refusal: Refusal | None,
    urgency_after: UrgencyStatus | None,
    urgent: bool,
) -> None:
    d = _approve(roles, **facts)
    assert d.refusal is refusal
    assert d.urgency_after is urgency_after
    assert d.urgent_approval is urgent


def test_approve_not_as_urgent_then_certify_later_alerts_once() -> None:
    d = _approve(PAS, decline_urgency=True)
    assert d.urgency_after is U.NOT_CERTIFIED
    u = check_urgency_transition(UA.CERTIFY_URGENCY, U.NOT_CERTIFIED, S.APPROVED, actor_roles=PAS)
    assert u.becomes_urgent_approval
    assert (
        becomes_urgent_approval(
            S.AWAITING_APPROVAL, U.AWAITING_CERTIFICATION, S.APPROVED, U.NOT_CERTIFIED
        )
        is False
    )


def _undo(**facts: object):  # type: ignore[no-untyped-def]
    base: dict[str, object] = {
        "actor_id": "p1",
        "decided_by_id": "p1",
        "decided_at": DECIDED,
        "now": DECIDED + timedelta(minutes=10),
        "undone_at": None,
        "current_status": S.APPROVED,
        "current_urgency": U.NOT_CERTIFIED,
        "prior_urgency": U.AWAITING_CERTIFICATION,
        "accompanying_urgency": UA.DECLINE_URGENCY,
    }
    base.update(facts)
    return check_undo(A.APPROVE, **base)  # type: ignore[arg-type]


def test_undo_approve_not_as_urgent_restores_both() -> None:
    d = _undo()
    assert d.allowed, d
    assert d.restore_status is S.AWAITING_APPROVAL
    assert d.restore_urgency is U.AWAITING_CERTIFICATION
    assert not d.urgent_approval_undone


@pytest.mark.parametrize(
    ("facts", "refusal"),
    [
        # Someone certified it since: the combined decision can't be undone as recorded.
        ({"current_urgency": U.CERTIFIED}, Refusal.STATE_CHANGED_SINCE_DECISION),
        ({"prior_urgency": U.NOT_CERTIFIED}, Refusal.FACTS_MISSING),
        ({"prior_urgency": None}, Refusal.FACTS_MISSING),
        ({"accompanying_urgency": "bogus"}, Refusal.FACTS_MISSING),
    ],
)
def test_undo_approve_not_as_urgent_refusals(facts: dict[str, object], refusal: Refusal) -> None:
    assert _undo(**facts).refusal is refusal


def test_accompanying_urgency_only_on_an_approval() -> None:
    d = check_undo(
        A.REJECT,
        actor_id="p1",
        decided_by_id="p1",
        decided_at=DECIDED,
        now=DECIDED + timedelta(minutes=10),
        undone_at=None,
        current_status=S.REJECTED,
        current_urgency=U.NOT_CERTIFIED,
        prior_urgency=U.AWAITING_CERTIFICATION,
        accompanying_urgency=UA.DECLINE_URGENCY,
    )
    assert d.refusal is Refusal.FACTS_MISSING


def test_explicit_certify_combo_matches_the_default() -> None:
    """``accompanying_urgency`` defaults to "Approve as urgent" when only prior_urgency is
    passed (the S3.1 contract), and naming it explicitly gives the same answer."""
    implicit = _undo(current_urgency=U.CERTIFIED, accompanying_urgency=None)
    explicit = _undo(current_urgency=U.CERTIFIED, accompanying_urgency=UA.CERTIFY_URGENCY)
    assert implicit == explicit
    assert implicit.allowed
    assert implicit.restore_urgency is U.AWAITING_CERTIFICATION
    assert implicit.urgent_approval_undone
