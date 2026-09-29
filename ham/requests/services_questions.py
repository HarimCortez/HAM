"""S3.3 real implementation of the seam S3.0 declared (approvals.md §2.5; approvals-contracts.md
§2): HAM's questions to the requester and the requester's answers.

Text limits (owner decisions box, `docs/architecture/approvals.md`, 2026-09-28, "Text limits:
question 500 characters, answer 1,000" -- this overrides both the plan body's own §2.1/§2.5
numbers and approvals-contracts.md §1.4's docstring, which still say question <=500/1000 and
answer <=2000; the box is the final word per this repo's own rule that it overrides the body).
Per approvals.md §2.1 "Text length limits are form validation constants ... They don't go in
the rules module" -- these two are intentionally plain module constants, not `ham.rules`
entries; `ham.requests.forms`/the web layer should import them from here rather than
duplicating the numbers.

Every function below is `@command`-wrapped except `close_open_questions` (S3.0's own real,
non-stub function, unchanged here) and `erase_question_text` (a plain retention helper, same
shape -- see its own docstring).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from ham.authz import roles
from ham.authz.commands import CommandResult, OutboxSpec, PermissionDenied, command
from ham.platform.clock import now as clock_now

from .models import AssistanceRequest, QuestionCloseReason, RequesterChannel, RequestQuestion
from .states import RequestStatus

if TYPE_CHECKING:
    from ham.authz.context import ActorContext, RequesterContext

QUESTION_MAX_LENGTH = 500
ANSWER_MAX_LENGTH = 1000

_DIR_AD = frozenset({roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR})


# ------------------------------------------------------------------------------------------
# resource_from helpers (foundation.md §4: the matrix authorizes on a *resource*, not just a
# role -- `Scope.OWN_REQUEST` for the requester's own answer needs the `RequestQuestion` row
# itself, compared against `ctx.request_id`)
# ------------------------------------------------------------------------------------------
def _resource_request(ctx: object, *, request_id: UUID, **_: object) -> AssistanceRequest | None:
    return AssistanceRequest.objects.filter(pk=request_id).first()


def _resource_question(ctx: object, *, question_id: UUID, **_: object) -> RequestQuestion | None:
    return RequestQuestion.objects.filter(pk=question_id).first()


# ------------------------------------------------------------------------------------------
# request.question.ask
# ------------------------------------------------------------------------------------------
@command("request.question.ask", resource_from=_resource_request)
def ask_question(
    ctx: ActorContext, *, request_id: UUID, question: str, phone_answer: str = ""
) -> CommandResult:
    """`request.question.ask` (DIR, AD, PAS, BRD; approvals.md §2.5, Q-162). Allowed on any
    request that isn't closed and isn't still `NEEDS_PHONE_CHECK` (there is no verified
    contact to ask yet). `phone_answer`, for a no-email requester only in the UX, records the
    phone answer in the same step instead of leaving the question open for a callback --
    written straight onto the new row's `ONCE_FIELDS`, same shape `record_phone_answer` uses
    for an already-open question.

    Several questions may be open on one request at once (approvals.md §2.5): this never
    checks for an existing open question before creating another."""
    question_text = question.strip()
    if not question_text:
        raise ValueError("request.question.ask: question text is required")
    if len(question_text) > QUESTION_MAX_LENGTH:
        raise ValueError(f"request.question.ask: question exceeds {QUESTION_MAX_LENGTH} characters")
    phone_answer_text = phone_answer.strip()
    if phone_answer_text and len(phone_answer_text) > ANSWER_MAX_LENGTH:
        raise ValueError(f"request.question.ask: answer exceeds {ANSWER_MAX_LENGTH} characters")

    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    if request.closed_at is not None:
        raise ValueError("request.question.ask: request is closed")
    if request.status == RequestStatus.NEEDS_PHONE_CHECK.value:
        raise ValueError("request.question.ask: request needs a phone check first")

    now = clock_now()
    create_kwargs: dict[str, object] = {
        "request": request,
        "asked_by_user_id": ctx.user_id,
        "asked_at": now,
        "question": question_text,
    }
    answered_in_same_step = bool(phone_answer_text)
    if answered_in_same_step:
        create_kwargs.update(
            answer=phone_answer_text,
            answered_at=now,
            answered_via=RequesterChannel.PHONE.value,
            answer_recorded_by_user_id=ctx.user_id,
        )
    record = RequestQuestion.objects.create(**create_kwargs)

    if answered_in_same_step:
        # Two distinct consequential facts happened in one call ("asked" and "answered by
        # phone") -- same shape as `complete_intake_checks`' own extra hand-written
        # `request.duplicates_flagged` audit row, still inside the `@command` wrapper's own
        # open `transaction.atomic()`. No second outbox event: the asker is the same person
        # who just recorded the answer, so there is no one else to notify "an answer
        # arrived" (Q-162/Q-168's notification is for when someone *else* answers).
        from ham.audit.services import record as audit_record

        audit_record(
            ctx=ctx,
            action="request.question_answered",
            target_type="request",
            target_id=str(request.id),
            project_id=request.id,
            context={"question_id": str(record.id), "via": RequesterChannel.PHONE.value},
        )

    return CommandResult(
        value=record,
        audit_action="request.question_asked",
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        context={"question_id": str(record.id)},
        outbox=OutboxSpec(
            "RequesterQuestionAsked",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "question_id": str(record.id)},
        ),
    )


# ------------------------------------------------------------------------------------------
# requester.question.answer
# ------------------------------------------------------------------------------------------
@command("requester.question.answer", resource_from=_resource_question)
def answer_question(ctx: RequesterContext, *, question_id: UUID, answer: str) -> CommandResult:
    """`requester.question.answer` (own request only, one answer per question, never edited).

    Ownership is proved by `ctx.request_id`, which must itself come from a **freshly
    resolved** access-link token (`ham.requester_portal.services.resolve_token`, called by the
    view on *every* request) -- never from a session value or anything cached across requests.
    `Scope.OWN_REQUEST` (the matrix rule for this action) already compares `ctx.request_id` to
    this `RequestQuestion`'s own `request_id` before this function body ever runs, so a
    forwarded or superseded link token resolves to `None` upstream (no `RequesterContext` at
    all) long before it could reach here; the in-body check below is defense in depth against
    a caller that builds a `RequesterContext` by hand instead of through `resolve_token`, not
    the only guard."""
    answer_text = answer.strip()
    if not answer_text:
        raise ValueError("requester.question.answer: answer is required")
    if len(answer_text) > ANSWER_MAX_LENGTH:
        raise ValueError(
            f"requester.question.answer: answer exceeds {ANSWER_MAX_LENGTH} characters"
        )

    question = RequestQuestion.objects.select_for_update().get(pk=question_id)
    if question.request_id != ctx.request_id:
        raise PermissionDenied("requester.question.answer: not this request's question")
    if question.answered_at is not None:
        raise ValueError("requester.question.answer: already answered")
    if question.closed_at is not None:
        raise ValueError("requester.question.answer: question is closed")

    now = clock_now()
    question.answer = answer_text
    question.answered_at = now
    question.answered_via = RequesterChannel.SECURE_PAGE.value
    question.save(update_fields=["answer", "answered_at", "answered_via"])

    return CommandResult(
        value=None,
        audit_action="request.question_answered",
        target_type="request",
        target_id=str(question.request_id),
        project_id=question.request_id,
        context={"question_id": str(question.id), "via": RequesterChannel.SECURE_PAGE.value},
        outbox=OutboxSpec(
            "RequesterQuestionAnswered",
            aggregate_type="request",
            aggregate_id=question.request_id,
            payload={
                "request_id": str(question.request_id),
                "question_id": str(question.id),
                "via": RequesterChannel.SECURE_PAGE.value,
            },
        ),
    )


# ------------------------------------------------------------------------------------------
# request.question.record_answer ("Record an answer from a phone call")
# ------------------------------------------------------------------------------------------
@command("request.question.record_answer", resource_from=_resource_question)
def record_phone_answer(ctx: ActorContext, *, question_id: UUID, answer: str) -> CommandResult:
    """`request.question.record_answer` (DIR, AD, PAS, BRD; approvals.md §2.5 "Record an
    answer from a phone call", Q-159). Any of the four roles that may ask a question may also
    record a phone answer to an already-open one -- unlike `withdraw_question`, this is not
    narrowed to the asker/DIR/AD."""
    answer_text = answer.strip()
    if not answer_text:
        raise ValueError("request.question.record_answer: answer is required")
    if len(answer_text) > ANSWER_MAX_LENGTH:
        raise ValueError(
            f"request.question.record_answer: answer exceeds {ANSWER_MAX_LENGTH} characters"
        )

    question = RequestQuestion.objects.select_for_update().get(pk=question_id)
    if question.answered_at is not None:
        raise ValueError("request.question.record_answer: already answered")
    if question.closed_at is not None:
        raise ValueError("request.question.record_answer: question is closed")

    now = clock_now()
    question.answer = answer_text
    question.answered_at = now
    question.answered_via = RequesterChannel.PHONE.value
    question.answer_recorded_by_user_id = ctx.user_id
    question.save(
        update_fields=["answer", "answered_at", "answered_via", "answer_recorded_by_user_id"]
    )

    return CommandResult(
        value=None,
        audit_action="request.question_answered",
        target_type="request",
        target_id=str(question.request_id),
        project_id=question.request_id,
        context={"question_id": str(question.id), "via": RequesterChannel.PHONE.value},
        outbox=OutboxSpec(
            "RequesterQuestionAnswered",
            aggregate_type="request",
            aggregate_id=question.request_id,
            payload={
                "request_id": str(question.request_id),
                "question_id": str(question.id),
                "via": RequesterChannel.PHONE.value,
            },
        ),
    )


# ------------------------------------------------------------------------------------------
# request.question.withdraw
# ------------------------------------------------------------------------------------------
@command("request.question.withdraw", resource_from=_resource_question)
def withdraw_question(ctx: ActorContext, *, question_id: UUID) -> CommandResult:
    """`request.question.withdraw` (matrix: DIR, AD, PAS, BRD; finer rule the matrix can't
    express, approvals.md §2.5/§3 "the asker, Director or AD may withdraw an open question" --
    a Pastor or Board rep who isn't the asker is refused here, inside the service, even though
    the matrix itself would let any of the four roles through)."""
    question = RequestQuestion.objects.select_for_update().get(pk=question_id)
    if question.answered_at is not None or question.closed_at is not None:
        raise ValueError("request.question.withdraw: question is not open")

    is_asker = ctx.user_id is not None and ctx.user_id == question.asked_by_user_id
    is_dir_ad = bool(ctx.effective_roles & _DIR_AD)
    if not (is_asker or is_dir_ad):
        raise PermissionDenied(
            "request.question.withdraw: only the asker, Director or AD may withdraw"
        )

    now = clock_now()
    question.closed_at = now
    question.close_reason = QuestionCloseReason.WITHDRAWN.value
    question.closed_by_user_id = ctx.user_id
    question.save(update_fields=["closed_at", "close_reason", "closed_by_user_id"])

    return CommandResult(
        value=None,
        audit_action="request.question_withdrawn",
        target_type="request",
        target_id=str(question.request_id),
        project_id=question.request_id,
        context={"question_id": str(question.id)},
    )


# ------------------------------------------------------------------------------------------
# close_open_questions -- S3.0's real (non-stub) function, unchanged.
# ------------------------------------------------------------------------------------------
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


# ------------------------------------------------------------------------------------------
# Retention (Q-127/Q-145)
# ------------------------------------------------------------------------------------------
def erase_question_text(request_id: UUID) -> int:
    """7-year purge helper: blanks every `RequestQuestion.question`/`.answer` for
    ``request_id`` (Q-145). A thin, request-id-keyed wrapper around
    `RequestQuestion.objects.erase_text_for_retention` (already declared by S3.0,
    approvals-contracts.md §1.4 -- codes/dates/ids are untouched, only the two free-text
    fields are blanked). Plain function, same shape as `close_open_questions`: always called
    from *inside* `ham.requests.services.purge_expired_request`'s (S3.2) own transaction, not
    a standalone consequential action.

    **Flag for S3.2:** `purge_expired_request` does not yet call this, nor
    `Approval.objects.erase_text_for_retention`/`Reconsideration.objects.erase_text_for_
    retention` -- approvals-contracts.md §1.2/§1.3/§1.4 each say so explicitly ("not yet
    called from purge_expired_request (S3.2 wires it)"). Wire all three into the existing
    `purge_expired_request` body in `ham.requests.services`, in the same
    `transaction.atomic()` the rest of that command already runs in."""
    request = AssistanceRequest.objects.get(pk=request_id)
    return RequestQuestion.objects.erase_text_for_retention(request)
