"""S3.2: the real decisions-core write path (approvals.md §2.2-§2.4; approvals-contracts.md
§2, §4). Every function below is `@command`-wrapped except `run_held_decision_effects` (a
plain function the held-effects job calls, mirroring `services_questions.close_open_questions`
-- SYSTEM releasing already-decided, already-audited effects is not itself a new consequential
action with its own actor) and the small private helpers.

**Held effects (Q-156/Q-176, approvals-contracts.md §4).** `approve_request`, `reject_request`
and `decide_reconsideration` never emit `RequestApproved`/`RequestRejected` themselves at
decide time (except the urgent-approval alert path below) -- they store `Approval.
effective_at` and defer `run_held_decision_effects` for exactly that instant
(`ham.requests.jobs.defer_held_decision_effects`). The decision's own audit event
(`request.approved`/`.rejected`/`.reconsideration_decided`) still fires immediately, every
time, undone or not (§3.3: the audit trail is never held, only the side effects are).

**Urgent-approval alert (Q-160/Q-161, never held).** Whichever action makes
`states.becomes_urgent_approval`/`is_urgent_approval` true first emits the alert immediately,
through the normal `@command` outbox path: `UrgencyCertified(urgent_approval=True)` when the
same command also certifies urgency (`approve_request(certify_urgent=True)`,
`review_urgency(certify=True)`), or `RequestApproved(urgent_approval=True)` when the approval
alone is what tips it (urgency was already certified earlier). Either emission additionally
means the *held* copy of the same event, released later by the effects job, repeats the
`urgent_approval` flag -- S3.4/S3.5's subscribers for `RequestApproved` must treat a second
delivery for the same `request_id`/`stage` as a no-op (media close and question auto-close
already are; the leader "decision" in-app update should dedupe on `(user_id, request_id,
stage)` -- flagged in the handback, not silently assumed).
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db import transaction

from ham.audit.services import record as audit_record
from ham.authz.commands import CommandResult, OutboxSpec, command
from ham.outbox.api import emit as outbox_emit
from ham.platform.church import church_profile
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from .models import (
    Approval,
    ApprovalOutcome,
    ApprovalRoute,
    ApprovalStage,
    AssistanceRequest,
    NeedCategory,
    QuestionCloseReason,
    Reconsideration,
    RequesterChannel,
)
from .states import (
    RequestAction,
    UrgencyAction,
    check_transition,
    check_undo,
    check_urgency_transition,
    reconsideration_deadline,
)

if TYPE_CHECKING:
    from ham.authz.context import ActorContext, RequesterContext, SystemContext

# Form-level text limits (approvals.md §2.4 "Text limits"; not a rules-module business rule --
# see `ham.requests.states`'s own module docstring "Text length limits ... don't go in the
# rules module").
RECONSIDERATION_NOTE_MAX_CHARS = 1000


def _resource_request(ctx: Any, *, request_id: UUID, **_: Any) -> AssistanceRequest:
    return AssistanceRequest.objects.get(pk=request_id)


def _resource_requester_ctx(ctx: RequesterContext, *_: Any, **__: Any) -> RequesterContext:
    return ctx


def _church_today(now: dt.datetime) -> dt.date:
    zone = ZoneInfo(church_profile().time_zone)
    return now.astimezone(zone).date()


def _live_initial_approval(request_id: UUID) -> Approval:
    return Approval.objects.get(
        request_id=request_id, stage=ApprovalStage.INITIAL.value, undone_at__isnull=True
    )


# ------------------------------------------------------------------------------------------
# request.approve
# ------------------------------------------------------------------------------------------
@command("request.approve", resource_from=_resource_request)
def approve_request(
    ctx: ActorContext,
    *,
    request_id: UUID,
    route: str,
    board_decided_on: dt.date | None = None,
    certify_urgent: bool = False,
    # Additive kwargs beyond the S3.0 stub signature (submit_request's own "strictly
    # additive" precedent, ham.requests.services module docstring): Q-178, Q-169, Q-159.
    decline_urgency: bool = False,
    approval_note: str = "",
    told_by_phone: bool = False,
) -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    now = clock_now()

    if route == ApprovalRoute.BOARD.value and board_decided_on is None:
        board_decided_on = _church_today(now)  # Q-163: prefilled today
    if board_decided_on is not None and board_decided_on > _church_today(now):
        raise ValueError("request.approve: board_decided_on cannot be in the future")

    before_urgency = request.urgency_status
    decision = check_transition(
        RequestAction.APPROVE,
        request.status,
        actor_roles=ctx.effective_roles,
        is_impersonating=ctx.is_impersonating,
        route=route,
        urgency=before_urgency,
        certify_urgent=certify_urgent,
        decline_urgency=decline_urgency,
        now=now,
        closed_at=request.closed_at,
    )
    if not decision.allowed:
        raise ValueError(f"request.approve refused: {decision.refusal}")
    assert decision.target is not None and decision.urgency_after is not None
    assert ctx.user_id is not None  # a staff actor always has a user_id

    approval = Approval.objects.create(
        request=request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.APPROVED.value,
        route=route,
        decided_by_user_id=ctx.user_id,
        decided_at=now,
        effective_at=now + RULES.approvals.DECISION_UNDO_WINDOW,
        board_decided_on=board_decided_on,
        approval_note=approval_note,
        urgent_approval=decision.urgent_approval,
        requester_phoned_at=now if told_by_phone else None,
        requester_phoned_by_user_id=ctx.user_id if told_by_phone else None,
    )

    request.status = decision.target.value
    request.status_changed_at = now
    update_fields = ["status", "status_changed_at"]
    if decision.urgency_after.value != before_urgency:
        request.urgency_status = decision.urgency_after.value
        request.urgency_reviewed_at = now
        request.urgency_reviewed_by_user_id = ctx.user_id
        update_fields += ["urgency_status", "urgency_reviewed_at", "urgency_reviewed_by_user_id"]
    request.save(update_fields=update_fields)

    if certify_urgent:
        audit_record(
            ctx=ctx,
            action="request.urgency_certified",
            target_type="request",
            target_id=str(request.id),
            project_id=request.id,
            before={"urgency_status": before_urgency},
            after={"urgency_status": request.urgency_status},
        )
        outbox_emit(
            "UrgencyCertified",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "urgent_approval": True},
        )
    elif decline_urgency:
        audit_record(
            ctx=ctx,
            action="request.urgency_not_certified",
            target_type="request",
            target_id=str(request.id),
            project_id=request.id,
            before={"urgency_status": before_urgency},
            after={"urgency_status": request.urgency_status},
        )
        outbox_emit(
            "UrgencyNotCertified",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id)},
        )
    elif decision.urgent_approval:
        # Urgency was already CERTIFIED earlier; this approval alone tips it into an urgent
        # approval -- the alert fires now, immediately (never held, §4).
        outbox_emit(
            "RequestApproved",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={
                "request_id": str(request.id),
                "stage": "initial",
                "route": route,
                "urgent_approval": True,
            },
        )

    from .jobs import defer_held_decision_effects

    defer_held_decision_effects(approval.id, effective_at=approval.effective_at)

    return CommandResult(
        value=approval,
        audit_action="request.approved",
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        after={
            "route": route,
            "stage": "initial",
            "urgent_approval": decision.urgent_approval,
            "approval_id": str(approval.id),
        },
    )


# ------------------------------------------------------------------------------------------
# request.reject
# ------------------------------------------------------------------------------------------
@command("request.reject", resource_from=_resource_request)
def reject_request(
    ctx: ActorContext,
    *,
    request_id: UUID,
    route: str,
    reason_code: str,
    message: str,
    board_decided_on: dt.date | None = None,
    told_by_phone: bool = False,
) -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    now = clock_now()

    if route == ApprovalRoute.BOARD.value and board_decided_on is None:
        board_decided_on = _church_today(now)
    if board_decided_on is not None and board_decided_on > _church_today(now):
        raise ValueError("request.reject: board_decided_on cannot be in the future")

    decision = check_transition(
        RequestAction.REJECT,
        request.status,
        actor_roles=ctx.effective_roles,
        is_impersonating=ctx.is_impersonating,
        route=route,
        reason_code=reason_code,
        message=message,
        now=now,
        closed_at=request.closed_at,
    )
    if not decision.allowed:
        raise ValueError(f"request.reject refused: {decision.refusal}")
    assert decision.target is not None
    assert ctx.user_id is not None  # a staff actor always has a user_id

    zone = church_profile().time_zone
    deadline = reconsideration_deadline(now, zone)

    approval = Approval.objects.create(
        request=request,
        stage=ApprovalStage.INITIAL.value,
        outcome=ApprovalOutcome.REJECTED.value,
        route=route,
        decided_by_user_id=ctx.user_id,
        decided_at=now,
        effective_at=now + RULES.approvals.DECISION_UNDO_WINDOW,
        board_decided_on=board_decided_on,
        reason_code=reason_code,
        reason=message,
        requester_phoned_at=now if told_by_phone else None,
        requester_phoned_by_user_id=ctx.user_id if told_by_phone else None,
    )

    request.status = decision.target.value
    request.status_changed_at = now
    request.reconsideration_deadline_at = deadline
    request.save(update_fields=["status", "status_changed_at", "reconsideration_deadline_at"])

    from .jobs import defer_held_decision_effects

    defer_held_decision_effects(approval.id, effective_at=approval.effective_at)

    return CommandResult(
        value=approval,
        audit_action="request.rejected",
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        after={
            "route": route,
            "stage": "initial",
            "reason_code": reason_code,
            "urgent_approval": False,
            "approval_id": str(approval.id),
        },
    )


# ------------------------------------------------------------------------------------------
# request.urgency.review
# ------------------------------------------------------------------------------------------
@command("request.urgency.review", resource_from=_resource_request)
def review_urgency(ctx: ActorContext, *, request_id: UUID, certify: bool) -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    now = clock_now()
    action = UrgencyAction.CERTIFY_URGENCY if certify else UrgencyAction.DECLINE_URGENCY
    decision = check_urgency_transition(
        action,
        request.urgency_status,
        request.status,
        actor_roles=ctx.effective_roles,
        is_impersonating=ctx.is_impersonating,
        closed_at=request.closed_at,
    )
    if not decision.allowed:
        raise ValueError(f"request.urgency.review refused: {decision.refusal}")
    assert decision.target is not None and decision.transition is not None

    before_urgency = request.urgency_status
    request.urgency_status = decision.target.value
    request.urgency_reviewed_at = now
    request.urgency_reviewed_by_user_id = ctx.user_id
    request.save(
        update_fields=["urgency_status", "urgency_reviewed_at", "urgency_reviewed_by_user_id"]
    )

    payload: dict[str, object] = {"request_id": str(request.id)}
    if certify:
        payload["urgent_approval"] = decision.becomes_urgent_approval

    return CommandResult(
        value=request,
        audit_action=decision.transition.audit_action,
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        before={"urgency_status": before_urgency},
        after={"urgency_status": request.urgency_status},
        outbox=OutboxSpec(
            decision.transition.outbox_event,
            aggregate_type="request",
            aggregate_id=request.id,
            payload=payload,
        ),
    )


# ------------------------------------------------------------------------------------------
# requester.reconsideration.request / request.reconsideration.record_phone
# ------------------------------------------------------------------------------------------
def _create_reconsideration(
    request: AssistanceRequest,
    *,
    now,
    requested_via: str,
    recorded_by_user_id: UUID | None,
    note: str,
) -> Reconsideration:
    if len(note) > RECONSIDERATION_NOTE_MAX_CHARS:
        raise ValueError("reconsideration note exceeds the character limit")
    live_approval = _live_initial_approval(request.id)
    return Reconsideration.objects.create(
        request=request,
        requested_at=now,
        requested_via=requested_via,
        recorded_by_user_id=recorded_by_user_id,
        requester_note=note,
        route=live_approval.route,
        original_decider_user_id=live_approval.decided_by_user_id,
    )


@command("requester.reconsideration.request", resource_from=_resource_requester_ctx)
def request_reconsideration(ctx: RequesterContext, *, note: str = "") -> CommandResult:
    assert ctx.request_id is not None  # OWN_REQUEST scope already guarantees this
    request = AssistanceRequest.objects.select_for_update().get(pk=ctx.request_id)
    now = clock_now()
    has_reconsideration = Reconsideration.objects.filter(request_id=request.id).exists()
    decision = check_transition(
        RequestAction.REQUEST_RECONSIDERATION,
        request.status,
        actor_roles=ctx.roles,
        now=now,
        reconsideration_deadline_at=request.reconsideration_deadline_at,
        has_reconsideration=has_reconsideration,
        closed_at=request.closed_at,
    )
    if not decision.allowed:
        raise ValueError(f"requester.reconsideration.request refused: {decision.refusal}")
    assert decision.target is not None

    reconsideration = _create_reconsideration(
        request,
        now=now,
        requested_via=RequesterChannel.SECURE_PAGE.value,
        recorded_by_user_id=None,
        note=note,
    )
    request.status = decision.target.value
    request.status_changed_at = now
    request.save(update_fields=["status", "status_changed_at"])

    return CommandResult(
        value=reconsideration,
        audit_action=decision.transition.audit_action,  # type: ignore[union-attr]
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        after={"via": "secure_page"},
        outbox=OutboxSpec(
            "ReconsiderationRequested",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={
                "request_id": str(request.id),
                "reconsideration_id": str(reconsideration.id),
                "route": reconsideration.route,
                "via": "secure_page",
            },
        ),
    )


@command("request.reconsideration.record_phone", resource_from=_resource_request)
def record_reconsideration_by_phone(
    ctx: ActorContext, *, request_id: UUID, note: str = ""
) -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    now = clock_now()
    has_reconsideration = Reconsideration.objects.filter(request_id=request.id).exists()
    decision = check_transition(
        RequestAction.REQUEST_RECONSIDERATION,
        request.status,
        actor_roles=ctx.effective_roles,
        is_impersonating=ctx.is_impersonating,
        now=now,
        reconsideration_deadline_at=request.reconsideration_deadline_at,
        has_reconsideration=has_reconsideration,
        closed_at=request.closed_at,
    )
    if not decision.allowed:
        raise ValueError(f"request.reconsideration.record_phone refused: {decision.refusal}")
    assert decision.target is not None

    reconsideration = _create_reconsideration(
        request,
        now=now,
        requested_via=RequesterChannel.PHONE.value,
        recorded_by_user_id=ctx.user_id,
        note=note,
    )
    request.status = decision.target.value
    request.status_changed_at = now
    request.save(update_fields=["status", "status_changed_at"])

    return CommandResult(
        value=reconsideration,
        audit_action=decision.transition.audit_action,  # type: ignore[union-attr]
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        after={"via": "phone"},
        outbox=OutboxSpec(
            "ReconsiderationRequested",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={
                "request_id": str(request.id),
                "reconsideration_id": str(reconsideration.id),
                "route": reconsideration.route,
                "via": "phone",
            },
        ),
    )


# ------------------------------------------------------------------------------------------
# request.reconsideration.decide
# ------------------------------------------------------------------------------------------
def _is_active_pastor(user_id: UUID | None) -> bool:
    from ham.authz import roles
    from ham.identity.services import user_holds_global_role

    return user_holds_global_role(user_id, roles.PASTOR)


@command("request.reconsideration.decide", resource_from=_resource_request)
def decide_reconsideration(
    ctx: ActorContext,
    *,
    request_id: UUID,
    approve: bool,
    reason: str,
    reason_code: str = "",
    take_over: bool = False,
) -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    now = clock_now()
    recon = Reconsideration.objects.get(request_id=request.id)

    original_active = True
    if recon.route == ApprovalRoute.PASTORAL.value:
        original_active = _is_active_pastor(recon.original_decider_user_id)

    action = RequestAction.RECONSIDER_APPROVE if approve else RequestAction.RECONSIDER_REJECT
    decision = check_transition(
        action,
        request.status,
        actor_roles=ctx.effective_roles,
        is_impersonating=ctx.is_impersonating,
        route=recon.route,
        reason_code=reason_code,
        message=reason,
        urgency=request.urgency_status,
        actor_id=str(ctx.user_id) if ctx.user_id else None,
        original_decider_id=str(recon.original_decider_user_id),
        original_decider_is_active_pastor=original_active,
        take_over=take_over,
        decider_unavailable_confirmed=take_over,
        now=now,
        closed_at=request.closed_at,
    )
    if not decision.allowed:
        raise ValueError(f"request.reconsideration.decide refused: {decision.refusal}")
    assert decision.target is not None
    assert ctx.user_id is not None  # a staff actor always has a user_id

    outcome = ApprovalOutcome.APPROVED.value if approve else ApprovalOutcome.REJECTED.value
    approval = Approval.objects.create(
        request=request,
        stage=ApprovalStage.RECONSIDERATION.value,
        outcome=outcome,
        route=recon.route,
        decided_by_user_id=ctx.user_id,
        decided_at=now,
        effective_at=now + RULES.approvals.DECISION_UNDO_WINDOW,
        reason_code=reason_code if not approve else "",
        reason=reason,
        urgent_approval=decision.urgent_approval,
        took_over_from_user_id=decision.took_over_from,
        unavailable_confirmed=bool(decision.took_over_from),
    )

    request.status = decision.target.value
    request.status_changed_at = now
    update_fields = ["status", "status_changed_at"]
    if decision.closes_request:
        request.closed_at = now
        request.closed_by_user_id = ctx.user_id
        request.requester_access_ends_at = now + RULES.requester_access.REQUESTER_ACCESS_AFTER_CLOSE
        update_fields += ["closed_at", "closed_by_user_id", "requester_access_ends_at"]
    request.save(update_fields=update_fields)

    if decision.urgent_approval:
        outbox_emit(
            "RequestApproved",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={
                "request_id": str(request.id),
                "stage": "reconsideration",
                "route": recon.route,
                "urgent_approval": True,
            },
        )

    from .jobs import defer_held_decision_effects

    defer_held_decision_effects(approval.id, effective_at=approval.effective_at)

    return CommandResult(
        value=approval,
        audit_action="request.reconsideration_decided",
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        after={
            "outcome": outcome,
            "route": recon.route,
            "took_over": bool(decision.took_over_from),
            "approval_id": str(approval.id),
        },
    )


# ------------------------------------------------------------------------------------------
# system.request.finalize_rejection (+ hourly job in .jobs)
# ------------------------------------------------------------------------------------------
@command("system.request.finalize_rejection")
def finalize_rejection(ctx: SystemContext, *, request_id: UUID) -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    now = clock_now()
    has_reconsideration = Reconsideration.objects.filter(request_id=request.id).exists()
    decision = check_transition(
        RequestAction.FINALIZE_REJECTION,
        request.status,
        actor_roles=ctx.roles,
        now=now,
        reconsideration_deadline_at=request.reconsideration_deadline_at,
        has_reconsideration=has_reconsideration,
        closed_at=request.closed_at,
    )
    if not decision.allowed:
        raise ValueError(f"finalize_rejection refused: {decision.refusal}")
    assert decision.target is not None and decision.transition is not None
    assert decision.transition.outbox_event is not None

    request.status = decision.target.value
    request.closed_at = now
    request.requester_access_ends_at = now + RULES.requester_access.REQUESTER_ACCESS_AFTER_CLOSE
    request.status_changed_at = now
    request.save(
        update_fields=["status", "closed_at", "requester_access_ends_at", "status_changed_at"]
    )

    from .services_questions import close_open_questions

    close_open_questions(request.id, reason=QuestionCloseReason.REQUEST_CLOSED.value)

    return CommandResult(
        value=request,
        audit_action=decision.transition.audit_action,
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        after={"status": request.status},
        outbox=OutboxSpec(
            decision.transition.outbox_event,
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id)},
        ),
    )


# ------------------------------------------------------------------------------------------
# request.decision.record_phoned (Q-159 "Told them by phone", the Director/AD follow-up card)
# ------------------------------------------------------------------------------------------
@command("request.decision.record_phoned", resource_from=_resource_request)
def record_decision_phoned(ctx: ActorContext, *, request_id: UUID) -> CommandResult:
    approval = Approval.objects.select_for_update().get(
        request_id=request_id, stage=ApprovalStage.INITIAL.value, undone_at__isnull=True
    )
    if approval.requester_phoned_at is not None:
        raise ValueError("request.decision.record_phoned: already recorded")
    now = clock_now()
    approval.requester_phoned_at = now
    approval.requester_phoned_by_user_id = ctx.user_id
    approval.save(update_fields=["requester_phoned_at", "requester_phoned_by_user_id"])
    return CommandResult(
        value=approval,
        audit_action="request.decision_phoned",
        target_type="request",
        target_id=str(request_id),
        project_id=request_id,
        after={"approval_id": str(approval.id)},
    )


# ------------------------------------------------------------------------------------------
# request.category.change (Q-109: DIR/AD only, not blocked while impersonating)
# ------------------------------------------------------------------------------------------
@command("request.category.change", resource_from=_resource_request)
def change_category(ctx: ActorContext, *, request_id: UUID, need_category: str) -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    if request.closed_at is not None:
        raise ValueError("request.category.change: request is closed")
    try:
        NeedCategory(need_category)
    except ValueError:
        raise ValueError("request.category.change: unknown category") from None
    before = request.need_category
    if before == need_category:
        raise ValueError("request.category.change: category unchanged")
    request.need_category = need_category
    request.save(update_fields=["need_category"])
    return CommandResult(
        value=request,
        audit_action="request.category_changed",
        target_type="request",
        target_id=str(request_id),
        project_id=request_id,
        before={"need_category": before},
        after={"need_category": need_category},
        outbox=OutboxSpec(
            "RequestCategoryChanged",
            aggregate_type="request",
            aggregate_id=request_id,
            payload={"request_id": str(request_id), "need_category": need_category},
        ),
    )


# ------------------------------------------------------------------------------------------
# request.decision.undo (Q-156/Q-176)
# ------------------------------------------------------------------------------------------
def _decision_action_for_approval(approval: Approval) -> RequestAction:
    if approval.stage == ApprovalStage.RECONSIDERATION.value:
        return (
            RequestAction.RECONSIDER_APPROVE
            if approval.outcome == ApprovalOutcome.APPROVED.value
            else RequestAction.RECONSIDER_REJECT
        )
    return (
        RequestAction.APPROVE
        if approval.outcome == ApprovalOutcome.APPROVED.value
        else RequestAction.REJECT
    )


@command("request.decision.undo")
def undo_decision(ctx: ActorContext, *, approval_id: UUID) -> CommandResult:
    approval = Approval.objects.select_for_update().get(pk=approval_id)
    request = AssistanceRequest.objects.select_for_update().get(pk=approval.request_id)
    now = clock_now()
    kind = _decision_action_for_approval(approval)

    # PRD-GAP: `Approval` stores no "urgency before this decision" field, so a decision that
    # bundled a certify/decline (approve_request(certify_urgent=True/decline_urgency=True))
    # cannot have its urgency choice reconstructed and restored here -- undo restores the
    # REQUEST status only; the urgency review this decision may have bundled is left as-is.
    # Flagged in the S3.2 handback for the orchestrator, not silently assumed.
    outcome = check_undo(
        kind,
        actor_id=str(ctx.user_id) if ctx.user_id else None,
        decided_by_id=str(approval.decided_by_user_id),
        decided_at=approval.decided_at,
        now=now,
        undone_at=approval.undone_at,
        current_status=request.status,
        current_urgency=request.urgency_status,
        is_impersonating=ctx.is_impersonating,
    )
    if not outcome.allowed:
        raise ValueError(f"request.decision.undo refused: {outcome.refusal}")
    assert outcome.restore_status is not None

    approval.undone_at = now
    approval.undone_by_user_id = ctx.user_id
    approval.save(update_fields=["undone_at", "undone_by_user_id"])

    request.status = outcome.restore_status.value
    request.status_changed_at = now
    update_fields = ["status", "status_changed_at"]
    if outcome.reopens_request:
        request.closed_at = None
        request.closed_by_user_id = None
        request.requester_access_ends_at = None
        update_fields += ["closed_at", "closed_by_user_id", "requester_access_ends_at"]
    if outcome.clears_reconsideration_deadline:
        request.reconsideration_deadline_at = None
        update_fields.append("reconsideration_deadline_at")
    request.save(update_fields=update_fields)

    return CommandResult(
        value=approval,
        audit_action="request.decision_undone",
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        after={"approval_id": str(approval.id), "stage": approval.stage},
        outbox=OutboxSpec(
            "RequestDecisionUndone",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={
                "request_id": str(request.id),
                "approval_id": str(approval.id),
                "stage": approval.stage,
            },
        ),
    )


# ------------------------------------------------------------------------------------------
# Held effects (approvals-contracts.md §4). Plain function, SYSTEM-triggered from
# `ham.requests.jobs`, not `@command`-wrapped -- releasing an already-decided, already-audited
# decision's side effects is not itself a new human consequential action (same reasoning as
# `services_questions.close_open_questions`'s own docstring).
# ------------------------------------------------------------------------------------------
def run_held_decision_effects(approval_id: UUID) -> None:
    with transaction.atomic():
        approval = Approval.objects.select_for_update().get(pk=approval_id)
        if approval.effects_ran_at is not None:
            return  # idempotent: a retried/duplicate job invocation is a no-op
        now = clock_now()
        if approval.undone_at is not None:
            # Undone before the window closed: none of the held effects ever run, but the
            # marker is still set so a retried invocation is provably a no-op either way.
            approval.effects_ran_at = now
            approval.save(update_fields=["effects_ran_at"])
            return

        event_type = (
            "RequestApproved"
            if approval.outcome == ApprovalOutcome.APPROVED.value
            else "RequestRejected"
        )
        payload: dict[str, object] = {
            "request_id": str(approval.request_id),
            "stage": approval.stage,
            "route": approval.route,
        }
        if approval.outcome == ApprovalOutcome.APPROVED.value:
            payload["urgent_approval"] = approval.urgent_approval
        else:
            payload["reason_code"] = approval.reason_code
            payload["final"] = approval.stage == ApprovalStage.RECONSIDERATION.value
        outbox_emit(
            event_type,
            aggregate_type="request",
            aggregate_id=approval.request_id,
            payload=payload,
        )

        from .services_questions import close_open_questions

        close_open_questions(approval.request_id, reason=QuestionCloseReason.REQUEST_CLOSED.value)

        approval.effects_ran_at = now
        approval.save(update_fields=["effects_ran_at"])
