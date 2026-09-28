"""Request state machine (PRD §52; intake.md §4; Q-025, Q-106, Q-107). Pure, no DB.

The expected table below is typed from the architecture plan and the owner decisions, not
copied from ``TRANSITIONS``.
"""

from __future__ import annotations

import itertools

import pytest

from ham.authz import roles as authz_roles
from ham.requests import states
from ham.requests.states import (
    CancelReason,
    Refusal,
    RequestAction,
    RequestStatus,
    UrgencyStatus,
    VerificationMethod,
    allowed_actions,
    check_transition,
)

S = RequestStatus
A = RequestAction
DIR = {"HAM_DIRECTOR"}
AD = {"ASSISTANT_DIRECTOR"}
PAS = {"PASTOR"}
BRD = {"BOARD_REPRESENTATIVE"}
ADM = {"ADMINISTRATOR"}
REQ = {"REQUESTER"}
SYS = {"SYSTEM"}
VOL = {"VOLUNTEER"}

# Facts that satisfy each action's domain guard, so the tests below isolate state/actor.
GOOD_FACTS: dict[RequestAction, dict[str, object]] = {
    A.SUBMIT_VERIFIED: {"verification_method": "email_code", "has_email": True},
    A.SUBMIT_WITHOUT_EMAIL: {"email_opt_out": True, "has_email": False},
    A.VERIFY_BY_PHONE: {},
    A.COMPLETE_INTAKE_CHECKS: {"intake_checks_complete": True},
    A.CANCEL: {"reason": "spam"},
}

# (action, from) -> (to, allowed actor role sets)
EXPECTED_EDGES: dict[tuple[RequestAction, RequestStatus | None], RequestStatus] = {
    (A.SUBMIT_VERIFIED, None): S.SUBMITTED,
    (A.SUBMIT_WITHOUT_EMAIL, None): S.NEEDS_PHONE_CHECK,
    (A.VERIFY_BY_PHONE, S.NEEDS_PHONE_CHECK): S.SUBMITTED,
    (A.COMPLETE_INTAKE_CHECKS, S.SUBMITTED): S.AWAITING_APPROVAL,
    (A.CANCEL, S.NEEDS_PHONE_CHECK): S.CANCELLED,
    (A.CANCEL, S.SUBMITTED): S.CANCELLED,
    (A.CANCEL, S.AWAITING_APPROVAL): S.CANCELLED,
}
EXPECTED_ACTORS: dict[RequestAction, list[set[str]]] = {
    A.SUBMIT_VERIFIED: [REQ],
    A.SUBMIT_WITHOUT_EMAIL: [REQ],
    A.VERIFY_BY_PHONE: [DIR, AD],
    A.COMPLETE_INTAKE_CHECKS: [SYS],
    A.CANCEL: [DIR, AD],
}
ALL_ACTORS = [DIR, AD, PAS, BRD, ADM, REQ, SYS, VOL]
ALL_FROM: list[RequestStatus | None] = [None, *RequestStatus]


def test_role_codes_match_authz() -> None:
    assert states.HAM_DIRECTOR == authz_roles.HAM_DIRECTOR
    assert states.ASSISTANT_DIRECTOR == authz_roles.ASSISTANT_DIRECTOR


def test_table_has_exactly_the_expected_edges() -> None:
    actual = {(t.action, src): t.target for t in states.TRANSITIONS for src in t.sources}
    assert actual == EXPECTED_EDGES


@pytest.mark.parametrize(
    ("action", "current", "roles"),
    [
        (action, current, roles)
        for action, current in itertools.product(RequestAction, ALL_FROM)
        for roles in ALL_ACTORS
    ],
)
def test_every_action_state_actor_combination(
    action: RequestAction, current: RequestStatus | None, roles: set[str]
) -> None:
    d = check_transition(action, current, actor_roles=roles, **GOOD_FACTS[action])  # type: ignore[arg-type]
    edge = (action, current)
    if edge not in EXPECTED_EDGES:
        assert not d.allowed
        assert d.refusal is Refusal.WRONG_STATE
    elif roles not in EXPECTED_ACTORS[action]:
        assert not d.allowed
        assert d.refusal is Refusal.ACTOR_NOT_ALLOWED
    else:
        assert d.allowed, d
        assert d.target is EXPECTED_EDGES[edge]
        assert d.refusal is None


def test_role_union_counts() -> None:
    d = check_transition(A.CANCEL, S.AWAITING_APPROVAL, actor_roles=DIR | VOL, reason="spam")
    assert d.allowed


@pytest.mark.parametrize("action", [A.VERIFY_BY_PHONE, A.CANCEL])
def test_blocked_while_impersonating(action: RequestAction) -> None:
    current = S.NEEDS_PHONE_CHECK
    ok = check_transition(action, current, actor_roles=DIR, **GOOD_FACTS[action])  # type: ignore[arg-type]
    assert ok.allowed
    d = check_transition(
        action,
        current,
        actor_roles=DIR,
        is_impersonating=True,
        **GOOD_FACTS[action],  # type: ignore[arg-type]
    )
    assert not d.allowed
    assert d.refusal is Refusal.BLOCKED_WHILE_IMPERSONATING


def test_system_move_is_not_blocked_by_an_impersonation_flag() -> None:
    d = check_transition(
        A.COMPLETE_INTAKE_CHECKS,
        S.SUBMITTED,
        actor_roles=SYS,
        is_impersonating=True,
        intake_checks_complete=True,
    )
    assert d.allowed


# --- Q-100 / Q-025: how a request enters ---------------------------------------------------
@pytest.mark.parametrize(
    ("facts", "refusal"),
    [
        ({"verification_method": "email_code", "has_email": True}, None),
        ({"verification_method": "email_link", "has_email": True}, None),
        ({"verification_method": VerificationMethod.EMAIL_CODE, "has_email": True}, None),
        ({"verification_method": None, "has_email": True}, Refusal.EMAIL_VERIFICATION_REQUIRED),
        (
            {"verification_method": "staff_phone_call", "has_email": True},
            Refusal.EMAIL_VERIFICATION_REQUIRED,
        ),
        ({"verification_method": "sms", "has_email": True}, Refusal.EMAIL_VERIFICATION_REQUIRED),
        (
            {"verification_method": "email_code", "has_email": False},
            Refusal.EMAIL_VERIFICATION_REQUIRED,
        ),
        (
            {"verification_method": "email_code", "has_email": True, "email_opt_out": True},
            Refusal.EMAIL_GIVEN_WITH_OPT_OUT,
        ),
    ],
)
def test_submit_verified_needs_an_email_code_or_link(
    facts: dict[str, object], refusal: Refusal | None
) -> None:
    d = check_transition(A.SUBMIT_VERIFIED, None, actor_roles=REQ, **facts)  # type: ignore[arg-type]
    assert d.allowed is (refusal is None)
    assert d.refusal is refusal
    if refusal is None:
        assert d.target is S.SUBMITTED


@pytest.mark.parametrize(
    ("facts", "refusal"),
    [
        ({"email_opt_out": True, "has_email": False}, None),
        ({"email_opt_out": False, "has_email": False}, Refusal.EMAIL_OPT_OUT_REQUIRED),
        ({"email_opt_out": True, "has_email": True}, Refusal.EMAIL_GIVEN_WITH_OPT_OUT),
    ],
)
def test_submit_without_email_goes_to_phone_check(
    facts: dict[str, object], refusal: Refusal | None
) -> None:
    d = check_transition(A.SUBMIT_WITHOUT_EMAIL, None, actor_roles=REQ, **facts)  # type: ignore[arg-type]
    assert d.refusal is refusal
    if refusal is None:
        assert d.target is S.NEEDS_PHONE_CHECK


def test_phone_check_leaves_only_by_phone_verification_or_cancel() -> None:
    """Q-025: nothing moves a phone-check request towards approvers except 'verified by
    phone call' -- not the system job, not a requester, not an approver."""
    ways_out = {t.action for t in states.TRANSITIONS if S.NEEDS_PHONE_CHECK in t.sources}
    assert ways_out == {A.VERIFY_BY_PHONE, A.CANCEL}
    d = check_transition(
        A.COMPLETE_INTAKE_CHECKS, S.NEEDS_PHONE_CHECK, actor_roles=SYS, intake_checks_complete=True
    )
    assert d.refusal is Refusal.WRONG_STATE
    for roles in (PAS, BRD, ADM, REQ, SYS):
        assert not check_transition(
            A.VERIFY_BY_PHONE, S.NEEDS_PHONE_CHECK, actor_roles=roles
        ).allowed
    verified = check_transition(A.VERIFY_BY_PHONE, S.NEEDS_PHONE_CHECK, actor_roles=AD)
    assert verified.target is S.SUBMITTED  # then the normal duplicate check runs
    assert verified.transition is not None
    assert verified.transition.audit_action == "request.contact_verified"


def test_phone_check_is_hidden_from_approvers() -> None:
    assert not states.visible_to_approvers(S.NEEDS_PHONE_CHECK)
    for s in (S.SUBMITTED, S.AWAITING_APPROVAL, S.CANCELLED):
        assert states.visible_to_approvers(s)
    assert states.AWAITING_DECISION_STATUSES == {S.AWAITING_APPROVAL}


def test_intake_checks_must_have_finished() -> None:
    d = check_transition(A.COMPLETE_INTAKE_CHECKS, S.SUBMITTED, actor_roles=SYS)
    assert d.refusal is Refusal.INTAKE_CHECKS_INCOMPLETE


# --- Q-107: pre-decision close reasons -----------------------------------------------------
def test_cancel_reasons_are_exactly_the_three() -> None:
    assert {r.value for r in CancelReason} == {
        "spam",
        "requester_withdrew",
        "duplicate_submission",
    }


@pytest.mark.parametrize(
    ("reason", "refusal"),
    [
        ("spam", None),
        ("requester_withdrew", None),
        ("duplicate_submission", None),
        (CancelReason.SPAM, None),
        (None, Refusal.REASON_REQUIRED),
        ("", Refusal.REASON_REQUIRED),
        ("other", Refusal.REASON_NOT_ALLOWED),  # dropped by the reconciliation
        ("not_eligible", Refusal.REASON_NOT_ALLOWED),  # need/eligibility goes to approvers
        ("SPAM", Refusal.REASON_NOT_ALLOWED),
    ],
)
def test_cancel_reason_guard(reason: str | None, refusal: Refusal | None) -> None:
    d = check_transition(A.CANCEL, S.AWAITING_APPROVAL, actor_roles=AD, reason=reason)
    assert d.refusal is refusal
    if refusal is None:
        assert d.target is S.CANCELLED
        assert d.closes_request


@pytest.mark.parametrize(
    ("reason", "notified"),
    [("spam", False), ("requester_withdrew", True), ("duplicate_submission", True)],
)
def test_requester_notification_on_cancel(reason: str, notified: bool) -> None:
    assert states.requester_notified_of_cancellation(reason) is notified


def test_cannot_cancel_twice_or_after_a_decision() -> None:
    for current in (S.CANCELLED, S.APPROVED, S.REJECTED, S.RECONSIDERATION_PENDING):
        d = check_transition(A.CANCEL, current, actor_roles=DIR, reason="spam")
        assert d.refusal is Refusal.WRONG_STATE


# --- misc -----------------------------------------------------------------------------------
def test_only_cancel_closes_in_step_2() -> None:
    for t in states.TRANSITIONS:
        d = check_transition(
            t.action,
            next(iter(t.sources)),
            actor_roles=t.actors,
            **GOOD_FACTS[t.action],  # type: ignore[arg-type]
        )
        assert d.allowed
        assert d.closes_request is (t.action is A.CANCEL)
    assert states.is_terminal(S.CANCELLED)
    assert not states.is_terminal("AWAITING_APPROVAL")


def test_audit_and_outbox_names() -> None:
    by = states.TRANSITIONS_BY_ACTION
    assert by[A.SUBMIT_VERIFIED].audit_action == "request.submitted"
    assert by[A.SUBMIT_VERIFIED].outbox_event == "RequestSubmitted"
    assert by[A.SUBMIT_WITHOUT_EMAIL].outbox_event == "RequestSubmitted"
    assert by[A.COMPLETE_INTAKE_CHECKS].audit_action == "request.status_changed"
    assert by[A.COMPLETE_INTAKE_CHECKS].outbox_event == "RequestAwaitingApproval"
    assert by[A.CANCEL].audit_action == "request.cancelled"
    assert by[A.CANCEL].outbox_event == "RequestCancelled"
    assert by[A.VERIFY_BY_PHONE].outbox_event is None


def test_unknown_inputs_are_refused_not_raised() -> None:
    assert check_transition("approve", S.AWAITING_APPROVAL, actor_roles=PAS).refusal is (
        Refusal.UNKNOWN_ACTION
    )
    assert check_transition(A.CANCEL, "BOGUS", actor_roles=DIR, reason="spam").refusal is (
        Refusal.WRONG_STATE
    )


def test_allowed_actions_for_buttons() -> None:
    assert allowed_actions(S.NEEDS_PHONE_CHECK, DIR) == (A.VERIFY_BY_PHONE, A.CANCEL)
    assert allowed_actions(S.AWAITING_APPROVAL, AD) == (A.CANCEL,)
    assert allowed_actions(S.AWAITING_APPROVAL, PAS) == ()  # step 3 adds decisions
    assert allowed_actions(None, REQ) == (A.SUBMIT_VERIFIED, A.SUBMIT_WITHOUT_EMAIL)
    assert allowed_actions(S.CANCELLED, DIR) == ()


def test_pre_decision_and_urgency() -> None:
    assert {s for s in S if states.is_pre_decision(s)} == {
        S.NEEDS_PHONE_CHECK,
        S.SUBMITTED,
        S.AWAITING_APPROVAL,
    }
    assert states.initial_urgency_status(True) is UrgencyStatus.AWAITING_CERTIFICATION
    assert states.initial_urgency_status(False) is UrgencyStatus.NONE


def test_decisions_are_deterministic() -> None:
    args = (A.CANCEL, S.SUBMITTED)
    first = check_transition(*args, actor_roles=DIR, reason="duplicate_submission")
    for _ in range(3):
        assert check_transition(*args, actor_roles=DIR, reason="duplicate_submission") == first
