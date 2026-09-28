"""AssistanceRequest state machine for intake (PRD §52; intake.md §4). Rules-owned, pure.

No Django, no I/O, no clock. Services pass in the facts; this module says whether a move is
allowed, where it goes and what it must emit. Services still authorize the real principal
through ``ham.authz`` first; the actor check here is defence in depth and documents who may
move a request.

Step 2 edges (step 3 adds approval, rejection and reconsideration):

==========================  =====================  ==================  ====================
Action                      From                   To                  Actor
==========================  =====================  ==================  ====================
SUBMIT_VERIFIED             (new)                  SUBMITTED           REQUESTER, email
                                                                       code or link used
SUBMIT_WITHOUT_EMAIL        (new)                  NEEDS_PHONE_CHECK   REQUESTER who chose
                                                                       "I don't use email"
VERIFY_BY_PHONE             NEEDS_PHONE_CHECK      SUBMITTED           DIR, AD; not while
                                                                       impersonating
COMPLETE_INTAKE_CHECKS      SUBMITTED              AWAITING_APPROVAL   SYSTEM, after the
                                                                       duplicate check
CANCEL                      NEEDS_PHONE_CHECK,     CANCELLED           DIR, AD; not while
                            SUBMITTED,                                 impersonating; Q-107
                            AWAITING_APPROVAL                          reason required
==========================  =====================  ==================  ====================

- Q-025 (decided): a request sent with "I don't use email" is held in NEEDS_PHONE_CHECK
  (seen by the Director and Assistant Director only). The ONLY way out towards approvers is
  VERIFY_BY_PHONE ("verified by phone call"), which goes to SUBMITTED so the normal
  duplicate check runs next.
- Q-107 (proposed default in use): before any approval decision, a request may be closed
  only as spam/test, requester withdrew, or duplicate submission. Need/eligibility goes to
  approvers (§5, §8.3); there is no "other".
- Urgent is an attribute, not a state (§52).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Role codes, spelled out (``ham.authz.roles`` values; a unit test pins them in sync). Kept
# local so this module stays importable from anywhere, including pure tests.
HAM_DIRECTOR = "HAM_DIRECTOR"
ASSISTANT_DIRECTOR = "ASSISTANT_DIRECTOR"
REQUESTER = "REQUESTER"
SYSTEM = "SYSTEM"


# PRD-GAP Q-106: Submitted -> Awaiting Approval is automatic after the duplicate check.
class RequestStatus(StrEnum):
    """Full request status set from day 1; step 2 uses the first four."""

    NEEDS_PHONE_CHECK = "NEEDS_PHONE_CHECK"
    SUBMITTED = "SUBMITTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    CANCELLED = "CANCELLED"
    # Step 3 adds the edges into these.
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RECONSIDERATION_PENDING = "RECONSIDERATION_PENDING"


class RequestAction(StrEnum):
    SUBMIT_VERIFIED = "submit_verified"
    SUBMIT_WITHOUT_EMAIL = "submit_without_email"
    VERIFY_BY_PHONE = "verify_by_phone"
    COMPLETE_INTAKE_CHECKS = "complete_intake_checks"
    CANCEL = "cancel"


class VerificationMethod(StrEnum):
    """How the requester's contact was verified (``RequestContactVerification.method``)."""

    EMAIL_CODE = "email_code"
    EMAIL_LINK = "email_link"
    STAFF_PHONE_CALL = "staff_phone_call"


EMAIL_VERIFICATION_METHODS: frozenset[VerificationMethod] = frozenset(
    {VerificationMethod.EMAIL_CODE, VerificationMethod.EMAIL_LINK}
)


# PRD-GAP Q-107: proposed default in use; owner may change.
class CancelReason(StrEnum):
    """Pre-decision close reasons (Q-107). Never need or eligibility.

    PRD-GAP Q-140: proposed default in use. ``COULDNT_REACH_THEM`` is a 4th reason, only
    for a "Needs a phone check" request no one could get hold of (not an eligibility
    judgement -- the person may ask again). ``check_transition`` below refuses it from any
    other source status.
    """

    SPAM = "spam"  # spam or a test
    REQUESTER_WITHDREW = "requester_withdrew"
    DUPLICATE_SUBMISSION = "duplicate_submission"
    COULDNT_REACH_THEM = "couldnt_reach_them"  # Q-140: NEEDS_PHONE_CHECK only


class UrgencyStatus(StrEnum):
    NONE = "none"
    AWAITING_CERTIFICATION = "awaiting_certification"
    CERTIFIED = "certified"  # step 3
    NOT_CERTIFIED = "not_certified"  # step 3


class Refusal(StrEnum):
    """Why a transition was refused. Stable codes for services, tests and audit ``after``."""

    UNKNOWN_ACTION = "unknown_action"
    WRONG_STATE = "wrong_state"
    ACTOR_NOT_ALLOWED = "actor_not_allowed"
    BLOCKED_WHILE_IMPERSONATING = "blocked_while_impersonating"
    EMAIL_VERIFICATION_REQUIRED = "email_verification_required"
    EMAIL_OPT_OUT_REQUIRED = "email_opt_out_required"
    EMAIL_GIVEN_WITH_OPT_OUT = "email_given_with_opt_out"
    INTAKE_CHECKS_INCOMPLETE = "intake_checks_incomplete"
    REASON_REQUIRED = "reason_required"
    REASON_NOT_ALLOWED = "reason_not_allowed"


@dataclass(frozen=True, slots=True)
class Transition:
    """One edge of the table: who may do ``action`` from ``sources`` and what it emits."""

    action: RequestAction
    sources: frozenset[RequestStatus | None]  # None = the request does not exist yet
    target: RequestStatus
    actors: frozenset[str]
    blocked_while_impersonating: bool
    audit_action: str
    # None = no domain event of its own (intake.md §6 defines none for this edge).
    outbox_event: str | None


_DIR_AD = frozenset({HAM_DIRECTOR, ASSISTANT_DIRECTOR})

TRANSITIONS: tuple[Transition, ...] = (
    Transition(
        action=RequestAction.SUBMIT_VERIFIED,
        sources=frozenset({None}),
        target=RequestStatus.SUBMITTED,
        actors=frozenset({REQUESTER}),
        blocked_while_impersonating=False,
        audit_action="request.submitted",
        outbox_event="RequestSubmitted",
    ),
    Transition(
        action=RequestAction.SUBMIT_WITHOUT_EMAIL,
        sources=frozenset({None}),
        target=RequestStatus.NEEDS_PHONE_CHECK,
        actors=frozenset({REQUESTER}),
        blocked_while_impersonating=False,
        audit_action="request.submitted",
        outbox_event="RequestSubmitted",
    ),
    Transition(
        action=RequestAction.VERIFY_BY_PHONE,
        sources=frozenset({RequestStatus.NEEDS_PHONE_CHECK}),
        target=RequestStatus.SUBMITTED,
        actors=_DIR_AD,
        blocked_while_impersonating=True,
        audit_action="request.contact_verified",
        # The service enqueues the intake checks exactly as for any SUBMITTED request.
        outbox_event=None,
    ),
    Transition(
        action=RequestAction.COMPLETE_INTAKE_CHECKS,
        sources=frozenset({RequestStatus.SUBMITTED}),
        target=RequestStatus.AWAITING_APPROVAL,
        actors=frozenset({SYSTEM}),
        blocked_while_impersonating=False,
        audit_action="request.status_changed",
        outbox_event="RequestAwaitingApproval",
    ),
    Transition(
        action=RequestAction.CANCEL,
        sources=frozenset(
            {
                RequestStatus.NEEDS_PHONE_CHECK,
                RequestStatus.SUBMITTED,
                RequestStatus.AWAITING_APPROVAL,
            }
        ),
        target=RequestStatus.CANCELLED,
        actors=_DIR_AD,
        blocked_while_impersonating=True,
        audit_action="request.cancelled",
        outbox_event="RequestCancelled",
    ),
)

TRANSITIONS_BY_ACTION: dict[RequestAction, Transition] = {t.action: t for t in TRANSITIONS}

# Terminal in step 2. Step 3 adds final REJECTED (after the one reconsideration, §8.4) --
# which is why "closed" is recorded as ``closed_at`` on the request, not derived from
# status alone (a reconsiderable REJECTED is not closed, Q-116).
TERMINAL_STATUSES: frozenset[RequestStatus] = frozenset({RequestStatus.CANCELLED})

# Before any approval decision (Q-107 close reasons apply only here).
PRE_DECISION_STATUSES: frozenset[RequestStatus] = frozenset(
    {RequestStatus.NEEDS_PHONE_CHECK, RequestStatus.SUBMITTED, RequestStatus.AWAITING_APPROVAL}
)

# Q-025: held for a phone check -- Director/AD only, never shown to approvers.
PHONE_CHECK_STATUSES: frozenset[RequestStatus] = frozenset({RequestStatus.NEEDS_PHONE_CHECK})

# What pastors and the Board representative act on in step 2 (§8, Q-106).
AWAITING_DECISION_STATUSES: frozenset[RequestStatus] = frozenset({RequestStatus.AWAITING_APPROVAL})


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    allowed: bool
    target: RequestStatus | None
    refusal: Refusal | None
    transition: Transition | None
    # True when entering the target closes the request: the service sets ``closed_at`` and
    # the requester access end (``ham.requester_portal.validity.normal_access_ends_at``).
    closes_request: bool = False


def _refuse(refusal: Refusal, transition: Transition | None = None) -> TransitionDecision:
    return TransitionDecision(False, None, refusal, transition)


def check_transition(
    action: RequestAction | str,
    current: RequestStatus | str | None,
    *,
    actor_roles: frozenset[str] | set[str],
    is_impersonating: bool = False,
    verification_method: VerificationMethod | str | None = None,
    email_opt_out: bool = False,
    has_email: bool = False,
    intake_checks_complete: bool = False,
    reason: CancelReason | str | None = None,
) -> TransitionDecision:
    """Decide one transition. Pure: same inputs, same answer, every time.

    ``current`` is None for a request that does not exist yet (submission).
    Guards, by action:
    - SUBMIT_VERIFIED: the contact was verified by an emailed code or link (Q-100).
    - SUBMIT_WITHOUT_EMAIL: the requester ticked "I don't use email" and gave no email (Q-025).
    - VERIFY_BY_PHONE: only from NEEDS_PHONE_CHECK; blocked while impersonating (Q-025).
    - COMPLETE_INTAKE_CHECKS: the duplicate check has finished (Q-106).
    - CANCEL: reason is one of the Q-107 codes; blocked while impersonating.
    """
    try:
        act = RequestAction(action)
    except ValueError:
        return _refuse(Refusal.UNKNOWN_ACTION)
    t = TRANSITIONS_BY_ACTION[act]

    try:
        state = None if current is None else RequestStatus(current)
    except ValueError:
        return _refuse(Refusal.WRONG_STATE, t)
    if state not in t.sources:
        return _refuse(Refusal.WRONG_STATE, t)
    if not (t.actors & frozenset(actor_roles)):
        return _refuse(Refusal.ACTOR_NOT_ALLOWED, t)
    if t.blocked_while_impersonating and is_impersonating:
        return _refuse(Refusal.BLOCKED_WHILE_IMPERSONATING, t)

    if act is RequestAction.SUBMIT_VERIFIED:
        if email_opt_out:
            return _refuse(Refusal.EMAIL_GIVEN_WITH_OPT_OUT, t)
        if not has_email or _method(verification_method) not in EMAIL_VERIFICATION_METHODS:
            return _refuse(Refusal.EMAIL_VERIFICATION_REQUIRED, t)
    elif act is RequestAction.SUBMIT_WITHOUT_EMAIL:
        if not email_opt_out:
            return _refuse(Refusal.EMAIL_OPT_OUT_REQUIRED, t)
        if has_email:
            return _refuse(Refusal.EMAIL_GIVEN_WITH_OPT_OUT, t)
    elif act is RequestAction.COMPLETE_INTAKE_CHECKS:
        if not intake_checks_complete:
            return _refuse(Refusal.INTAKE_CHECKS_INCOMPLETE, t)
    elif act is RequestAction.CANCEL:
        if reason is None or reason == "":
            return _refuse(Refusal.REASON_REQUIRED, t)
        try:
            cancel_reason = CancelReason(reason)
        except ValueError:
            return _refuse(Refusal.REASON_NOT_ALLOWED, t)
        # Q-140: "couldn't reach them" only makes sense -- and is only allowed -- while the
        # request is still waiting for a phone check; any other source status refuses it.
        phone_check_only = cancel_reason is CancelReason.COULDNT_REACH_THEM
        if phone_check_only and state is not RequestStatus.NEEDS_PHONE_CHECK:
            return _refuse(Refusal.REASON_NOT_ALLOWED, t)

    return TransitionDecision(
        allowed=True,
        target=t.target,
        refusal=None,
        transition=t,
        closes_request=t.target in TERMINAL_STATUSES,
    )


def _method(value: VerificationMethod | str | None) -> VerificationMethod | None:
    if value is None:
        return None
    try:
        return VerificationMethod(value)
    except ValueError:
        return None


def allowed_actions(
    current: RequestStatus | str | None, actor_roles: frozenset[str] | set[str]
) -> tuple[RequestAction, ...]:
    """Actions whose state and actor guards pass (for showing buttons; still call
    ``check_transition`` with the full facts before acting)."""
    state = None if current is None else RequestStatus(current)
    roles = frozenset(actor_roles)
    return tuple(t.action for t in TRANSITIONS if state in t.sources and t.actors & roles)


def is_terminal(status: RequestStatus | str) -> bool:
    return RequestStatus(status) in TERMINAL_STATUSES


def is_pre_decision(status: RequestStatus | str) -> bool:
    return RequestStatus(status) in PRE_DECISION_STATUSES


def visible_to_approvers(status: RequestStatus | str) -> bool:
    """Pastors and the Board rep never see a request still waiting for a phone check
    (Q-025). A SUBMITTED request (duplicate check running) is visible, so a stalled job
    never hides a request; it only becomes "waiting for a decision" once AWAITING_APPROVAL."""
    return RequestStatus(status) not in PHONE_CHECK_STATUSES


def initial_urgency_status(urgent_requested: bool) -> UrgencyStatus:
    """On submission a ticked urgent flag waits for a pastor's certification (§10)."""
    return UrgencyStatus.AWAITING_CERTIFICATION if urgent_requested else UrgencyStatus.NONE


def requester_notified_of_cancellation(reason: CancelReason | str) -> bool:
    """Q-107: a kind closure note for every reason except spam/test."""
    return CancelReason(reason) is not CancelReason.SPAM
