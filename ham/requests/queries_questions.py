"""S3.3 read side for HAM questions (approvals.md §2.5; approvals-contracts.md §1.4).

- `waiting_on_requester(ctx)`: the "Waiting on requester" list view (a filter, not a status --
  approvals.md §2.5 "it does not pause anything and does not block a decision") -- requests
  scoped to this viewer with at least one open question, rows restricted to HAM # + category
  only (Q-132's own list-row rule, reused here).
- `question_thread(ctx, request_id)`: the leadership detail page's question thread (L16),
  masking the answer text for the Administrator's read-only view (Q-124/Q-151 -- "sees the
  question text and 'Answered on {date}', never answer text").
- `requester_question_thread(request_id)`: the plain (unmasked -- there is no Administrator
  concept on the requester's own secure page) thread for the requester's own R14 card(s).
  S3.4 owns the requester portal page/projection as a whole; this is offered as a ready-made
  building block in case it's useful there rather than a second, independent read of the same
  rows -- not a claim on S3.4's own file.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import QuerySet

from .models import AssistanceRequest, RequestQuestion
from .queries import is_masked_view, scope_queryset_for_requests

if TYPE_CHECKING:
    from ham.authz.context import ActorContext

QUESTION_STATUS_OPEN = "open"
QUESTION_STATUS_ANSWERED = "answered"
QUESTION_STATUS_CLOSED = "closed"


# ------------------------------------------------------------------------------------------
# "Waiting on requester"
# ------------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True, slots=True)
class WaitingOnRequesterRow:
    """approvals.md §2.5 "a chip on list rows and on the detail page" / Q-132's "rows still
    show HAM # + category only" -- reused here for the dedicated list view. No status, no
    urgency flag, no age, no PII: just enough to open the request."""

    id: UUID
    display_number: str
    need_category: str


def waiting_on_requester(ctx: ActorContext) -> list[WaitingOnRequesterRow]:
    """Requests, scoped to this viewer the same way `request.list` is
    (`ham.requests.queries.scope_queryset_for_requests`), that carry at least one open
    (unanswered, not withdrawn/closed) question. A list *view*: nothing here pauses a
    decision or blocks an approver (approvals.md §2.5)."""
    qs: QuerySet[AssistanceRequest] = (
        AssistanceRequest.objects.filter(
            questions__answered_at__isnull=True, questions__closed_at__isnull=True
        )
        .distinct()
        .order_by("-urgent_requested", "submitted_at")
    )
    qs = scope_queryset_for_requests(ctx, qs)
    return [
        WaitingOnRequesterRow(
            id=r.id, display_number=r.display_number, need_category=r.need_category
        )
        for r in qs
    ]


# ------------------------------------------------------------------------------------------
# Question thread (leadership L16 / requester R14)
# ------------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True, slots=True)
class QuestionRow:
    """One question/answer entry. `status` is derived, never stored (`RequestQuestion` itself
    keeps no status column). When `masked` is true (Administrator, Q-124/Q-151), `answer` is
    always `""` regardless of what's actually recorded -- the template renders "Answered on
    {answered_at}" from `status`/`answered_at` alone, never `answer`."""

    id: UUID
    question: str
    asked_by_user_id: UUID
    asked_at: dt.datetime
    status: str
    answer: str
    answered_at: dt.datetime | None
    answered_via: str
    close_reason: str
    closed_at: dt.datetime | None
    masked: bool


def _status_of(question: RequestQuestion) -> str:
    if question.answered_at is not None:
        return QUESTION_STATUS_ANSWERED
    if question.closed_at is not None:
        return QUESTION_STATUS_CLOSED
    return QUESTION_STATUS_OPEN


def _row(question: RequestQuestion, *, masked: bool) -> QuestionRow:
    return QuestionRow(
        id=question.id,
        question=question.question,
        asked_by_user_id=question.asked_by_user_id,
        asked_at=question.asked_at,
        status=_status_of(question),
        answer="" if masked else question.answer,
        answered_at=question.answered_at,
        answered_via=question.answered_via,
        close_reason=question.close_reason,
        closed_at=question.closed_at,
        masked=masked,
    )


def question_thread(ctx: ActorContext, request_id: UUID) -> list[QuestionRow]:
    """The leadership detail page's question thread (L16). Every `request.view` holder may see
    it, including the Administrator -- whose view is masked (`ham.requests.queries.
    is_masked_view`, the same Q-124/Q-151 rule the contact-details panel and the duplicate
    history already use) so `answer` never carries the requester's own words, which can hold
    contact details the same way `contact_note` can (approvals.md §2.5)."""
    masked = is_masked_view(ctx)
    questions = RequestQuestion.objects.filter(request_id=request_id).order_by("asked_at")
    return [_row(q, masked=masked) for q in questions]


def requester_question_thread(request_id: UUID) -> list[QuestionRow]:
    """The requester's own view of their request's questions (R14) -- never masked (there is
    no Administrator concept on the requester's own secure page); a closed question's card is
    a display-time decision (approvals.md §2.5 "no card once the request is closed"), not a
    filter here, since the same rows also back an audit-style leadership view that must keep
    seeing withdrawn/closed questions."""
    questions = RequestQuestion.objects.filter(request_id=request_id).order_by("asked_at")
    return [_row(q, masked=False) for q in questions]
