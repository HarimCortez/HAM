"""S3.4: the secure-page card data (R10-R19; docs/ux/approvals.md §6, design-system/screens/
approvals.md §5). Called by `ham.web`'s secure-page view (S3.7) with a request id that has
*already* been resolved from a link token (`ham.requester_portal.services.resolve_token`) --
this module never sees, decrypts or shows the token itself, and never scopes by session; the
one thing it takes is the id the token already resolved to (intake-contracts.md §1
`Scope.OWN_REQUEST`).

Calls `ham.requests` services/models directly, a legal downward import (`ham.web ->
ham.requester_portal -> ham.media -> ham.requests -> ...`) -- no outbox-registry indirection,
since this is a plain, unauthenticated-beyond-the-token read, same shape as S2.7's own
`get_request_for_requester` call. Question cards read `RequestQuestion` directly today
(S3.3's own query/service layer is a parallel, not-yet-merged slice); once S3.3 lands, swap
`_question_cards` for its query instead of re-deriving open/answered/closed here (TODO below).

Never carries the decider's identity or route anywhere in this module's output (Q-171).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID
from zoneinfo import ZoneInfo

from ham.platform.church import church_profile
from ham.platform.clock import now as clock_now
from ham.requests.models import Approval as ApprovalModel
from ham.requests.models import (
    ApprovalOutcome,
    ApprovalStage,
    Reconsideration,
    RequestQuestion,
)
from ham.requests.models import (
    AssistanceRequest as AssistanceRequestModel,
)
from ham.requests.queries import RequesterPageRow, get_request_for_requester
from ham.requests.states import RequestStatus, UrgencyStatus, may_request_reconsideration

from . import projection
from .validity import normal_access_ends_at

# Q-176: the prior status a live, not-yet-effective decision's stage produced *from* --
# "during the undo window, nothing changes for the requester" (task brief §2): the page shows
# the state as of the last *effective* decision, never a just-recorded, still-undoable one.
_STAGE_PRIOR_STATUS: dict[str, RequestStatus] = {
    ApprovalStage.INITIAL.value: RequestStatus.AWAITING_APPROVAL,
    ApprovalStage.RECONSIDERATION.value: RequestStatus.RECONSIDERATION_PENDING,
}

_DECIDED_STATUSES = frozenset({RequestStatus.APPROVED.value, RequestStatus.REJECTED.value})


@dataclass(frozen=True, slots=True)
class StatusCard:
    """The status chip + sentence + "what happens next" list (R10's per-status table)."""

    status: str
    chip_label: str
    chip_tone: str
    chip_icon: str
    sentence: str
    next_steps: list[str]
    # R14/R18a, urgent-certified only; "" otherwise.
    urgent_alert: str


@dataclass(frozen=True, slots=True)
class DecisionCard:
    """R14/R15/R17/R18's decision content. Never the decider's identity or route (Q-171) --
    those fields simply don't exist on this dataclass."""

    outcome: str  # ApprovalOutcome: "approved" | "rejected"
    stage: str  # ApprovalStage: "initial" | "reconsideration"
    closed: bool  # final -- a rejection that can no longer be reconsidered
    reason_message: str  # "" unless outcome == "rejected"


@dataclass(frozen=True, slots=True)
class ReconsiderEligibility:
    """R15's "Ask us to reconsider" block. `None` on the page's own `reconsider` field when
    the request isn't in a state where asking could ever make sense."""

    eligible: bool
    already_requested: bool
    last_day: dt.date | None
    ask_line: str  # "" when last_day is None


@dataclass(frozen=True, slots=True)
class QuestionCard:
    """R13 (open) / "Questions and answers" (answered). Never the asker's identity (R13 shows
    only "From HAM", no leader name -- G3-11)."""

    id: UUID
    question: str
    answer: str
    status: str  # "open" | "answered"
    asked_at: dt.datetime
    answered_at: dt.datetime | None


@dataclass(frozen=True, slots=True)
class SecurePageData:
    """What `ham.web`'s secure-page view (S3.7) renders. `decision`/`reconsider` are `None`
    when the current (effective) status has no decision content to show."""

    status: StatusCard
    decision: DecisionCard | None
    reconsider: ReconsiderEligibility | None
    open_questions: tuple[QuestionCard, ...]
    answered_questions: tuple[QuestionCard, ...]
    # R17 "What you told us" -- her own note (Q-158), "" when she left it blank or hasn't
    # asked. Never the leaders' own reconsideration reason (that's `Approval.reason`, not
    # this -- and it's never shown to the requester at all).
    reconsideration_note: str
    reconsideration_requested_at: dt.datetime | None
    # R18b/R18c footer "This page will stay available until {date}." -- the church-local
    # calendar date normal access ends, only set once the request is finally closed.
    access_ends_at: dt.date | None


def _effective_status_and_closed(
    row: RequesterPageRow, live_approvals: list[ApprovalModel], now: dt.datetime
) -> tuple[str, dt.datetime | None]:
    """Q-176: the request's own `status`/`closed_at` flip the instant a decision is recorded,
    but the requester's own page must keep showing the *prior* state until that decision's
    `effective_at` passes -- the held effects (including what the requester is told) wait out
    the undo window too (approvals-contracts.md §4)."""
    if not live_approvals:
        return row.status, row.closed_at
    latest = max(live_approvals, key=lambda a: a.decided_at)
    if now >= latest.effective_at:
        return row.status, row.closed_at
    prior = _STAGE_PRIOR_STATUS.get(latest.stage)
    if prior is None:  # pragma: no cover - defensive; every live stage is in the map
        return row.status, row.closed_at
    return prior.value, None


def _status_card(
    status: str,
    *,
    closed: dt.datetime | None,
    decision: DecisionCard | None,
    urgent_certified: bool,
    cancel_reason: str | None = None,
    has_open_question: bool = False,
) -> StatusCard:
    closed_flag = closed is not None
    after_reconsideration = (
        decision is not None and decision.stage == ApprovalStage.RECONSIDERATION.value
    )

    if status == RequestStatus.APPROVED.value:
        chip = projection.REQUESTER_STATUS_CHIPS[RequestStatus.APPROVED.value]
        return StatusCard(
            status=status,
            chip_label=chip[0],
            chip_tone=chip[1],
            chip_icon=chip[2],
            sentence=projection.approved_sentence(after_reconsideration=after_reconsideration),
            next_steps=list(projection.APPROVED_NEXT_STEPS),
            urgent_alert=projection.URGENT_CERTIFIED_ALERT if urgent_certified else "",
        )

    if status == RequestStatus.REJECTED.value:
        chip = projection.rejected_chip(closed=closed_flag)
        if closed_flag:
            sentence = projection.rejected_final_sentence(
                after_reconsideration=after_reconsideration
            )
            next_steps = [projection.REJECTED_FINAL_NEXT_STEP]
        else:
            sentence = projection.rejected_open_sentence()
            next_steps = [projection.RECONSIDER_OFFER_LINE, projection.REJECTED_SYMPATHY_LINE]
        return StatusCard(
            status=status,
            chip_label=chip[0],
            chip_tone=chip[1],
            chip_icon=chip[2],
            sentence=sentence,
            next_steps=next_steps,
            urgent_alert="",
        )

    if status == RequestStatus.RECONSIDERATION_PENDING.value:
        chip = projection.REQUESTER_STATUS_CHIPS[RequestStatus.RECONSIDERATION_PENDING.value]
        return StatusCard(
            status=status,
            chip_label=chip[0],
            chip_tone=chip[1],
            chip_icon=chip[2],
            sentence=projection.reconsideration_pending_sentence(),
            next_steps=[projection.RECONSIDERATION_PENDING_NEXT_STEP],
            urgent_alert="",
        )

    # Step 1-2 statuses (SUBMITTED, NEEDS_PHONE_CHECK, AWAITING_APPROVAL, CANCELLED) keep the
    # existing step-2 wording (`projection.status_wording`/`STATUS_NEXT_STEPS`), plus the
    # step-3 "question open" row (R10 table: "Awaiting Approval + question open").
    chip_tuple = projection.REQUESTER_STATUS_CHIPS.get(status)
    next_steps = projection.STATUS_NEXT_STEPS.get(status, [])
    if status == RequestStatus.AWAITING_APPROVAL.value and has_open_question:
        next_steps = [projection.AWAITING_APPROVAL_QUESTION_NEXT_STEP]
    return StatusCard(
        status=status,
        chip_label=chip_tuple[0] if chip_tuple else status,
        chip_tone=chip_tuple[1] if chip_tuple else "neutral",
        chip_icon=chip_tuple[2] if chip_tuple else "circle-help",
        sentence=projection.status_wording(status, cancel_reason=cancel_reason),
        next_steps=next_steps,
        urgent_alert="",
    )


def _reconsider_eligibility(
    *,
    decision: DecisionCard | None,
    already_requested: bool,
    deadline_at: dt.datetime | None,
    now: dt.datetime,
) -> ReconsiderEligibility | None:
    """R15's reconsider block -- only meaningful for an open (not yet final) rejection."""
    if decision is None or decision.outcome != ApprovalOutcome.REJECTED.value or decision.closed:
        return None
    if deadline_at is None:  # pragma: no cover - defensive; REJECT always sets this (Q-155)
        return ReconsiderEligibility(
            eligible=False, already_requested=already_requested, last_day=None, ask_line=""
        )
    church_tz = ZoneInfo(church_profile().time_zone)
    last_day = deadline_at.astimezone(church_tz).date()
    eligible = not already_requested and may_request_reconsideration(now, deadline_at)
    return ReconsiderEligibility(
        eligible=eligible,
        already_requested=already_requested,
        last_day=last_day,
        ask_line=projection.reconsider_ask_line(last_day),
    )


def _question_cards(
    request_id: UUID,
) -> tuple[tuple[QuestionCard, ...], tuple[QuestionCard, ...]]:
    """(open, answered) -- withdrawn/auto-closed questions are never shown to the requester
    (R19 "Question withdrawn: card removed").

    TODO(S3.3): once `ham.requests.services_questions`/its query module merges, switch this to
    that module's own requester-facing query instead of a direct `RequestQuestion` read -- kept
    here as a thin, obviously-correct placeholder so S3.4/S3.7 aren't blocked on that slice.
    """
    open_cards: list[QuestionCard] = []
    answered_cards: list[QuestionCard] = []
    questions = RequestQuestion.objects.filter(request_id=request_id).order_by("asked_at")
    for q in questions:
        if q.closed_at is not None:
            continue
        if q.answered_at is not None:
            answered_cards.append(
                QuestionCard(
                    id=q.id,
                    question=q.question,
                    answer=q.answer,
                    status="answered",
                    asked_at=q.asked_at,
                    answered_at=q.answered_at,
                )
            )
        else:
            open_cards.append(
                QuestionCard(
                    id=q.id,
                    question=q.question,
                    answer="",
                    status="open",
                    asked_at=q.asked_at,
                    answered_at=None,
                )
            )
    return tuple(open_cards), tuple(answered_cards)


def secure_page_data(request_id: UUID, *, now: dt.datetime | None = None) -> SecurePageData | None:
    """Everything the secure page (R10 and on) needs about decisions/reconsideration/
    questions. `None` when `request_id` doesn't exist (defensive; the caller's own token
    resolution already guarantees a live request in practice)."""
    now = now or clock_now()
    row = get_request_for_requester(request_id)
    if row is None:
        return None

    live_approvals = list(
        ApprovalModel.objects.filter(request_id=request_id, undone_at__isnull=True)
    )
    effective_status, effective_closed_at = _effective_status_and_closed(row, live_approvals, now)

    effective_decision_row: ApprovalModel | None = None
    if live_approvals and effective_status in _DECIDED_STATUSES:
        latest = max(live_approvals, key=lambda a: a.decided_at)
        if now >= latest.effective_at:
            effective_decision_row = latest

    facts = (
        AssistanceRequestModel.objects.filter(id=request_id)
        .values_list("urgency_status", "reconsideration_deadline_at")
        .first()
    )
    urgency_status, deadline_at = facts if facts is not None else ("", None)

    decision_card: DecisionCard | None = None
    if effective_decision_row is not None:
        decision_card = DecisionCard(
            outcome=effective_decision_row.outcome,
            stage=effective_decision_row.stage,
            closed=effective_closed_at is not None,
            reason_message=(
                effective_decision_row.reason
                if effective_decision_row.outcome == ApprovalOutcome.REJECTED.value
                else ""
            ),
        )

    urgent_certified = (
        decision_card is not None
        and decision_card.outcome == ApprovalOutcome.APPROVED.value
        and urgency_status == UrgencyStatus.CERTIFIED.value
    )

    open_questions, answered_questions = _question_cards(request_id)

    status_card = _status_card(
        effective_status,
        closed=effective_closed_at,
        decision=decision_card,
        urgent_certified=urgent_certified,
        cancel_reason=row.cancel_reason_code or None,
        has_open_question=bool(open_questions),
    )

    reconsideration = Reconsideration.objects.filter(request_id=request_id).first()
    already_requested = reconsideration is not None
    reconsider = _reconsider_eligibility(
        decision=decision_card,
        already_requested=already_requested,
        deadline_at=deadline_at,
        now=now,
    )

    access_ends_at: dt.date | None = None
    if effective_closed_at is not None:
        church_tz = ZoneInfo(church_profile().time_zone)
        access_end = normal_access_ends_at(status=effective_status, closed_at=effective_closed_at)
        if access_end is not None:
            access_ends_at = access_end.astimezone(church_tz).date()

    return SecurePageData(
        status=status_card,
        decision=decision_card,
        reconsider=reconsider,
        open_questions=open_questions,
        answered_questions=answered_questions,
        reconsideration_note=reconsideration.requester_note if reconsideration else "",
        reconsideration_requested_at=reconsideration.requested_at if reconsideration else None,
        access_ends_at=access_ends_at,
    )


__all__ = [
    "DecisionCard",
    "QuestionCard",
    "ReconsiderEligibility",
    "SecurePageData",
    "StatusCard",
    "secure_page_data",
]
