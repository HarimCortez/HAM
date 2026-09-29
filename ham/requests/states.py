"""AssistanceRequest state machine (PRD §52; intake.md §4; approvals.md §2.2). Rules-owned, pure.

No Django, no I/O, no clock. Services pass in the facts (including ``now``); this module says
whether a move is allowed, where it goes and what it must emit. Services still authorize the
real principal through ``ham.authz`` first; the actor check here is defence in depth and
documents who may move a request.

Step 2 edges (intake):

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

Step 3 edges (approvals.md §2.2 as overridden by its owner box; PRD §8, §8.3, §8.4, §10):

=========================  =======================  ======================  ===================
Action                     From                     To                      Actor
=========================  =======================  ======================  ===================
APPROVE                    AWAITING_APPROVAL        APPROVED                PASTOR (pastoral
                                                                            route), BOARD_REP
                                                                            (board route)
REJECT                     AWAITING_APPROVAL        REJECTED (open)         same; reason code
                                                                            + kind message
REQUEST_RECONSIDERATION    REJECTED, open, by the   RECONSIDERATION_        REQUESTER (secure
                           deadline, none yet       PENDING                 page); DIR, AD (by
                                                                            phone, Q-159)
RECONSIDER_APPROVE         RECONSIDERATION_PENDING  APPROVED                the route's role:
                                                                            original pastor or
                                                                            take-over (Q-157)
RECONSIDER_REJECT          RECONSIDERATION_PENDING  REJECTED (closes)       same
FINALIZE_REJECTION         REJECTED, open, past     REJECTED (closes)       SYSTEM
                           the deadline
CANCEL (extended)          + APPROVED,              CANCELLED               DIR, AD; only
                           RECONSIDERATION_PENDING                          "requester withdrew"
                                                                            (Q-165)
=========================  =======================  ======================  ===================

- Q-153 (decided): the first recorded decision settles the request. A second approver acting
  at the same moment finds the request no longer AWAITING_APPROVAL (``WRONG_STATE``).
- Q-155/Q-174: "closed" is ``closed_at``, not status. REJECTED with ``closed_at`` unset can
  still be reconsidered; RECONSIDER_REJECT and FINALIZE_REJECTION close it (final).
- Q-156/Q-176 (undo) is NOT an edge. ``check_undo`` is a pure function of the decision that
  was made and the state it produced; it says whether the decider may undo it and which
  prior state to restore. While a decision can still be undone nothing may build on it
  (``decision_undo_open`` refuses REQUEST_RECONSIDERATION, FINALIZE_REJECTION and CANCEL).
- Urgency (§10, Q-160, Q-161) is a sub-machine on the attribute:
  ``check_urgency_transition`` and ``is_urgent_approval``.

Datetimes must be timezone-aware; a naive one is a programming error and raises
``ValueError``. Everything else is answered with a ``Refusal`` code, never an exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from enum import StrEnum
from zoneinfo import ZoneInfo

from ham.rules import RULES, Rules

# Role codes, spelled out (``ham.authz.roles`` values; a unit test pins them in sync). Kept
# local so this module stays importable from anywhere, including pure tests.
HAM_DIRECTOR = "HAM_DIRECTOR"
ASSISTANT_DIRECTOR = "ASSISTANT_DIRECTOR"
PASTOR = "PASTOR"
BOARD_REPRESENTATIVE = "BOARD_REPRESENTATIVE"
REQUESTER = "REQUESTER"
SYSTEM = "SYSTEM"


# PRD-GAP Q-106: Submitted -> Awaiting Approval is automatic after the duplicate check.
class RequestStatus(StrEnum):
    """Full request status set from day 1."""

    NEEDS_PHONE_CHECK = "NEEDS_PHONE_CHECK"
    SUBMITTED = "SUBMITTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    CANCELLED = "CANCELLED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RECONSIDERATION_PENDING = "RECONSIDERATION_PENDING"


class RequestAction(StrEnum):
    SUBMIT_VERIFIED = "submit_verified"
    SUBMIT_WITHOUT_EMAIL = "submit_without_email"
    VERIFY_BY_PHONE = "verify_by_phone"
    COMPLETE_INTAKE_CHECKS = "complete_intake_checks"
    CANCEL = "cancel"
    # Step 3 (approvals)
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_RECONSIDERATION = "request_reconsideration"
    RECONSIDER_APPROVE = "reconsider_approve"
    RECONSIDER_REJECT = "reconsider_reject"
    FINALIZE_REJECTION = "finalize_rejection"


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
    """Close reasons (Q-107). Never need or eligibility.

    PRD-GAP Q-140: proposed default in use. ``COULDNT_REACH_THEM`` is a 4th reason, only
    for a "Needs a phone check" request no one could get hold of (not an eligibility
    judgement -- the person may ask again). ``check_transition`` below refuses it from any
    other source status. After a decision only ``REQUESTER_WITHDREW`` is allowed (Q-165).
    """

    SPAM = "spam"  # spam or a test
    REQUESTER_WITHDREW = "requester_withdrew"
    DUPLICATE_SUBMISSION = "duplicate_submission"
    COULDNT_REACH_THEM = "couldnt_reach_them"  # Q-140: NEEDS_PHONE_CHECK only


class DecisionRoute(StrEnum):
    """Who decided (§8.1 Board route, §8.2 pastoral route).

    PRD-GAP Q-164: someone holding both roles chooses the route every time (nothing is
    preselected); a reconsideration follows the route of the decision it reconsiders.
    """

    PASTORAL = "pastoral"
    BOARD = "board"


# The role a route needs.
ROUTE_ROLE: dict[DecisionRoute, str] = {
    DecisionRoute.PASTORAL: PASTOR,
    DecisionRoute.BOARD: BOARD_REPRESENTATIVE,
}


class RejectionReason(StrEnum):
    """Q-154 (decided): why a request was declined, grounded in PRD §5.

    The Django choices in ``ham.requests.models`` must carry exactly these values (a unit
    test checks once they exist). The kind message the requester reads is separate text.
    """

    FAMILY_OR_OTHERS_CAN_HELP = "family_or_others_can_help"
    OWNER_OR_LANDLORD_RESPONSIBLE = "owner_or_landlord_responsible"
    NOT_HELP_HAM_OFFERS = "not_help_ham_offers"
    COULDNT_CONFIRM = "couldnt_confirm"
    ANOTHER_REASON = "another_reason"


class UrgencyStatus(StrEnum):
    NONE = "none"
    AWAITING_CERTIFICATION = "awaiting_certification"
    CERTIFIED = "certified"
    NOT_CERTIFIED = "not_certified"


class UrgencyAction(StrEnum):
    CERTIFY_URGENCY = "certify_urgency"
    DECLINE_URGENCY = "decline_urgency"


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
    # Step 3
    FACTS_MISSING = "facts_missing"  # a fact the rule needs was not passed (caller bug)
    ROUTE_REQUIRED = "route_required"  # Q-164: nothing preselected
    ROUTE_NOT_HELD = "route_not_held"  # the actor doesn't hold the route's role
    MESSAGE_REQUIRED = "message_required"  # Q-154 kind message / §8.4 simple reason
    URGENCY_NOT_CERTIFIABLE = "urgency_not_certifiable"
    WRONG_URGENCY_STATE = "wrong_urgency_state"
    ALREADY_FINAL = "already_final"  # the request is closed (e.g. a final rejection)
    RECONSIDERATION_ALREADY_USED = "reconsideration_already_used"  # §8.4: only one
    DEADLINE_PASSED = "deadline_passed"
    DEADLINE_NOT_REACHED = "deadline_not_reached"
    NOT_YOUR_RECONSIDERATION = "not_your_reconsideration"  # Q-157: take it over first
    TAKE_OVER_CONFIRMATION_REQUIRED = "take_over_confirmation_required"  # Q-157 tick
    DECISION_UNDO_WINDOW_OPEN = "decision_undo_window_open"  # Q-176
    # Undo (Q-156, Q-176)
    NOT_UNDOABLE = "not_undoable"
    NOT_THE_DECIDER = "not_the_decider"
    ALREADY_UNDONE = "already_undone"
    UNDO_WINDOW_PASSED = "undo_window_passed"
    STATE_CHANGED_SINCE_DECISION = "state_changed_since_decision"


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
    # Entering the target closes the request: the service sets ``closed_at`` and the
    # requester access end (``ham.requester_portal.validity.normal_access_ends_at``).
    closes_request: bool = False


_DIR_AD = frozenset({HAM_DIRECTOR, ASSISTANT_DIRECTOR})
_APPROVERS = frozenset({PASTOR, BOARD_REPRESENTATIVE})

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
                # PRD-GAP Q-165: after a decision, only "requester withdrew" (guard below).
                RequestStatus.APPROVED,
                RequestStatus.RECONSIDERATION_PENDING,
            }
        ),
        target=RequestStatus.CANCELLED,
        actors=_DIR_AD,
        blocked_while_impersonating=True,
        audit_action="request.cancelled",
        outbox_event="RequestCancelled",
        closes_request=True,
    ),
    Transition(
        action=RequestAction.APPROVE,
        sources=frozenset({RequestStatus.AWAITING_APPROVAL}),
        target=RequestStatus.APPROVED,
        actors=_APPROVERS,
        blocked_while_impersonating=True,  # Q-048
        audit_action="request.approved",
        outbox_event="RequestApproved",  # stage=initial
    ),
    Transition(
        action=RequestAction.REJECT,
        sources=frozenset({RequestStatus.AWAITING_APPROVAL}),
        target=RequestStatus.REJECTED,  # open: may still be reconsidered (§8.4)
        actors=_APPROVERS,
        blocked_while_impersonating=True,  # Q-048
        audit_action="request.rejected",
        outbox_event="RequestRejected",  # final=false
    ),
    Transition(
        action=RequestAction.REQUEST_RECONSIDERATION,
        sources=frozenset({RequestStatus.REJECTED}),
        target=RequestStatus.RECONSIDERATION_PENDING,
        # The requester on the secure page; PRD-GAP Q-159: Director/AD record a phone request.
        actors=frozenset({REQUESTER}) | _DIR_AD,
        blocked_while_impersonating=True,  # Q-172 (staff; a requester never impersonates)
        audit_action="request.reconsideration_requested",
        outbox_event="ReconsiderationRequested",
    ),
    Transition(
        action=RequestAction.RECONSIDER_APPROVE,
        sources=frozenset({RequestStatus.RECONSIDERATION_PENDING}),
        target=RequestStatus.APPROVED,
        actors=_APPROVERS,
        blocked_while_impersonating=True,
        audit_action="request.reconsideration_decided",
        outbox_event="RequestApproved",  # stage=reconsideration
    ),
    Transition(
        action=RequestAction.RECONSIDER_REJECT,
        sources=frozenset({RequestStatus.RECONSIDERATION_PENDING}),
        target=RequestStatus.REJECTED,
        actors=_APPROVERS,
        blocked_while_impersonating=True,
        audit_action="request.reconsideration_decided",
        outbox_event="RequestRejected",  # final=true
        closes_request=True,
    ),
    Transition(
        action=RequestAction.FINALIZE_REJECTION,
        sources=frozenset({RequestStatus.REJECTED}),
        target=RequestStatus.REJECTED,
        actors=frozenset({SYSTEM}),
        blocked_while_impersonating=False,
        audit_action="request.rejection_finalized",
        outbox_event="RequestRejectionFinalized",
        closes_request=True,
    ),
)

TRANSITIONS_BY_ACTION: dict[RequestAction, Transition] = {t.action: t for t in TRANSITIONS}

# Statuses that are ALWAYS closed. A final REJECTED is closed too, but REJECTED alone is not
# (a reconsiderable REJECTED is open, Q-116/Q-155): "closed" is ``closed_at`` on the request.
# For access, media and retention use ``is_closed(status, closed_at)``, never this set.
TERMINAL_STATUSES: frozenset[RequestStatus] = frozenset({RequestStatus.CANCELLED})

# Statuses that never carry ``closed_at`` in step 3 (approvals.md §2.1 CHECK constraint).
NEVER_CLOSED_STATUSES: frozenset[RequestStatus] = frozenset(
    {
        RequestStatus.NEEDS_PHONE_CHECK,
        RequestStatus.SUBMITTED,
        RequestStatus.AWAITING_APPROVAL,
        RequestStatus.RECONSIDERATION_PENDING,
        RequestStatus.APPROVED,
    }
)

# Before any approval decision (Q-107 close reasons apply only here).
PRE_DECISION_STATUSES: frozenset[RequestStatus] = frozenset(
    {RequestStatus.NEEDS_PHONE_CHECK, RequestStatus.SUBMITTED, RequestStatus.AWAITING_APPROVAL}
)

# PRD-GAP Q-165: after a decision a request may be closed only because the requester
# withdrew, and only from APPROVED or RECONSIDERATION_PENDING (an open rejection finalizes
# on its own).
POST_DECISION_CANCEL_REASONS: frozenset[CancelReason] = frozenset({CancelReason.REQUESTER_WITHDREW})

# Q-025: held for a phone check -- Director/AD only, never shown to approvers.
PHONE_CHECK_STATUSES: frozenset[RequestStatus] = frozenset({RequestStatus.NEEDS_PHONE_CHECK})

# What pastors and the Board representative act on (§8, Q-106).
AWAITING_DECISION_STATUSES: frozenset[RequestStatus] = frozenset({RequestStatus.AWAITING_APPROVAL})

# PRD-GAP Q-173: leaders may reopen requester uploads only in these statuses and only while
# the request is not closed -- not on a rejection that can still be reconsidered (only once
# the requester asks, which moves it to RECONSIDERATION_PENDING).
MEDIA_REOPEN_STATUSES: frozenset[RequestStatus] = frozenset(
    {
        RequestStatus.AWAITING_APPROVAL,
        RequestStatus.RECONSIDERATION_PENDING,
        RequestStatus.APPROVED,
    }
)

# Urgency may be certified from these (Q-160: a declined urgency may later be certified) ...
CERTIFIABLE_URGENCY: frozenset[UrgencyStatus] = frozenset(
    {UrgencyStatus.AWAITING_CERTIFICATION, UrgencyStatus.NOT_CERTIFIED}
)


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    allowed: bool
    target: RequestStatus | None
    refusal: Refusal | None
    transition: Transition | None
    # True when entering the target closes the request: the service sets ``closed_at`` and
    # the requester access end (``ham.requester_portal.validity.normal_access_ends_at``).
    closes_request: bool = False
    # APPROVE / RECONSIDER_APPROVE: the approval is an urgent approval (§10, Q-161), so the
    # service records ``Approval.urgent_approval`` and the Director/AD alert fires now.
    urgent_approval: bool = False
    # RECONSIDER_*: record ``Approval.took_over_from_user_id`` (Q-157); None = no take-over.
    took_over_from: str | None = None


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
    # Step 3 facts
    now: datetime | None = None,
    closed_at: datetime | None = None,
    route: DecisionRoute | str | None = None,
    reason_code: RejectionReason | str | None = None,
    message: str = "",
    urgency: UrgencyStatus | str | None = None,
    certify_urgent: bool = False,
    reconsideration_deadline_at: datetime | None = None,
    has_reconsideration: bool = False,
    decision_undo_open: bool = False,
    actor_id: str | None = None,
    original_decider_id: str | None = None,
    original_decider_is_active_pastor: bool = True,
    take_over: bool = False,
    decider_unavailable_confirmed: bool = False,
) -> TransitionDecision:
    """Decide one transition. Pure: same inputs, same answer, every time.

    ``current`` is None for a request that does not exist yet (submission). Common guards
    run in this order: known action, source state, actor role, impersonation, not closed.
    Then, by action:

    - SUBMIT_VERIFIED: the contact was verified by an emailed code or link (Q-100).
    - SUBMIT_WITHOUT_EMAIL: the requester ticked "I don't use email" and gave no email (Q-025).
    - VERIFY_BY_PHONE: only from NEEDS_PHONE_CHECK; blocked while impersonating (Q-025).
    - COMPLETE_INTAKE_CHECKS: the duplicate check has finished (Q-106).
    - CANCEL: ``reason`` is one of the Q-107 codes; after a decision only
      "requester withdrew" (Q-165), and not while that decision can still be undone.
    - APPROVE: ``route`` chosen and held (Q-164); ``urgency`` passed (so an urgent approval
      is never missed); ``certify_urgent`` ("Approve as urgent") needs the pastoral route
      and a certifiable urgency (§10, Q-160).
    - REJECT: ``route`` as above; ``reason_code`` (Q-154) and a non-blank ``message``.
    - REQUEST_RECONSIDERATION: not closed, none used yet, the decline's undo window over,
      and ``now`` within ``reconsideration_deadline_at`` (§8.4, Q-155, Q-174).
    - RECONSIDER_APPROVE / RECONSIDER_REJECT: ``route`` is the recorded route of the
      decision being reconsidered; ``may_decide_reconsideration`` (Q-157); a non-blank
      ``message`` (the §8.4 "simple reason"); rejecting also needs ``reason_code``.
    - FINALIZE_REJECTION: not closed, no reconsideration, ``now`` past the deadline.
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
    roles = frozenset(actor_roles)
    if not (t.actors & roles):
        return _refuse(Refusal.ACTOR_NOT_ALLOWED, t)
    if t.blocked_while_impersonating and is_impersonating:
        return _refuse(Refusal.BLOCKED_WHILE_IMPERSONATING, t)
    _aware("now", now)
    _aware("closed_at", closed_at)
    _aware("reconsideration_deadline_at", reconsideration_deadline_at)
    if state is not None and closed_at is not None:
        return _refuse(Refusal.ALREADY_FINAL, t)

    urgent_approval = False
    took_over_from: str | None = None

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
        if state not in PRE_DECISION_STATUSES:
            # PRD-GAP Q-165: after a decision, only "requester withdrew".
            if cancel_reason not in POST_DECISION_CANCEL_REASONS:
                return _refuse(Refusal.REASON_NOT_ALLOWED, t)
            if decision_undo_open:
                return _refuse(Refusal.DECISION_UNDO_WINDOW_OPEN, t)
    elif act in (RequestAction.APPROVE, RequestAction.REJECT):
        refusal = _route_refusal(route, roles)
        if refusal is not None:
            return _refuse(refusal, t)
        if act is RequestAction.REJECT:
            refusal = _rejection_text_refusal(reason_code, message)
            if refusal is not None:
                return _refuse(refusal, t)
        else:
            known_urgency = _urgency(urgency)
            if known_urgency is None:
                return _refuse(Refusal.FACTS_MISSING, t)
            if certify_urgent:
                # §10, §67: only a pastor certifies; "Approve as urgent" is the pastoral route.
                if DecisionRoute(str(route)) is not DecisionRoute.PASTORAL:
                    return _refuse(Refusal.ACTOR_NOT_ALLOWED, t)
                if known_urgency not in CERTIFIABLE_URGENCY:
                    return _refuse(Refusal.URGENCY_NOT_CERTIFIABLE, t)
                known_urgency = UrgencyStatus.CERTIFIED
            urgent_approval = is_urgent_approval(t.target, known_urgency)
    elif act is RequestAction.REQUEST_RECONSIDERATION:
        if has_reconsideration:
            return _refuse(Refusal.RECONSIDERATION_ALREADY_USED, t)
        if decision_undo_open:
            return _refuse(Refusal.DECISION_UNDO_WINDOW_OPEN, t)
        if now is None or reconsideration_deadline_at is None:
            return _refuse(Refusal.FACTS_MISSING, t)
        if not may_request_reconsideration(now, reconsideration_deadline_at):
            return _refuse(Refusal.DEADLINE_PASSED, t)
    elif act in (RequestAction.RECONSIDER_APPROVE, RequestAction.RECONSIDER_REJECT):
        authority = may_decide_reconsideration(
            route,
            roles,
            actor_id=actor_id,
            original_decider_id=original_decider_id,
            original_decider_is_active_pastor=original_decider_is_active_pastor,
            take_over=take_over,
            decider_unavailable_confirmed=decider_unavailable_confirmed,
        )
        if not authority.allowed:
            return _refuse(authority.refusal or Refusal.ACTOR_NOT_ALLOWED, t)
        took_over_from = authority.took_over_from
        if act is RequestAction.RECONSIDER_REJECT:
            refusal = _rejection_text_refusal(reason_code, message)
            if refusal is not None:
                return _refuse(refusal, t)
        else:
            if not message.strip():
                return _refuse(Refusal.MESSAGE_REQUIRED, t)
            known_urgency = _urgency(urgency)
            if known_urgency is None:
                return _refuse(Refusal.FACTS_MISSING, t)
            urgent_approval = is_urgent_approval(t.target, known_urgency)
    elif act is RequestAction.FINALIZE_REJECTION:
        if has_reconsideration:
            return _refuse(Refusal.RECONSIDERATION_ALREADY_USED, t)
        if decision_undo_open:
            return _refuse(Refusal.DECISION_UNDO_WINDOW_OPEN, t)
        if now is None or reconsideration_deadline_at is None:
            return _refuse(Refusal.FACTS_MISSING, t)
        if may_request_reconsideration(now, reconsideration_deadline_at):
            return _refuse(Refusal.DEADLINE_NOT_REACHED, t)

    return TransitionDecision(
        allowed=True,
        target=t.target,
        refusal=None,
        transition=t,
        closes_request=t.closes_request,
        urgent_approval=urgent_approval,
        took_over_from=took_over_from,
    )


def _method(value: VerificationMethod | str | None) -> VerificationMethod | None:
    if value is None:
        return None
    try:
        return VerificationMethod(value)
    except ValueError:
        return None


def _urgency(value: UrgencyStatus | str | None) -> UrgencyStatus | None:
    if value is None:
        return None
    try:
        return UrgencyStatus(value)
    except ValueError:
        return None


def _route_refusal(route: DecisionRoute | str | None, roles: frozenset[str]) -> Refusal | None:
    """Q-164: a route must be chosen, and the actor must hold that route's role."""
    if route is None or route == "":
        return Refusal.ROUTE_REQUIRED
    try:
        chosen = DecisionRoute(route)
    except ValueError:
        return Refusal.ROUTE_NOT_HELD
    if ROUTE_ROLE[chosen] not in roles:
        return Refusal.ROUTE_NOT_HELD
    return None


def _rejection_text_refusal(
    reason_code: RejectionReason | str | None, message: str
) -> Refusal | None:
    """Q-154: a reason code from the list plus a non-blank kind message."""
    if reason_code is None or reason_code == "":
        return Refusal.REASON_REQUIRED
    try:
        RejectionReason(reason_code)
    except ValueError:
        return Refusal.REASON_NOT_ALLOWED
    if not message.strip():
        return Refusal.MESSAGE_REQUIRED
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
    """Always-closed statuses only. For "is this request closed?" use ``is_closed``."""
    return RequestStatus(status) in TERMINAL_STATUSES


def is_closed(status: RequestStatus | str, closed_at: datetime | None) -> bool:
    """Whether the request is closed (approvals.md §2.1; Q-116, Q-155).

    Closed = ``closed_at`` is set, or an always-closed status (CANCELLED). A REJECTED
    request is closed only once final. Statuses this module doesn't know (later project
    statuses) follow ``closed_at``. A never-closed status carrying ``closed_at`` is corrupt
    data and raises ``ValueError`` rather than guessing.
    """
    _aware("closed_at", closed_at)
    try:
        known: RequestStatus | None = RequestStatus(status)
    except ValueError:
        known = None
    if known in NEVER_CLOSED_STATUSES and closed_at is not None:
        raise ValueError(f"a {known} request cannot have closed_at")
    return closed_at is not None or known in TERMINAL_STATUSES


def is_pre_decision(status: RequestStatus | str) -> bool:
    return RequestStatus(status) in PRE_DECISION_STATUSES


def visible_to_approvers(status: RequestStatus | str) -> bool:
    """Pastors and the Board rep never see a request still waiting for a phone check
    (Q-025). A SUBMITTED request (duplicate check running) is visible, so a stalled job
    never hides a request; it only becomes "waiting for a decision" once AWAITING_APPROVAL."""
    return RequestStatus(status) not in PHONE_CHECK_STATUSES


def accepts_media_reopen(status: RequestStatus | str, closed_at: datetime | None) -> bool:
    """PRD-GAP Q-173: may a leader reopen requester uploads on this request?

    Only in AWAITING_APPROVAL, RECONSIDERATION_PENDING or APPROVED, and never once closed.
    A rejection that can still be reconsidered is refused (the requester must ask first).
    """
    if is_closed(status, closed_at):
        return False
    try:
        return RequestStatus(status) in MEDIA_REOPEN_STATUSES
    except ValueError:
        return False


def initial_urgency_status(urgent_requested: bool) -> UrgencyStatus:
    """On submission a ticked urgent flag waits for a pastor's certification (§10)."""
    return UrgencyStatus.AWAITING_CERTIFICATION if urgent_requested else UrgencyStatus.NONE


def requester_notified_of_cancellation(reason: CancelReason | str) -> bool:
    """Q-107: a kind closure note for every reason except spam/test."""
    return CancelReason(reason) is not CancelReason.SPAM


# --------------------------------------------------------------------------------------
# Urgency sub-machine (§10, §52; PRD-GAP Q-160, Q-161)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class UrgencyTransition:
    action: UrgencyAction
    sources: frozenset[UrgencyStatus]
    request_statuses: frozenset[RequestStatus]
    target: UrgencyStatus
    actors: frozenset[str]
    blocked_while_impersonating: bool
    audit_action: str
    outbox_event: str


URGENCY_TRANSITIONS: tuple[UrgencyTransition, ...] = (
    UrgencyTransition(
        action=UrgencyAction.CERTIFY_URGENCY,
        # Q-160: a declined urgency may later be certified.
        sources=CERTIFIABLE_URGENCY,
        # Q-160: also after approval -- a Board approval leaves urgency awaiting.
        request_statuses=frozenset({RequestStatus.AWAITING_APPROVAL, RequestStatus.APPROVED}),
        target=UrgencyStatus.CERTIFIED,
        actors=frozenset({PASTOR}),  # §10, §67: only a pastor certifies
        blocked_while_impersonating=True,  # Q-172
        audit_action="request.urgency_certified",
        outbox_event="UrgencyCertified",
    ),
    UrgencyTransition(
        action=UrgencyAction.DECLINE_URGENCY,
        sources=frozenset({UrgencyStatus.AWAITING_CERTIFICATION}),
        # approvals.md §2.2: "Not urgent: leave for normal review" is a pre-decision act.
        # PRD-GAP (new, see handback): declining after a Board approval is not allowed yet.
        request_statuses=frozenset({RequestStatus.AWAITING_APPROVAL}),
        target=UrgencyStatus.NOT_CERTIFIED,
        actors=frozenset({PASTOR}),
        blocked_while_impersonating=True,
        audit_action="request.urgency_not_certified",
        outbox_event="UrgencyNotCertified",
    ),
)

URGENCY_TRANSITIONS_BY_ACTION: dict[UrgencyAction, UrgencyTransition] = {
    t.action: t for t in URGENCY_TRANSITIONS
}


@dataclass(frozen=True, slots=True)
class UrgencyDecision:
    allowed: bool
    target: UrgencyStatus | None
    refusal: Refusal | None
    transition: UrgencyTransition | None
    # This change makes the request an urgent approval (it was already APPROVED): emit
    # ``UrgencyCertified`` with ``urgent_approval: true`` so the §10 alert fires (once).
    becomes_urgent_approval: bool = False


def check_urgency_transition(
    action: UrgencyAction | str,
    urgency: UrgencyStatus | str,
    request_status: RequestStatus | str,
    *,
    actor_roles: frozenset[str] | set[str],
    is_impersonating: bool = False,
    closed_at: datetime | None = None,
) -> UrgencyDecision:
    """Decide a pastor's urgency review (§10). Pure; refuses, never raises on business input.

    Guards in order: known action, request status, urgency status, actor, impersonation,
    not closed. A request the requester didn't flag (``NONE``) can never be certified (Q-160).
    """
    try:
        act = UrgencyAction(action)
    except ValueError:
        return UrgencyDecision(False, None, Refusal.UNKNOWN_ACTION, None)
    t = URGENCY_TRANSITIONS_BY_ACTION[act]

    def refuse(refusal: Refusal) -> UrgencyDecision:
        return UrgencyDecision(False, None, refusal, t)

    try:
        status = RequestStatus(request_status)
    except ValueError:
        return refuse(Refusal.WRONG_STATE)
    if status not in t.request_statuses:
        return refuse(Refusal.WRONG_STATE)
    current = _urgency(urgency)
    if current is None or current not in t.sources:
        return refuse(Refusal.WRONG_URGENCY_STATE)
    if not (t.actors & frozenset(actor_roles)):
        return refuse(Refusal.ACTOR_NOT_ALLOWED)
    if t.blocked_while_impersonating and is_impersonating:
        return refuse(Refusal.BLOCKED_WHILE_IMPERSONATING)
    _aware("closed_at", closed_at)
    if closed_at is not None:
        return refuse(Refusal.ALREADY_FINAL)
    return UrgencyDecision(
        allowed=True,
        target=t.target,
        refusal=None,
        transition=t,
        becomes_urgent_approval=becomes_urgent_approval(status, current, status, t.target),
    )


def is_urgent_approval(
    request_status: RequestStatus | str, urgency: UrgencyStatus | str | None
) -> bool:
    """PRD-GAP Q-161: an urgent approval = APPROVED and urgency CERTIFIED, in either order.

    Only certified urgency counts: a Board approval of a flagged request (urgency still
    awaiting certification) is not an urgent approval until a pastor certifies (Q-160).
    """
    return (
        str(request_status) == RequestStatus.APPROVED
        and urgency is not None
        and str(urgency) == UrgencyStatus.CERTIFIED
    )


def becomes_urgent_approval(
    before_status: RequestStatus | str,
    before_urgency: UrgencyStatus | str | None,
    after_status: RequestStatus | str,
    after_urgency: UrgencyStatus | str | None,
) -> bool:
    """True exactly when a change makes the request an urgent approval -- whichever of
    approval and certification happens second. Use it so the §10 alerts fire once."""
    return not is_urgent_approval(before_status, before_urgency) and is_urgent_approval(
        after_status, after_urgency
    )


# --------------------------------------------------------------------------------------
# Reconsideration (§8.4; Q-155, Q-157, Q-164, Q-174)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ReconsiderationAuthority:
    allowed: bool
    refusal: Refusal | None = None
    # The original decider this actor takes over from (record it on the Approval row and
    # tell that person in-app); None when the actor is the original decider or on the Board.
    took_over_from: str | None = None


def may_decide_reconsideration(
    route: DecisionRoute | str | None,
    actor_roles: frozenset[str] | set[str],
    *,
    actor_id: str | None,
    original_decider_id: str | None,
    original_decider_is_active_pastor: bool = True,
    take_over: bool = False,
    decider_unavailable_confirmed: bool = False,
) -> ReconsiderationAuthority:
    """Who may decide a reconsideration (approvals.md §2.3; PRD-GAP Q-157, Q-164).

    ``route`` is the route RECORDED on the decision being reconsidered (Q-164: it follows
    that decision; the actor does not choose again).

    - Board route: any Board representative.
    - Pastoral route: the original pastor. Another pastor only by taking it over, in one
      step, with the required tick "Pastor X isn't available to decide this" (Q-157). If the
      original pastor no longer holds an active Pastor role, every pastor may decide it
      without the tick, and the take-over is still recorded.
    """
    roles = frozenset(actor_roles)
    refusal = _route_refusal(route, roles)
    if refusal is not None:
        return ReconsiderationAuthority(False, refusal)
    if DecisionRoute(str(route)) is DecisionRoute.BOARD:
        return ReconsiderationAuthority(True)
    if not actor_id or not original_decider_id:
        return ReconsiderationAuthority(False, Refusal.FACTS_MISSING)
    if str(actor_id) == str(original_decider_id):
        return ReconsiderationAuthority(True)
    if not original_decider_is_active_pastor:
        return ReconsiderationAuthority(True, took_over_from=str(original_decider_id))
    if not take_over:
        return ReconsiderationAuthority(False, Refusal.NOT_YOUR_RECONSIDERATION)
    if not decider_unavailable_confirmed:
        return ReconsiderationAuthority(False, Refusal.TAKE_OVER_CONFIRMATION_REQUIRED)
    return ReconsiderationAuthority(True, took_over_from=str(original_decider_id))


def _zone(church_tz: tzinfo | str) -> tzinfo:
    return ZoneInfo(church_tz) if isinstance(church_tz, str) else church_tz


def reconsideration_last_day(
    decided_at: datetime, church_tz: tzinfo | str, *, rules: Rules = RULES
) -> date:
    """The church-local date printed in the decline email: "You can ask until {date}".

    PRD-GAP Q-174: the decision's church-local calendar day plus
    ``RECONSIDERATION_REQUEST_WINDOW`` calendar days (Q-155: 14).
    """
    _aware("decided_at", decided_at, required=True)
    local_day = decided_at.astimezone(_zone(church_tz)).date()
    return local_day + timedelta(days=rules.approvals.RECONSIDERATION_REQUEST_WINDOW)


def reconsideration_deadline(
    decided_at: datetime, church_tz: tzinfo | str, *, rules: Rules = RULES
) -> datetime:
    """The last instant a reconsideration may be asked for, in UTC (PRD-GAP Q-174).

    The end (23:59:59.999999) of the church-local calendar day ``reconsideration_last_day``.
    Calendar arithmetic, so a DST change inside the window neither shortens nor lengthens
    the day printed in the email. Store it on the request when the decline is recorded; an
    undone and re-made decline gets a new one from the new ``decided_at``.
    """
    zone = _zone(church_tz)
    last_day = reconsideration_last_day(decided_at, zone, rules=rules)
    return datetime.combine(last_day, time.max, tzinfo=zone).astimezone(UTC)


def may_request_reconsideration(now: datetime, deadline: datetime) -> bool:
    """Still in time to ask (§8.4)? Inclusive: the deadline is the day's last instant, so the
    first instant of the next church-local day is too late. FINALIZE_REJECTION is allowed
    exactly when this is False."""
    _aware("now", now, required=True)
    _aware("deadline", deadline, required=True)
    return now <= deadline


# --------------------------------------------------------------------------------------
# Undo (Q-156 decided; PRD-GAP Q-176 details)
# --------------------------------------------------------------------------------------
def undo_window_ends_at(decided_at: datetime, *, rules: Rules = RULES) -> datetime:
    """When the decider's undo ends and the held effects (requester email, batch close,
    question withdrawal, leader updates) are released (Q-176)."""
    _aware("decided_at", decided_at, required=True)
    return decided_at + rules.approvals.DECISION_UNDO_WINDOW


def decision_is_undoable(
    decided_at: datetime,
    now: datetime,
    undone_at: datetime | None,
    *,
    rules: Rules = RULES,
) -> bool:
    """Can this decision still be undone? Not undone yet, and ``now`` before the window ends
    (``decided_at`` + 30 min; at exactly 30:00 it is too late -- the held effects go)."""
    _aware("now", now, required=True)
    _aware("undone_at", undone_at)
    return undone_at is None and now < undo_window_ends_at(decided_at, rules=rules)


# What each undoable decision restores (the prior state), and the state it produced.
_UNDO_REQUEST_DECISIONS: dict[RequestAction, tuple[RequestStatus, RequestStatus]] = {
    RequestAction.APPROVE: (RequestStatus.AWAITING_APPROVAL, RequestStatus.APPROVED),
    RequestAction.REJECT: (RequestStatus.AWAITING_APPROVAL, RequestStatus.REJECTED),
    RequestAction.RECONSIDER_APPROVE: (
        RequestStatus.RECONSIDERATION_PENDING,
        RequestStatus.APPROVED,
    ),
    RequestAction.RECONSIDER_REJECT: (
        RequestStatus.RECONSIDERATION_PENDING,
        RequestStatus.REJECTED,
    ),
}
UNDOABLE_ACTIONS: frozenset[RequestAction | UrgencyAction] = frozenset(
    {*_UNDO_REQUEST_DECISIONS, *UrgencyAction}
)


@dataclass(frozen=True, slots=True)
class UndoDecision:
    allowed: bool
    refusal: Refusal | None = None
    # The state to restore. ``restore_urgency`` is None when urgency is left as it is.
    restore_status: RequestStatus | None = None
    restore_urgency: UrgencyStatus | None = None
    # RECONSIDER_REJECT closed the request: clear ``closed_at`` and the access end.
    reopens_request: bool = False
    # REJECT stored a reconsideration deadline: clear it (a re-made decline gets a new one).
    clears_reconsideration_deadline: bool = False
    # The undone decision had made the request an urgent approval, whose alert was never
    # held: send Director/AD the in-app "urgent approval was undone" follow-up (Q-176).
    urgent_approval_undone: bool = False


def _undo_refuse(refusal: Refusal) -> UndoDecision:
    return UndoDecision(False, refusal)


def _decision_kind(
    value: RequestAction | UrgencyAction | str,
) -> RequestAction | UrgencyAction | None:
    for enum in (RequestAction, UrgencyAction):
        try:
            return enum(value)  # type: ignore[no-any-return]
        except ValueError:
            continue
    return None


def check_undo(
    decision: RequestAction | UrgencyAction | str,
    *,
    actor_id: str | None,
    decided_by_id: str | None,
    decided_at: datetime,
    now: datetime,
    undone_at: datetime | None,
    current_status: RequestStatus | str,
    current_urgency: UrgencyStatus | str | None,
    prior_urgency: UrgencyStatus | str | None = None,
    is_impersonating: bool = False,
    rules: Rules = RULES,
) -> UndoDecision:
    """May ``actor_id`` undo this decision, and what does undoing restore? (Q-156, Q-176)

    A pure function of the decision and the state it produced -- not a free edge:

    - Undoable: APPROVE, REJECT, RECONSIDER_APPROVE, RECONSIDER_REJECT, CERTIFY_URGENCY and
      DECLINE_URGENCY. Everything else refuses ``NOT_UNDOABLE``.
    - Only the person who recorded it, never while impersonating (Q-172), once, and only
      while ``decision_is_undoable``.
    - The request must still be in the state the decision produced (the decision's status
      for request decisions, its urgency for urgency reviews); otherwise
      ``STATE_CHANGED_SINCE_DECISION``.
    - ``prior_urgency`` is the urgency before the decision. Required for urgency reviews;
      for APPROVE pass it only when the same command also certified urgency ("Approve as
      urgent"), so the undo restores both.
    """
    kind = _decision_kind(decision)
    if kind is None or kind not in UNDOABLE_ACTIONS:
        return _undo_refuse(Refusal.NOT_UNDOABLE)
    if is_impersonating:
        return _undo_refuse(Refusal.BLOCKED_WHILE_IMPERSONATING)
    if not actor_id or not decided_by_id:
        return _undo_refuse(Refusal.FACTS_MISSING)
    if str(actor_id) != str(decided_by_id):
        return _undo_refuse(Refusal.NOT_THE_DECIDER)
    _aware("undone_at", undone_at)
    if undone_at is not None:
        return _undo_refuse(Refusal.ALREADY_UNDONE)
    if not decision_is_undoable(decided_at, now, undone_at, rules=rules):
        return _undo_refuse(Refusal.UNDO_WINDOW_PASSED)

    try:
        status = RequestStatus(current_status)
    except ValueError:
        return _undo_refuse(Refusal.STATE_CHANGED_SINCE_DECISION)
    urgency_now = _urgency(current_urgency)
    if urgency_now is None:
        return _undo_refuse(Refusal.FACTS_MISSING)  # needed for the urgent follow-up
    prior_u = None if prior_urgency is None else _urgency(prior_urgency)
    if prior_urgency is not None and prior_u is None:
        return _undo_refuse(Refusal.FACTS_MISSING)

    if isinstance(kind, UrgencyAction):
        t = URGENCY_TRANSITIONS_BY_ACTION[kind]
        if prior_u is None or prior_u not in t.sources:
            return _undo_refuse(Refusal.FACTS_MISSING)
        if urgency_now is not t.target:
            return _undo_refuse(Refusal.STATE_CHANGED_SINCE_DECISION)
        return UndoDecision(
            allowed=True,
            restore_status=status,
            restore_urgency=prior_u,
            urgent_approval_undone=is_urgent_approval(status, urgency_now)
            and not is_urgent_approval(status, prior_u),
        )

    prior_status, produced = _UNDO_REQUEST_DECISIONS[kind]
    if status is not produced:
        return _undo_refuse(Refusal.STATE_CHANGED_SINCE_DECISION)
    restore_urgency: UrgencyStatus | None = None
    if prior_u is not None:
        # Only "Approve as urgent" changes urgency together with a decision.
        if kind is not RequestAction.APPROVE or prior_u not in CERTIFIABLE_URGENCY:
            return _undo_refuse(Refusal.FACTS_MISSING)
        if urgency_now is not UrgencyStatus.CERTIFIED:
            return _undo_refuse(Refusal.STATE_CHANGED_SINCE_DECISION)
        restore_urgency = prior_u
    urgency_after = restore_urgency or urgency_now
    return UndoDecision(
        allowed=True,
        restore_status=prior_status,
        restore_urgency=restore_urgency,
        reopens_request=TRANSITIONS_BY_ACTION[kind].closes_request,
        clears_reconsideration_deadline=kind is RequestAction.REJECT,
        urgent_approval_undone=is_urgent_approval(status, urgency_now)
        and not is_urgent_approval(prior_status, urgency_after),
    )


def _aware(name: str, value: datetime | None, *, required: bool = False) -> None:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware (UTC)")
