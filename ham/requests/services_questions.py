"""S3.0 seam (approvals.md §8.1, §2.5; approvals-contracts.md §2): the exact signatures S3.3
(HAM questions) commits to, so the parallel S3.2/S3.4 slices can code against them. See
`ham.requests.services_decisions`'s module docstring for the same "stub, not yet
`@command`-wrapped" convention -- `close_open_questions` is the one exception: it is a real,
plain (non-`@command`) function, not a stub, because S3.2's decision commands (approve/
reject/reconsider) call it *inside their own transaction* the moment a decision closes open
questions (approvals.md §2.2 "auto-closes open questions ... in the same transaction"), and
S3.0 fixes its exact behavior so S3.2 doesn't have to guess at it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from ham.platform.clock import now as clock_now

from .models import QuestionCloseReason, RequestQuestion

if TYPE_CHECKING:
    from ham.authz.context import ActorContext, RequesterContext


def ask_question(
    ctx: ActorContext, *, request_id: UUID, question: str, phone_answer: str = ""
) -> RequestQuestion:
    """`request.question.ask` (DIR, AD, PAS, BRD; §7.2, Q-162; any request that isn't closed,
    not NEEDS_PHONE_CHECK). `phone_answer` (no-email requests only): when given, creates the
    question and records the phone answer in one step (approvals.md §2.5) instead of leaving
    it open for a callback."""
    raise NotImplementedError("S3.3: ham.requests.services_questions.ask_question")


def answer_question(ctx: RequesterContext, *, question_id: UUID, answer: str) -> None:
    """`requester.question.answer` (own request only; one answer per question)."""
    raise NotImplementedError("S3.3: ham.requests.services_questions.answer_question")


def record_phone_answer(ctx: ActorContext, *, question_id: UUID, answer: str) -> None:
    """`request.question.record_answer` (DIR, AD, PAS, BRD; §7.2, no-email requesters)."""
    raise NotImplementedError("S3.3: ham.requests.services_questions.record_phone_answer")


def withdraw_question(ctx: ActorContext, *, question_id: UUID) -> None:
    """`request.question.withdraw` (matrix: DIR, AD, PAS, BRD; service-layer finer rule --
    only the asker, Director or AD, per approvals.md §3's "Finer rules the matrix can't
    express")."""
    raise NotImplementedError("S3.3: ham.requests.services_questions.withdraw_question")


def close_open_questions(request_id: UUID, *, reason: str) -> int:
    """Withdraws every open (unanswered, not yet closed) `RequestQuestion` on `request_id`
    (Q-162, amended: "open questions are withdrawn automatically when any decision is
    recorded"). `reason` is a `QuestionCloseReason` value -- `request_closed` for this
    auto-close path (`withdrawn` is the human-triggered `withdraw_question` action above).

    A **plain function**, not `@command`-wrapped and not itself authorized/audited: it is
    always called from *inside* another command's own transaction (a decision, a cancel) as
    one of that command's own side effects, not as a standalone consequential action of its
    own -- approvals.md §2.2's "auto-closes open questions ... in the same transaction".
    `closed_by_user_id` is left null (no single human actor "did" this withdrawal; the
    decision's own audit event is the record of what caused it).

    Returns the number of questions closed."""
    close_reason = QuestionCloseReason(reason)
    now = clock_now()
    updated = 0
    open_questions = RequestQuestion.objects.filter(
        request_id=request_id, answered_at__isnull=True, closed_at__isnull=True
    )
    for open_question in open_questions:
        open_question.closed_at = now
        open_question.close_reason = close_reason.value
        open_question.save(update_fields=["closed_at", "close_reason"])
        updated += 1
    return updated
