"""Step 3 rules: approval, rejection, reconsideration, urgency, undo and the date math.

Pure, no DB. Expected values are typed from the PRD (§8, §8.3, §8.4, §10, §46, §52) and the
owner decisions / proposed defaults (Q-153..Q-176), not copied from ``states``. The whole
edge x state x actor matrix is in ``test_request_states.py``; this file covers each guard.
"""

from __future__ import annotations

import dataclasses
import itertools
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

import pytest

from ham.authz import roles as authz_roles
from ham.requests import states
from ham.requests.states import (
    DecisionRoute,
    Refusal,
    RejectionReason,
    RequestAction,
    RequestStatus,
    UrgencyAction,
    UrgencyStatus,
    accepts_media_reopen,
    becomes_urgent_approval,
    check_transition,
    check_undo,
    check_urgency_transition,
    decision_is_undoable,
    is_closed,
    is_urgent_approval,
    may_decide_reconsideration,
    may_request_reconsideration,
    reconsideration_deadline,
    reconsideration_last_day,
    undo_window_ends_at,
)
from ham.rules import RULES

S = RequestStatus
A = RequestAction
U = UrgencyStatus
UA = UrgencyAction
DIR = {"HAM_DIRECTOR"}
AD = {"ASSISTANT_DIRECTOR"}
PAS = {"PASTOR"}
BRD = {"BOARD_REPRESENTATIVE"}
PAS_BRD = PAS | BRD
ADM = {"ADMINISTRATOR"}
REQ = {"REQUESTER"}
SYS = {"SYSTEM"}
VOL = {"VOLUNTEER"}

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 1, 18, 15, tzinfo=UTC)  # 2:15 PM EDT
KIND = "We're so sorry; this is something the owner of the home would need to repair."
US = timedelta(microseconds=1)


def _at(zone: tzinfo, y: int, mo: int, d: int, *hms: int, fold: int = 0) -> datetime:
    h, mi, s, us = (*hms, 0, 0, 0, 0)[:4]
    return datetime(y, mo, d, h, mi, s, us, tzinfo=zone, fold=fold)


def ny(y: int, mo: int, d: int, *hms: int, fold: int = 0) -> datetime:
    return _at(NY, y, mo, d, *hms, fold=fold)


def utc(y: int, mo: int, d: int, *hms: int) -> datetime:
    return _at(UTC, y, mo, d, *hms)


# ---------------------------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------------------------
def test_role_codes_match_authz() -> None:
    assert states.PASTOR == authz_roles.PASTOR
    assert states.BOARD_REPRESENTATIVE == authz_roles.BOARD_REPRESENTATIVE


def test_rejection_reasons_are_exactly_the_q154_list() -> None:
    """Q-154 (decided), grounded in §5. "Outside the area" and "needs a licensed
    professional" were dropped by the owner."""
    assert {r.value for r in RejectionReason} == {
        "family_or_others_can_help",
        "owner_or_landlord_responsible",
        "not_help_ham_offers",
        "couldnt_confirm",
        "another_reason",
    }


def test_model_choices_match_the_rejection_reasons() -> None:
    """S3.0 owns the Django choices; they must carry exactly these codes once they exist."""
    from ham.requests import models

    choices = getattr(models, "RejectionReason", None)
    if choices is None:
        pytest.skip("ham.requests.models.RejectionReason not added yet (S3.0)")
    assert {c.value for c in choices} == {r.value for r in RejectionReason}


def test_routes_and_their_roles() -> None:
    assert {r.value for r in DecisionRoute} == {"pastoral", "board"}
    assert states.ROUTE_ROLE == {
        DecisionRoute.PASTORAL: "PASTOR",
        DecisionRoute.BOARD: "BOARD_REPRESENTATIVE",
    }


def test_new_edges_audit_and_outbox_names() -> None:
    """approvals.md §2.2 / §4 names."""
    by = states.TRANSITIONS_BY_ACTION
    expected = {
        A.APPROVE: ("request.approved", "RequestApproved"),
        A.REJECT: ("request.rejected", "RequestRejected"),
        A.REQUEST_RECONSIDERATION: (
            "request.reconsideration_requested",
            "ReconsiderationRequested",
        ),
        A.RECONSIDER_APPROVE: ("request.reconsideration_decided", "RequestApproved"),
        A.RECONSIDER_REJECT: ("request.reconsideration_decided", "RequestRejected"),
        A.FINALIZE_REJECTION: ("request.rejection_finalized", "RequestRejectionFinalized"),
        A.CANCEL: ("request.cancelled", "RequestCancelled"),
    }
    for action, (audit, event) in expected.items():
        assert (by[action].audit_action, by[action].outbox_event) == (audit, event), action
    ut = states.URGENCY_TRANSITIONS_BY_ACTION
    assert (ut[UA.CERTIFY_URGENCY].audit_action, ut[UA.CERTIFY_URGENCY].outbox_event) == (
        "request.urgency_certified",
        "UrgencyCertified",
    )
    assert (ut[UA.DECLINE_URGENCY].audit_action, ut[UA.DECLINE_URGENCY].outbox_event) == (
        "request.urgency_not_certified",
        "UrgencyNotCertified",
    )


# ---------------------------------------------------------------------------------------------
# APPROVE / REJECT (§8, Q-048, Q-153, Q-154, Q-164)
# ---------------------------------------------------------------------------------------------
def _approve(roles: set[str], **facts: object) -> states.TransitionDecision:
    base: dict[str, object] = {"route": "pastoral", "urgency": "none"}
    base.update(facts)
    return check_transition(A.APPROVE, S.AWAITING_APPROVAL, actor_roles=roles, **base)  # type: ignore[arg-type]


def _reject(roles: set[str], **facts: object) -> states.TransitionDecision:
    base: dict[str, object] = {
        "route": "pastoral",
        "reason_code": "another_reason",
        "message": KIND,
    }
    base.update(facts)
    return check_transition(A.REJECT, S.AWAITING_APPROVAL, actor_roles=roles, **base)  # type: ignore[arg-type]


@pytest.mark.parametrize("decide", [_approve, _reject])
@pytest.mark.parametrize(
    ("roles", "route", "refusal"),
    [
        (PAS, "pastoral", None),
        (BRD, "board", None),
        (PAS, DecisionRoute.PASTORAL, None),
        (PAS, "board", Refusal.ROUTE_NOT_HELD),
        (BRD, "pastoral", Refusal.ROUTE_NOT_HELD),
        # Q-164: someone holding both chooses either route, but must choose.
        (PAS_BRD, "pastoral", None),
        (PAS_BRD, "board", None),
        (PAS_BRD, None, Refusal.ROUTE_REQUIRED),
        (PAS, None, Refusal.ROUTE_REQUIRED),
        (PAS, "", Refusal.ROUTE_REQUIRED),
        (PAS, "PASTORAL", Refusal.ROUTE_NOT_HELD),
        (PAS, "director", Refusal.ROUTE_NOT_HELD),
        # A Director who is also a pastor decides as a pastor (approvals.md §2.3).
        (DIR | PAS, "pastoral", None),
    ],
)
def test_route_must_be_chosen_and_held(
    decide: object, roles: set[str], route: str | None, refusal: Refusal | None
) -> None:
    d = decide(roles, route=route)  # type: ignore[operator]
    assert d.refusal is refusal
    assert d.allowed is (refusal is None)


@pytest.mark.parametrize("roles", [DIR, AD, ADM, REQ, SYS, VOL, DIR | AD])
@pytest.mark.parametrize("decide", [_approve, _reject])
def test_director_ad_and_administrator_never_decide(roles: set[str], decide: object) -> None:
    """§4.4, §5, §12: Director/AD own feasibility, not eligibility; Q-124: Administrator."""
    d = decide(roles, route="pastoral")  # type: ignore[operator]
    assert d.refusal is Refusal.ACTOR_NOT_ALLOWED


@pytest.mark.parametrize(
    ("action", "current", "roles", "facts"),
    [
        (A.APPROVE, S.AWAITING_APPROVAL, PAS, {"route": "pastoral", "urgency": "none"}),
        (
            A.REJECT,
            S.AWAITING_APPROVAL,
            BRD,
            {"route": "board", "reason_code": "couldnt_confirm", "message": KIND},
        ),
        (
            A.REQUEST_RECONSIDERATION,
            S.REJECTED,
            DIR,
            {"now": NOW, "reconsideration_deadline_at": NOW + timedelta(days=3)},
        ),
        (
            A.RECONSIDER_APPROVE,
            S.RECONSIDERATION_PENDING,
            PAS,
            {
                "route": "pastoral",
                "actor_id": "p1",
                "original_decider_id": "p1",
                "message": "ok",
                "urgency": "none",
            },
        ),
        (
            A.RECONSIDER_REJECT,
            S.RECONSIDERATION_PENDING,
            BRD,
            {"route": "board", "reason_code": "another_reason", "message": KIND},
        ),
        (A.CANCEL, S.APPROVED, AD, {"reason": "requester_withdrew"}),
    ],
)
def test_every_step3_staff_action_is_blocked_while_impersonating(
    action: RequestAction, current: RequestStatus, roles: set[str], facts: dict[str, object]
) -> None:
    """Q-048, Q-172."""
    ok = check_transition(action, current, actor_roles=roles, **facts)  # type: ignore[arg-type]
    assert ok.allowed, ok
    d = check_transition(action, current, actor_roles=roles, is_impersonating=True, **facts)  # type: ignore[arg-type]
    assert d.refusal is Refusal.BLOCKED_WHILE_IMPERSONATING


def test_finalize_job_is_not_blocked_by_an_impersonation_flag() -> None:
    d = check_transition(
        A.FINALIZE_REJECTION,
        S.REJECTED,
        actor_roles=SYS,
        is_impersonating=True,
        now=NOW,
        reconsideration_deadline_at=NOW - US,
    )
    assert d.allowed


@pytest.mark.parametrize("decided", [S.APPROVED, S.REJECTED, S.RECONSIDERATION_PENDING])
@pytest.mark.parametrize("decide", [_approve, _reject])
def test_first_recorded_decision_settles_the_request(
    decided: RequestStatus, decide: object
) -> None:
    """Q-153: once decided, the second approver's decision finds the wrong state (the UI
    says "Already decided by ...")."""
    for roles, route in ((PAS, "pastoral"), (BRD, "board")):
        d = check_transition(
            A.APPROVE if decide is _approve else A.REJECT,
            decided,
            actor_roles=roles,
            route=route,
            urgency="none",
            reason_code="another_reason",
            message=KIND,
        )
        assert d.refusal is Refusal.WRONG_STATE


@pytest.mark.parametrize("current", [S.NEEDS_PHONE_CHECK, S.SUBMITTED, S.CANCELLED])
def test_cannot_decide_before_awaiting_approval_or_after_cancel(current: RequestStatus) -> None:
    for action in (A.APPROVE, A.REJECT):
        d = check_transition(
            action,
            current,
            actor_roles=PAS,
            route="pastoral",
            urgency="none",
            reason_code="another_reason",
            message=KIND,
        )
        assert d.refusal is Refusal.WRONG_STATE


@pytest.mark.parametrize(
    ("reason_code", "message", "refusal"),
    [
        *[(r.value, KIND, None) for r in RejectionReason],
        (RejectionReason.COULDNT_CONFIRM, KIND, None),
        (None, KIND, Refusal.REASON_REQUIRED),
        ("", KIND, Refusal.REASON_REQUIRED),
        ("outside_area", KIND, Refusal.REASON_NOT_ALLOWED),  # dropped (Q-154)
        ("needs_licensed_professional", KIND, Refusal.REASON_NOT_ALLOWED),  # dropped
        ("spam", KIND, Refusal.REASON_NOT_ALLOWED),  # a cancel reason, not a decline reason
        ("ANOTHER_REASON", KIND, Refusal.REASON_NOT_ALLOWED),
        ("another_reason", "", Refusal.MESSAGE_REQUIRED),
        ("another_reason", "  \n\t ", Refusal.MESSAGE_REQUIRED),
    ],
)
def test_reject_needs_a_listed_reason_and_a_kind_message(
    reason_code: str | None, message: str, refusal: Refusal | None
) -> None:
    """Q-154: a required reason code from the list and a required, non-blank message."""
    d = _reject(PAS, reason_code=reason_code, message=message)
    assert d.refusal is refusal
    if refusal is None:
        assert d.target is S.REJECTED
        assert not d.closes_request  # it can still be reconsidered (§8.4)
        assert not d.urgent_approval


def test_approve_does_not_close() -> None:
    d = _approve(PAS)
    assert d.target is S.APPROVED
    assert not d.closes_request


@pytest.mark.parametrize(
    ("roles", "route", "urgency", "certify", "refusal", "urgent"),
    [
        # Plain approval: urgent only if a pastor already certified (Q-161).
        (PAS, "pastoral", "none", False, None, False),
        (PAS, "pastoral", "certified", False, None, True),
        (BRD, "board", "certified", False, None, True),
        # Q-160: a Board approval leaves urgency awaiting certification: not urgent (yet).
        (BRD, "board", "awaiting_certification", False, None, False),
        (PAS, "pastoral", "not_certified", False, None, False),
        # "Approve as urgent": pastor only, pastoral route, certifiable urgency.
        (PAS, "pastoral", "awaiting_certification", True, None, True),
        (PAS, "pastoral", "not_certified", True, None, True),  # a declined urgency, later
        (PAS, "pastoral", "none", True, Refusal.URGENCY_NOT_CERTIFIABLE, False),  # not flagged
        (PAS, "pastoral", "certified", True, Refusal.URGENCY_NOT_CERTIFIABLE, False),
        (BRD, "board", "awaiting_certification", True, Refusal.ACTOR_NOT_ALLOWED, False),
        (PAS_BRD, "board", "awaiting_certification", True, Refusal.ACTOR_NOT_ALLOWED, False),
        (PAS_BRD, "pastoral", "awaiting_certification", True, None, True),
        # The urgency fact is required so an urgent approval is never silently missed.
        (PAS, "pastoral", None, False, Refusal.FACTS_MISSING, False),
        (PAS, "pastoral", "urgent", False, Refusal.FACTS_MISSING, False),
    ],
)
def test_approval_and_urgency(
    roles: set[str],
    route: str,
    urgency: str | None,
    certify: bool,
    refusal: Refusal | None,
    urgent: bool,
) -> None:
    d = _approve(roles, route=route, urgency=urgency, certify_urgent=certify)
    assert d.refusal is refusal
    assert d.urgent_approval is urgent


# ---------------------------------------------------------------------------------------------
# REQUEST_RECONSIDERATION and FINALIZE_REJECTION (§8.4; Q-155, Q-159, Q-174, Q-176)
# ---------------------------------------------------------------------------------------------
DEADLINE = utc(2026, 10, 16, 3, 59, 59, 999999)  # end of Thu Oct 15 2026, New York


def _ask(roles: set[str] = REQ, **facts: object) -> states.TransitionDecision:
    base: dict[str, object] = {"now": NOW, "reconsideration_deadline_at": DEADLINE}
    base.update(facts)
    return check_transition(A.REQUEST_RECONSIDERATION, S.REJECTED, actor_roles=roles, **base)  # type: ignore[arg-type]


def _finalize(**facts: object) -> states.TransitionDecision:
    base: dict[str, object] = {"now": DEADLINE + US, "reconsideration_deadline_at": DEADLINE}
    base.update(facts)
    return check_transition(A.FINALIZE_REJECTION, S.REJECTED, actor_roles=SYS, **base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("facts", "refusal"),
    [
        ({}, None),
        ({"now": DEADLINE}, None),  # the very last instant still counts
        ({"now": DEADLINE - timedelta(hours=1)}, None),
        ({"now": DEADLINE + US}, Refusal.DEADLINE_PASSED),
        ({"now": DEADLINE + timedelta(days=30)}, Refusal.DEADLINE_PASSED),
        ({"closed_at": DEADLINE + US}, Refusal.ALREADY_FINAL),
        ({"has_reconsideration": True}, Refusal.RECONSIDERATION_ALREADY_USED),
        ({"decision_undo_open": True}, Refusal.DECISION_UNDO_WINDOW_OPEN),
        ({"now": None}, Refusal.FACTS_MISSING),
        ({"reconsideration_deadline_at": None}, Refusal.FACTS_MISSING),
    ],
)
def test_requesting_reconsideration(facts: dict[str, object], refusal: Refusal | None) -> None:
    d = _ask(REQ, **facts)
    assert d.refusal is refusal
    if refusal is None:
        assert d.target is S.RECONSIDERATION_PENDING
        assert not d.closes_request


@pytest.mark.parametrize("roles", [REQ, DIR, AD])
def test_requester_or_director_ad_by_phone_may_ask(roles: set[str]) -> None:
    """§8.4; Q-159: Director/AD record a reconsideration asked for by phone."""
    assert _ask(roles).allowed


@pytest.mark.parametrize("roles", [PAS, BRD, ADM, VOL, SYS])
def test_nobody_else_asks_for_reconsideration(roles: set[str]) -> None:
    assert _ask(roles).refusal is Refusal.ACTOR_NOT_ALLOWED


@pytest.mark.parametrize(
    "current", [S.AWAITING_APPROVAL, S.APPROVED, S.RECONSIDERATION_PENDING, S.CANCELLED]
)
def test_reconsideration_only_from_a_rejection(current: RequestStatus) -> None:
    d = check_transition(
        A.REQUEST_RECONSIDERATION,
        current,
        actor_roles=REQ,
        now=NOW,
        reconsideration_deadline_at=DEADLINE,
    )
    assert d.refusal is Refusal.WRONG_STATE


@pytest.mark.parametrize(
    ("facts", "refusal"),
    [
        ({}, None),
        ({"now": DEADLINE + timedelta(days=5)}, None),  # a late job run still finalizes
        ({"now": DEADLINE}, Refusal.DEADLINE_NOT_REACHED),
        ({"now": DEADLINE - timedelta(days=1)}, Refusal.DEADLINE_NOT_REACHED),
        # Idempotent re-run: already final -> refused, never a second close.
        ({"closed_at": DEADLINE + US}, Refusal.ALREADY_FINAL),
        ({"has_reconsideration": True}, Refusal.RECONSIDERATION_ALREADY_USED),
        ({"decision_undo_open": True}, Refusal.DECISION_UNDO_WINDOW_OPEN),
        ({"now": None}, Refusal.FACTS_MISSING),
        ({"reconsideration_deadline_at": None}, Refusal.FACTS_MISSING),
    ],
)
def test_finalizing_a_rejection(facts: dict[str, object], refusal: Refusal | None) -> None:
    d = _finalize(**facts)
    assert d.refusal is refusal
    if refusal is None:
        assert d.target is S.REJECTED
        assert d.closes_request


@pytest.mark.parametrize("roles", [DIR, AD, PAS, BRD, REQ, ADM])
def test_only_the_system_finalizes(roles: set[str]) -> None:
    d = check_transition(
        A.FINALIZE_REJECTION,
        S.REJECTED,
        actor_roles=roles,
        now=DEADLINE + US,
        reconsideration_deadline_at=DEADLINE,
    )
    assert d.refusal is Refusal.ACTOR_NOT_ALLOWED


@pytest.mark.parametrize(
    "offset",
    [-timedelta(days=14), -timedelta(seconds=1), -US, timedelta(0), US, timedelta(hours=1)],
)
def test_asking_and_finalizing_never_overlap_and_never_leave_a_gap(offset: timedelta) -> None:
    """At every instant exactly one of "ask" and "finalize" is possible."""
    now = DEADLINE + offset
    asked = _ask(now=now).allowed
    finalized = _finalize(now=now).allowed
    assert asked != finalized


def test_reconsideration_pending_is_never_finalized_by_the_job() -> None:
    d = check_transition(
        A.FINALIZE_REJECTION,
        S.RECONSIDERATION_PENDING,
        actor_roles=SYS,
        now=DEADLINE + timedelta(days=100),
        reconsideration_deadline_at=DEADLINE,
    )
    assert d.refusal is Refusal.WRONG_STATE


def test_naive_datetimes_are_programming_errors() -> None:
    naive = datetime(2026, 10, 1, 12, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        _ask(now=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        _finalize(reconsideration_deadline_at=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        may_request_reconsideration(naive, DEADLINE)
    with pytest.raises(ValueError, match="timezone-aware"):
        reconsideration_deadline(naive, NY)
    with pytest.raises(ValueError, match="timezone-aware"):
        decision_is_undoable(naive, NOW, None)


# ---------------------------------------------------------------------------------------------
# Deciding a reconsideration (Q-157, Q-164)
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("route", "roles", "actor", "facts", "refusal", "took_over_from"),
    [
        # Board route: any Board rep; no take-over concept.
        ("board", BRD, "b2", {}, None, None),
        ("board", BRD, "b1", {}, None, None),
        ("board", PAS_BRD, "x", {}, None, None),
        ("board", PAS, "p1", {}, Refusal.ROUTE_NOT_HELD, None),
        # Pastoral route: the original pastor ...
        ("pastoral", PAS, "p1", {}, None, None),
        ("pastoral", PAS, "p1", {"take_over": True}, None, None),  # nothing to take over
        # ... or another pastor, only by taking over with the tick (Q-157) ...
        ("pastoral", PAS, "p2", {}, Refusal.NOT_YOUR_RECONSIDERATION, None),
        (
            "pastoral",
            PAS,
            "p2",
            {"decider_unavailable_confirmed": True},
            Refusal.NOT_YOUR_RECONSIDERATION,
            None,
        ),
        (
            "pastoral",
            PAS,
            "p2",
            {"take_over": True},
            Refusal.TAKE_OVER_CONFIRMATION_REQUIRED,
            None,
        ),
        (
            "pastoral",
            PAS,
            "p2",
            {"take_over": True, "decider_unavailable_confirmed": True},
            None,
            "p1",
        ),
        # ... or any pastor when the original no longer holds an active Pastor role.
        ("pastoral", PAS, "p2", {"original_decider_is_active_pastor": False}, None, "p1"),
        # The Board rep can't decide a pastoral reconsideration; the route is the recorded one.
        ("pastoral", BRD, "b1", {}, Refusal.ROUTE_NOT_HELD, None),
        ("pastoral", PAS_BRD, "p1", {}, None, None),
        # The original pastor who lost the role can't decide it any more.
        ("pastoral", DIR, "p1", {}, Refusal.ROUTE_NOT_HELD, None),
        (None, PAS, "p1", {}, Refusal.ROUTE_REQUIRED, None),
        ("pastoral", PAS, None, {}, Refusal.FACTS_MISSING, None),
        ("pastoral", PAS, "p1", {"original_decider_id": None}, Refusal.FACTS_MISSING, None),
    ],
)
def test_who_decides_a_reconsideration(
    route: str | None,
    roles: set[str],
    actor: str | None,
    facts: dict[str, object],
    refusal: Refusal | None,
    took_over_from: str | None,
) -> None:
    kwargs: dict[str, object] = {"actor_id": actor, "original_decider_id": "p1"}
    kwargs.update(facts)
    authority = may_decide_reconsideration(route, roles, **kwargs)  # type: ignore[arg-type]
    assert authority.refusal is refusal
    assert authority.allowed is (refusal is None)
    assert authority.took_over_from == took_over_from


def _reconsider(
    action: RequestAction, roles: set[str], **facts: object
) -> states.TransitionDecision:
    base: dict[str, object] = {
        "route": "pastoral",
        "actor_id": "p1",
        "original_decider_id": "p1",
        "message": "We took another look.",
        "reason_code": "another_reason",
        "urgency": "none",
    }
    base.update(facts)
    return check_transition(action, S.RECONSIDERATION_PENDING, actor_roles=roles, **base)  # type: ignore[arg-type]


def test_reconsideration_decisions_carry_the_take_over() -> None:
    d = _reconsider(
        A.RECONSIDER_APPROVE,
        PAS,
        actor_id="p2",
        take_over=True,
        decider_unavailable_confirmed=True,
    )
    assert d.allowed
    assert d.took_over_from == "p1"
    assert d.target is S.APPROVED
    assert not d.closes_request
    d = _reconsider(A.RECONSIDER_REJECT, PAS, actor_id="p2")
    assert d.refusal is Refusal.NOT_YOUR_RECONSIDERATION


@pytest.mark.parametrize(
    ("action", "facts", "refusal"),
    [
        (A.RECONSIDER_APPROVE, {}, None),
        (A.RECONSIDER_APPROVE, {"message": " "}, Refusal.MESSAGE_REQUIRED),  # §8.4 reason
        (A.RECONSIDER_APPROVE, {"reason_code": None}, None),  # no code on an approval
        (A.RECONSIDER_APPROVE, {"urgency": None}, Refusal.FACTS_MISSING),
        (A.RECONSIDER_REJECT, {}, None),
        (A.RECONSIDER_REJECT, {"message": ""}, Refusal.MESSAGE_REQUIRED),
        (A.RECONSIDER_REJECT, {"reason_code": None}, Refusal.REASON_REQUIRED),
        (A.RECONSIDER_REJECT, {"reason_code": "nope"}, Refusal.REASON_NOT_ALLOWED),
        (A.RECONSIDER_REJECT, {"urgency": None}, None),  # urgency only matters on approval
    ],
)
def test_reconsideration_decision_reasons(
    action: RequestAction, facts: dict[str, object], refusal: Refusal | None
) -> None:
    d = _reconsider(action, PAS, **facts)
    assert d.refusal is refusal
    if refusal is None:
        assert d.closes_request is (action is A.RECONSIDER_REJECT)


def test_reconsideration_approval_can_be_an_urgent_approval() -> None:
    assert _reconsider(A.RECONSIDER_APPROVE, PAS, urgency="certified").urgent_approval
    assert not _reconsider(
        A.RECONSIDER_APPROVE, PAS, urgency="awaiting_certification"
    ).urgent_approval


# ---------------------------------------------------------------------------------------------
# CANCEL after a decision (Q-165) and the undo window (Q-176)
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("current", "undo_open", "refusal"),
    [
        (S.APPROVED, False, None),
        (S.APPROVED, True, Refusal.DECISION_UNDO_WINDOW_OPEN),
        (S.RECONSIDERATION_PENDING, False, None),
        # Pre-decision cancels have no decision to wait for.
        (S.AWAITING_APPROVAL, True, None),
    ],
)
def test_cancel_waits_out_an_undo_window(
    current: RequestStatus, undo_open: bool, refusal: Refusal | None
) -> None:
    d = check_transition(
        A.CANCEL,
        current,
        actor_roles=DIR,
        reason="requester_withdrew",
        decision_undo_open=undo_open,
    )
    assert d.refusal is refusal


# ---------------------------------------------------------------------------------------------
# Urgency sub-machine (§10; Q-160, Q-161)
# ---------------------------------------------------------------------------------------------
CERTIFY_FROM = {U.AWAITING_CERTIFICATION, U.NOT_CERTIFIED}
CERTIFY_WHILE = {S.AWAITING_APPROVAL, S.APPROVED}
DECLINE_FROM = {U.AWAITING_CERTIFICATION}
DECLINE_WHILE = {S.AWAITING_APPROVAL}


@pytest.mark.parametrize(
    ("action", "urgency", "status", "roles"),
    list(
        itertools.product(
            UrgencyAction, UrgencyStatus, RequestStatus, [PAS, BRD, DIR, AD, ADM, PAS_BRD]
        )
    ),
)
def test_urgency_matrix(
    action: UrgencyAction, urgency: UrgencyStatus, status: RequestStatus, roles: set[str]
) -> None:
    sources, whiles, target = (
        (CERTIFY_FROM, CERTIFY_WHILE, U.CERTIFIED)
        if action is UA.CERTIFY_URGENCY
        else (DECLINE_FROM, DECLINE_WHILE, U.NOT_CERTIFIED)
    )
    d = check_urgency_transition(action, urgency, status, actor_roles=roles)
    if status not in whiles:
        assert d.refusal is Refusal.WRONG_STATE
    elif urgency not in sources:
        assert d.refusal is Refusal.WRONG_URGENCY_STATE
    elif "PASTOR" not in roles:
        assert d.refusal is Refusal.ACTOR_NOT_ALLOWED  # only a pastor (§10, §67)
    else:
        assert d.allowed
        assert d.target is target
        assert d.becomes_urgent_approval is (target is U.CERTIFIED and status is S.APPROVED)


def test_urgency_guards() -> None:
    args = (UA.CERTIFY_URGENCY, U.AWAITING_CERTIFICATION, S.APPROVED)
    assert check_urgency_transition(*args, actor_roles=PAS).allowed
    assert (
        check_urgency_transition(*args, actor_roles=PAS, is_impersonating=True).refusal
        is Refusal.BLOCKED_WHILE_IMPERSONATING
    )
    assert (
        check_urgency_transition(*args, actor_roles=PAS, closed_at=NOW).refusal
        is Refusal.ALREADY_FINAL
    )
    assert (
        check_urgency_transition(
            "mark_urgent", U.NONE, S.AWAITING_APPROVAL, actor_roles=PAS
        ).refusal
        is Refusal.UNKNOWN_ACTION
    )
    assert (
        check_urgency_transition(UA.CERTIFY_URGENCY, "bogus", S.APPROVED, actor_roles=PAS).refusal
        is Refusal.WRONG_URGENCY_STATE
    )
    assert (
        check_urgency_transition(
            UA.CERTIFY_URGENCY, U.NOT_CERTIFIED, "BOGUS", actor_roles=PAS
        ).refusal
        is Refusal.WRONG_STATE
    )


def test_pastors_cannot_make_an_unflagged_request_urgent() -> None:
    """Q-160: V1 has no "mark urgent" for a request the requester didn't flag."""
    for status in CERTIFY_WHILE:
        d = check_urgency_transition(UA.CERTIFY_URGENCY, U.NONE, status, actor_roles=PAS)
        assert d.refusal is Refusal.WRONG_URGENCY_STATE


@pytest.mark.parametrize(
    ("status", "urgency"), list(itertools.product(RequestStatus, UrgencyStatus))
)
def test_is_urgent_approval(status: RequestStatus, urgency: UrgencyStatus) -> None:
    """Q-161: approved AND certified, nothing else."""
    expected = status is S.APPROVED and urgency is U.CERTIFIED
    assert is_urgent_approval(status, urgency) is expected
    assert is_urgent_approval(status.value, urgency.value) is expected


def test_is_urgent_approval_needs_the_urgency_fact() -> None:
    assert not is_urgent_approval(S.APPROVED, None)


def _run(steps: list[tuple[str, object]]) -> int:
    """Play decisions through the pure rules; count urgent-approval alerts."""
    status, urgency, alerts = S.AWAITING_APPROVAL, U.AWAITING_CERTIFICATION, 0
    for kind, arg in steps:
        if kind == "approve":
            route = str(arg)
            roles = PAS if route == "pastoral" else BRD
            d = check_transition(A.APPROVE, status, actor_roles=roles, route=route, urgency=urgency)
            assert d.allowed, d
            alerts += becomes_urgent_approval(status, urgency, S.APPROVED, urgency)
            assert d.urgent_approval is is_urgent_approval(S.APPROVED, urgency)
            status = S.APPROVED
        elif kind == "approve_as_urgent":
            d = check_transition(
                A.APPROVE,
                status,
                actor_roles=PAS,
                route="pastoral",
                urgency=urgency,
                certify_urgent=True,
            )
            assert d.allowed and d.urgent_approval
            alerts += becomes_urgent_approval(status, urgency, S.APPROVED, U.CERTIFIED)
            status, urgency = S.APPROVED, U.CERTIFIED
        elif kind in ("certify", "decline"):
            action = UA.CERTIFY_URGENCY if kind == "certify" else UA.DECLINE_URGENCY
            u = check_urgency_transition(action, urgency, status, actor_roles=PAS)
            assert u.allowed, u
            assert u.target is not None
            alerts += u.becomes_urgent_approval
            urgency = u.target
    return alerts


@pytest.mark.parametrize(
    ("steps", "alerts"),
    [
        ([("approve_as_urgent", None)], 1),
        ([("certify", None), ("approve", "board")], 1),  # certified first, approved second
        ([("approve", "board"), ("certify", None)], 1),  # Q-160: Board first, pastor later
        ([("approve", "pastoral")], 0),
        ([("decline", None), ("approve", "pastoral")], 0),
        ([("decline", None), ("certify", None), ("approve", "board")], 1),
        ([("decline", None), ("approve", "board"), ("certify", None)], 1),
    ],
)
def test_urgent_alert_fires_exactly_once_whichever_happens_second(
    steps: list[tuple[str, object]], alerts: int
) -> None:
    assert _run(steps) == alerts


# ---------------------------------------------------------------------------------------------
# is_closed and accepts_media_reopen (Q-116, Q-155, Q-173)
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("status", "closed_at", "closed"),
    [
        (S.REJECTED, None, False),  # can still be reconsidered
        (S.REJECTED, NOW, True),  # final
        (S.CANCELLED, NOW, True),
        (S.CANCELLED, None, True),  # always closed, even if the timestamp were missing
        (S.AWAITING_APPROVAL, None, False),
        (S.APPROVED, None, False),
        (S.RECONSIDERATION_PENDING, None, False),
        (S.NEEDS_PHONE_CHECK, None, False),
        (S.SUBMITTED, None, False),
        ("COMPLETED", NOW, True),  # a later project status follows closed_at
        ("COMPLETED", None, False),
    ],
)
def test_is_closed(status: str, closed_at: datetime | None, closed: bool) -> None:
    assert is_closed(status, closed_at) is closed


@pytest.mark.parametrize("status", sorted(states.NEVER_CLOSED_STATUSES))
def test_is_closed_refuses_corrupt_data(status: RequestStatus) -> None:
    with pytest.raises(ValueError):
        is_closed(status, NOW)


@pytest.mark.parametrize(
    ("status", "closed_at", "accepts"),
    [
        (S.AWAITING_APPROVAL, None, True),
        (S.RECONSIDERATION_PENDING, None, True),
        (S.APPROVED, None, True),
        (S.REJECTED, None, False),  # Q-173: not until she asks for reconsideration
        (S.REJECTED, NOW, False),
        (S.CANCELLED, NOW, False),
        (S.NEEDS_PHONE_CHECK, None, False),
        (S.SUBMITTED, None, False),
        ("COMPLETED", NOW, False),
        ("NOT_A_STATUS", None, False),
    ],
)
def test_accepts_media_reopen(status: str, closed_at: datetime | None, accepts: bool) -> None:
    assert accepts_media_reopen(status, closed_at) is accepts


# ---------------------------------------------------------------------------------------------
# Q-174: the reconsideration deadline, in church time
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("decided_at", "last_day", "deadline_utc"),
    [
        # 2:15 PM EDT Thu Oct 1 -> last day Thu Oct 15; 23:59:59.999999 EDT = 03:59:59Z Oct 16.
        (ny(2026, 10, 1, 14, 15), date(2026, 10, 15), utc(2026, 10, 16, 3, 59, 59, 999999)),
        # Late evening: the UTC date is already Oct 2, but the church day is Oct 1.
        (ny(2026, 10, 1, 23, 30), date(2026, 10, 15), utc(2026, 10, 16, 3, 59, 59, 999999)),
        # Just after local midnight: a new church day, a new last day.
        (ny(2026, 10, 2, 0, 5), date(2026, 10, 16), utc(2026, 10, 17, 3, 59, 59, 999999)),
        # Fall back (Nov 1 2026) inside the window: the last day is in EST (UTC-5).
        (ny(2026, 10, 25, 14, 15), date(2026, 11, 8), utc(2026, 11, 9, 4, 59, 59, 999999)),
        # Decided during the repeated 1 AM hour of the fall-back day (second pass, EST).
        (ny(2026, 11, 1, 1, 30, fold=1), date(2026, 11, 15), utc(2026, 11, 16, 4, 59, 59, 999999)),
        # Spring forward (Mar 14 2027) inside the window: the last day is in EDT (UTC-4).
        (ny(2027, 3, 1, 14, 15), date(2027, 3, 15), utc(2027, 3, 16, 3, 59, 59, 999999)),
        # Decided on the spring-forward day itself, just after the jump.
        (ny(2027, 3, 14, 3, 30), date(2027, 3, 28), utc(2027, 3, 29, 3, 59, 59, 999999)),
        # The last day lands on a DST change day (Nov 1 2026): the day ends in EST.
        (ny(2026, 10, 18, 9, 0), date(2026, 11, 1), utc(2026, 11, 2, 4, 59, 59, 999999)),
        # Crossing a year end.
        (ny(2026, 12, 25, 10, 0), date(2027, 1, 8), utc(2027, 1, 9, 4, 59, 59, 999999)),
    ],
)
def test_reconsideration_deadline_is_the_end_of_the_church_day(
    decided_at: datetime, last_day: date, deadline_utc: datetime
) -> None:
    assert reconsideration_last_day(decided_at, NY) == last_day
    deadline = reconsideration_deadline(decided_at, NY)
    assert deadline == deadline_utc
    assert deadline.tzinfo is UTC
    local = deadline.astimezone(NY)
    assert (local.date(), local.hour, local.minute, local.second, local.microsecond) == (
        last_day,
        23,
        59,
        59,
        999999,
    )
    # The same instant expressed in UTC, a string zone name, or a fixed offset agrees.
    assert reconsideration_deadline(decided_at.astimezone(UTC), "America/New_York") == deadline
    assert (
        reconsideration_deadline(decided_at.astimezone(timezone(timedelta(hours=9))), NY)
        == deadline
    )


@pytest.mark.parametrize(
    ("now_local", "may_ask"),
    [
        (ny(2026, 10, 1, 14, 15), True),  # the moment of the decision (day 0, 2:15 PM)
        (ny(2026, 10, 15, 14, 15), True),  # exactly 14 x 24 h later: still day 14
        (ny(2026, 10, 15, 14, 16), True),  # past 14 elapsed days, still the printed day
        (ny(2026, 10, 15, 23, 59), True),  # 11:59 PM on day 14
        (ny(2026, 10, 15, 23, 59, 59, 999999), True),  # the last instant
        (ny(2026, 10, 16, 0, 0), False),  # midnight starting day 15: too late
        (ny(2026, 10, 16, 14, 15), False),
    ],
)
def test_q174_cutoff_in_church_time(now_local: datetime, may_ask: bool) -> None:
    """Decided 2:15 PM on day 0 (Oct 1 2026, New York): "You can ask until October 15"."""
    deadline = reconsideration_deadline(ny(2026, 10, 1, 14, 15), NY)
    assert may_request_reconsideration(now_local, deadline) is may_ask
    assert may_request_reconsideration(now_local.astimezone(UTC), deadline) is may_ask


def test_deadline_follows_the_church_zone_not_utc() -> None:
    decided = utc(2026, 10, 2, 3, 30)  # Oct 1, 11:30 PM in New York; Oct 2 in UTC
    assert reconsideration_last_day(decided, NY) == date(2026, 10, 15)
    assert reconsideration_last_day(decided, UTC) == date(2026, 10, 16)
    assert reconsideration_last_day(decided, "America/Los_Angeles") == date(2026, 10, 15)


def test_deadline_uses_the_rule_value() -> None:
    """Q-155: 14 days; a different rule set (e.g. a future version) changes the answer."""
    assert RULES.approvals.RECONSIDERATION_REQUEST_WINDOW == 14
    one_day = dataclasses.replace(
        RULES, approvals=dataclasses.replace(RULES.approvals, RECONSIDERATION_REQUEST_WINDOW=1)
    )
    decided = ny(2026, 10, 1, 14, 15)
    assert reconsideration_deadline(decided, NY, rules=one_day) == utc(
        2026, 10, 3, 3, 59, 59, 999999
    )


def test_redecided_decline_gets_a_new_window() -> None:
    """Q-174: an undone and re-made decision starts a new window from the new decision."""
    first = reconsideration_deadline(ny(2026, 10, 1, 23, 50), NY)
    again = reconsideration_deadline(ny(2026, 10, 2, 0, 10), NY)
    assert again - first == timedelta(days=1)


def test_deadline_needs_a_decision_time() -> None:
    with pytest.raises(ValueError, match="required"):
        reconsideration_deadline(None, NY)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------
# Undo (Q-156 decided, Q-176)
# ---------------------------------------------------------------------------------------------
DECIDED = utc(2026, 10, 1, 18, 15)
WINDOW = timedelta(minutes=30)


@pytest.mark.parametrize(
    ("now", "undone_at", "undoable"),
    [
        (DECIDED, None, True),
        (DECIDED + timedelta(minutes=29, seconds=59), None, True),
        (DECIDED + WINDOW - US, None, True),
        (DECIDED + WINDOW, None, False),  # at exactly 30:00 the held effects go
        (DECIDED + timedelta(days=1), None, False),
        (DECIDED + timedelta(minutes=5), DECIDED + timedelta(minutes=1), False),
    ],
)
def test_decision_is_undoable(now: datetime, undone_at: datetime | None, undoable: bool) -> None:
    assert decision_is_undoable(DECIDED, now, undone_at) is undoable


def test_undo_window_ends_30_minutes_after_the_decision() -> None:
    assert RULES.approvals.DECISION_UNDO_WINDOW == WINDOW
    assert undo_window_ends_at(DECIDED) == DECIDED + WINDOW


def test_undoable_decisions_are_exactly_these() -> None:
    """Q-176: approvals, rejections, urgency reviews and reconsideration decisions."""
    assert states.UNDOABLE_ACTIONS == {
        A.APPROVE,
        A.REJECT,
        A.RECONSIDER_APPROVE,
        A.RECONSIDER_REJECT,
        UA.CERTIFY_URGENCY,
        UA.DECLINE_URGENCY,
    }


def _undo(decision: str, **facts: object) -> states.UndoDecision:
    base: dict[str, object] = {
        "actor_id": "p1",
        "decided_by_id": "p1",
        "decided_at": DECIDED,
        "now": DECIDED + timedelta(minutes=10),
        "undone_at": None,
        "current_status": S.APPROVED,
        "current_urgency": U.NONE,
    }
    base.update(facts)
    return check_undo(decision, **base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("decision", "facts", "refusal"),
    [
        (A.APPROVE, {}, None),
        (A.APPROVE, {"actor_id": "p2"}, Refusal.NOT_THE_DECIDER),  # only the decider
        (A.APPROVE, {"actor_id": None}, Refusal.FACTS_MISSING),
        (A.APPROVE, {"is_impersonating": True}, Refusal.BLOCKED_WHILE_IMPERSONATING),
        (A.APPROVE, {"undone_at": DECIDED + timedelta(minutes=2)}, Refusal.ALREADY_UNDONE),
        (A.APPROVE, {"now": DECIDED + WINDOW}, Refusal.UNDO_WINDOW_PASSED),
        (A.APPROVE, {"now": DECIDED + WINDOW - US}, None),
        (A.APPROVE, {"current_status": S.CANCELLED}, Refusal.STATE_CHANGED_SINCE_DECISION),
        (A.APPROVE, {"current_status": "BOGUS"}, Refusal.STATE_CHANGED_SINCE_DECISION),
        (A.APPROVE, {"current_urgency": None}, Refusal.FACTS_MISSING),
        (A.REJECT, {"current_status": S.REJECTED}, None),
        (A.REJECT, {"current_status": S.APPROVED}, Refusal.STATE_CHANGED_SINCE_DECISION),
        (
            A.REJECT,
            {"current_status": S.REJECTED, "prior_urgency": "awaiting_certification"},
            Refusal.FACTS_MISSING,
        ),
        (A.RECONSIDER_APPROVE, {}, None),
        (A.RECONSIDER_REJECT, {"current_status": S.REJECTED}, None),
        (A.CANCEL, {"current_status": S.CANCELLED}, Refusal.NOT_UNDOABLE),
        (A.FINALIZE_REJECTION, {"current_status": S.REJECTED}, Refusal.NOT_UNDOABLE),
        (
            A.REQUEST_RECONSIDERATION,
            {"current_status": S.RECONSIDERATION_PENDING},
            Refusal.NOT_UNDOABLE,
        ),
        (A.SUBMIT_VERIFIED, {"current_status": S.SUBMITTED}, Refusal.NOT_UNDOABLE),
        ("bogus", {}, Refusal.NOT_UNDOABLE),
    ],
)
def test_undo_guards(decision: str, facts: dict[str, object], refusal: Refusal | None) -> None:
    d = _undo(decision, **facts)
    assert d.refusal is refusal
    assert d.allowed is (refusal is None)


@pytest.mark.parametrize(
    ("decision", "current", "restore", "reopens", "clears_deadline"),
    [
        (A.APPROVE, S.APPROVED, S.AWAITING_APPROVAL, False, False),
        (A.REJECT, S.REJECTED, S.AWAITING_APPROVAL, False, True),
        (A.RECONSIDER_APPROVE, S.APPROVED, S.RECONSIDERATION_PENDING, False, False),
        (A.RECONSIDER_REJECT, S.REJECTED, S.RECONSIDERATION_PENDING, True, False),
    ],
)
def test_undo_restores_the_prior_state(
    decision: RequestAction,
    current: RequestStatus,
    restore: RequestStatus,
    reopens: bool,
    clears_deadline: bool,
) -> None:
    d = _undo(decision, current_status=current)
    assert d.allowed
    assert d.restore_status is restore
    assert d.restore_urgency is None
    assert d.reopens_request is reopens
    assert d.clears_reconsideration_deadline is clears_deadline
    assert not d.urgent_approval_undone


def test_undo_is_the_inverse_of_each_decision_edge() -> None:
    """Round trip: the state a decision produces, undone, is the state it came from."""
    for action in (A.APPROVE, A.REJECT, A.RECONSIDER_APPROVE, A.RECONSIDER_REJECT):
        t = states.TRANSITIONS_BY_ACTION[action]
        (source,) = t.sources
        d = _undo(action, current_status=t.target)
        assert d.restore_status is source
        assert d.reopens_request is t.closes_request


@pytest.mark.parametrize(
    ("decision", "facts", "restore_status", "restore_urgency", "urgent_undone"),
    [
        # "Approve as urgent": both the approval and the certification are undone.
        (
            A.APPROVE,
            {"current_urgency": U.CERTIFIED, "prior_urgency": U.AWAITING_CERTIFICATION},
            S.AWAITING_APPROVAL,
            U.AWAITING_CERTIFICATION,
            True,
        ),
        # A plain approval of an already-certified request: urgency stays certified.
        (A.APPROVE, {"current_urgency": U.CERTIFIED}, S.AWAITING_APPROVAL, None, True),
        (
            A.APPROVE,
            {"current_urgency": U.AWAITING_CERTIFICATION},
            S.AWAITING_APPROVAL,
            None,
            False,
        ),
        (
            A.RECONSIDER_APPROVE,
            {"current_urgency": U.CERTIFIED},
            S.RECONSIDERATION_PENDING,
            None,
            True,
        ),
        # Certification after a (Board) approval made it urgent; undoing it un-makes it.
        (
            UA.CERTIFY_URGENCY,
            {"current_urgency": U.CERTIFIED, "prior_urgency": U.AWAITING_CERTIFICATION},
            S.APPROVED,
            U.AWAITING_CERTIFICATION,
            True,
        ),
        (
            UA.CERTIFY_URGENCY,
            {
                "current_status": S.AWAITING_APPROVAL,
                "current_urgency": U.CERTIFIED,
                "prior_urgency": U.NOT_CERTIFIED,
            },
            S.AWAITING_APPROVAL,
            U.NOT_CERTIFIED,
            False,
        ),
        (
            UA.DECLINE_URGENCY,
            {
                "current_status": S.AWAITING_APPROVAL,
                "current_urgency": U.NOT_CERTIFIED,
                "prior_urgency": U.AWAITING_CERTIFICATION,
            },
            S.AWAITING_APPROVAL,
            U.AWAITING_CERTIFICATION,
            False,
        ),
    ],
)
def test_undo_and_urgency(
    decision: str,
    facts: dict[str, object],
    restore_status: RequestStatus,
    restore_urgency: UrgencyStatus | None,
    urgent_undone: bool,
) -> None:
    """Q-176: the urgent-approval alert is never held, so undoing the decision that caused
    it triggers the Director/AD in-app follow-up."""
    d = _undo(decision, **facts)
    assert d.allowed, d
    assert d.restore_status is restore_status
    assert d.restore_urgency is restore_urgency
    assert d.urgent_approval_undone is urgent_undone


@pytest.mark.parametrize(
    ("decision", "facts", "refusal"),
    [
        (UA.CERTIFY_URGENCY, {"current_urgency": U.CERTIFIED}, Refusal.FACTS_MISSING),
        (
            UA.CERTIFY_URGENCY,
            {"current_urgency": U.CERTIFIED, "prior_urgency": U.CERTIFIED},
            Refusal.FACTS_MISSING,
        ),
        (
            UA.CERTIFY_URGENCY,
            {"current_urgency": U.CERTIFIED, "prior_urgency": U.NONE},
            Refusal.FACTS_MISSING,
        ),
        (
            UA.CERTIFY_URGENCY,
            {"current_urgency": U.CERTIFIED, "prior_urgency": "bogus"},
            Refusal.FACTS_MISSING,
        ),
        # Declined, then certified by someone since: the decline can't be undone.
        (
            UA.DECLINE_URGENCY,
            {"current_urgency": U.CERTIFIED, "prior_urgency": U.AWAITING_CERTIFICATION},
            Refusal.STATE_CHANGED_SINCE_DECISION,
        ),
        (
            UA.DECLINE_URGENCY,
            {"current_urgency": U.NOT_CERTIFIED, "prior_urgency": U.NOT_CERTIFIED},
            Refusal.FACTS_MISSING,
        ),
        # "Approve as urgent" undo needs the request to still be certified.
        (
            A.APPROVE,
            {"current_urgency": U.NOT_CERTIFIED, "prior_urgency": U.AWAITING_CERTIFICATION},
            Refusal.STATE_CHANGED_SINCE_DECISION,
        ),
        (
            A.RECONSIDER_APPROVE,
            {"current_urgency": U.CERTIFIED, "prior_urgency": U.AWAITING_CERTIFICATION},
            Refusal.FACTS_MISSING,
        ),
        (
            UA.CERTIFY_URGENCY,
            {"actor_id": "p2", "current_urgency": U.CERTIFIED, "prior_urgency": U.NOT_CERTIFIED},
            Refusal.NOT_THE_DECIDER,
        ),
    ],
)
def test_undo_urgency_refusals(decision: str, facts: dict[str, object], refusal: Refusal) -> None:
    assert _undo(decision, **facts).refusal is refusal


def test_undo_and_request_decision_share_the_window_rule() -> None:
    """While undoable, nothing may build on the decision; once over, the undo is gone."""
    inside, edge = DECIDED + WINDOW - US, DECIDED + WINDOW
    assert decision_is_undoable(DECIDED, inside, None)
    assert _undo(A.APPROVE, now=inside).allowed
    assert not decision_is_undoable(DECIDED, edge, None)
    assert _undo(A.APPROVE, now=edge).refusal is Refusal.UNDO_WINDOW_PASSED
