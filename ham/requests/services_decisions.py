"""S3.2: the real decisions-core write path (approvals.md §2.2-§2.4; approvals-contracts.md
§2, §4). Every function below is `@command`-wrapped except `run_held_decision_effects` (a
plain function the held-effects job calls, mirroring `services_questions.close_open_questions`
-- SYSTEM releasing already-decided, already-audited effects is not itself a new consequential
action with its own actor) and the small private helpers.

**Held effects (Q-156/Q-176, approvals-contracts.md §4).** `approve_request`, `reject_request`
and `decide_reconsideration` never emit `RequestApproved`/`RequestRejected` themselves at
decide time -- they store `Approval.effective_at` and defer `run_held_decision_effects` for
exactly that instant (`ham.requests.jobs.defer_held_decision_effects`). The decision's own
audit event (`request.approved`/`.rejected`/`.reconsideration_decided`) still fires
immediately, every time, undone or not (§3.3: the audit trail is never held, only the side
effects are). `RequestApproved` is therefore **never** emitted at decide time, only by the
held-effects job -- see the next paragraph for the dedicated immediate event.

**Urgent-approval alert (Q-160/Q-161, never held; coordinator fix round -- was briefly a
second, immediate delivery of `RequestApproved` itself, which double-delivered that event;
fixed to a distinct event type).** Whichever action first makes
`states.becomes_urgent_approval`/`is_urgent_approval` true emits `RequestUrgentApproval
{request_id, approval_id}` immediately, through the normal `@command` outbox path, in addition
to (never instead of) whatever event that same action already emits for the urgency review
itself (`UrgencyCertified`/`UrgencyNotCertified`, also always immediate). `RequestApproved`
stays exclusively the held copy at `effective_at` -- exactly one delivery per decision, ever.

**Undo restores urgency too (Q-176/Q-178, coordinator fix round).** `Approval.prior_urgency`/
`.accompanying_urgency` (set together, only when the same command also reviewed urgency --
`approve_request(certify_urgent=True/decline_urgency=True)`) let `undo_decision` pass both to
`states.check_undo`, which restores the pre-decision urgency alongside the pre-decision status.
A *standalone* urgency review (`review_urgency`, not bundled with an approval) gets its own
append-only, undoable `UrgencyReview` record (Q-176: "urgency certification and 'Not urgent'"
are themselves undoable within the same window) -- `undo_decision` now takes either
`approval_id` or `review_id` (exactly one).
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
    Requester,
    RequesterChannel,
    UrgencyReview,
)
from .presentation import APPROVAL_NOTE_MAX_CHARS, DECLINE_MESSAGE_MAX_CHARS
from .queries import decision_undo_open
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


def _has_email(request_id: UUID) -> bool:
    return Requester.objects.filter(request_id=request_id).exclude(email=None).exists()


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
    if len(approval_note) > APPROVAL_NOTE_MAX_CHARS:
        raise ValueError(
            f"request.approve: approval_note exceeds {APPROVAL_NOTE_MAX_CHARS} characters"
        )
    if told_by_phone and _has_email(request_id):
        # PRD guardian minor 4 / Q-159: "told by phone" is only meaningful for a no-email
        # requester -- an email requester is always told by email once the window closes.
        raise ValueError("request.approve: told_by_phone is not allowed for an email requester")

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

    # Coordinator fix round (Q-176/Q-178): record what urgency was, and which review action
    # this decision bundled, so `undo_decision` can restore both later -- `states.check_undo`
    # already accepted these two facts; only the persistence was missing.
    accompanying_urgency = None
    if certify_urgent:
        accompanying_urgency = UrgencyAction.CERTIFY_URGENCY.value
    elif decline_urgency:
        accompanying_urgency = UrgencyAction.DECLINE_URGENCY.value
    prior_urgency = before_urgency if accompanying_urgency is not None else None

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
        prior_urgency=prior_urgency,
        accompanying_urgency=accompanying_urgency,
        requester_phoned_at=now if told_by_phone else None,
        requester_phoned_by_user_id=ctx.user_id if told_by_phone else None,
        # Fix 3A / security M2: known at creation time (== `decision.urgent_approval` below),
        # so it's set once, at insert, like every other decision fact -- no `ONCE_FIELDS`
        # update needed.
        urgent_approval_emitted=decision.urgent_approval,
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
            payload={"request_id": str(request.id)},
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

    if decision.urgent_approval:
        # Coordinator fix round (gap 3): a DISTINCT immediate event, never `RequestApproved`
        # itself -- that stays exclusively the held copy at `effective_at` (§4). Fires here
        # whichever way this decision produced the urgent approval: bundled with
        # `certify_urgent` above, or an approval alone tipping an already-certified request.
        outbox_emit(
            "RequestUrgentApproval",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "approval_id": str(approval.id)},
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
    if len(message) > DECLINE_MESSAGE_MAX_CHARS:
        raise ValueError(f"request.reject: message exceeds {DECLINE_MESSAGE_MAX_CHARS} characters")
    if told_by_phone and _has_email(request_id):
        raise ValueError("request.reject: told_by_phone is not allowed for an email requester")

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

    if request.urgent_requested:
        # UX M9: declining an urgent request clears the other pastors' now-stale "needs a
        # pastor" banner for it -- the request left the awaiting queue by a different door
        # than certify/decline urgency, but the banner is just as stale.
        from .notifications import clear_pastor_urgent_banner_on_decline

        clear_pastor_urgent_banner_on_decline(request.id)

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
    # Fix 3A / security M2 (owner box Q-176: "while a decision can still be undone nothing
    # else may change the request ... except urgency certification" -- but that carve-out is
    # for a *different, live* decision being pending, e.g. certifying while an approval is
    # still in its own separate undo window is fine; a *second* review of urgency itself,
    # while THIS request's own live approval/urgency-review is still undoable, is refused so
    # the pastor card and the follow-up bookkeeping never have two pending reviews to reason
    # about at once).
    if decision_undo_open(request_id, now):
        raise ValueError("request.urgency.review refused: decision_undo_window_open")
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
    assert ctx.user_id is not None  # a staff actor always has a user_id

    before_urgency = request.urgency_status
    request.urgency_status = decision.target.value
    request.urgency_reviewed_at = now
    request.urgency_reviewed_by_user_id = ctx.user_id
    request.save(
        update_fields=["urgency_status", "urgency_reviewed_at", "urgency_reviewed_by_user_id"]
    )

    # Coordinator fix round (gap 2, Q-176): a standalone urgency review is itself undoable --
    # give it its own append-only record, the same "decided_at + DECISION_UNDO_WINDOW"
    # `effective_at` shape as `Approval` (no held effects hang off it; this is only so the
    # undo window has something to check against).
    UrgencyReview.objects.create(
        request=request,
        action=action.value,
        prior_urgency=before_urgency,
        decided_by_user_id=ctx.user_id,
        decided_at=now,
        effective_at=now + RULES.approvals.DECISION_UNDO_WINDOW,
        # Fix 3A / security M2: known at creation time -- the stored fact the Q-176 "undone"
        # follow-up keys on, instead of re-deriving from the request's live status at undo
        # time.
        urgent_approval_emitted=bool(certify and decision.becomes_urgent_approval),
    )

    if certify and decision.becomes_urgent_approval:
        # Coordinator fix round (gap 3): the dedicated immediate alert event -- hand-emitted
        # (the `complete_intake_checks`/`approve_request` precedent: `@command`'s wrapper
        # already has a `transaction.atomic()` open around this function body, so a second
        # outbox event here still lands atomically with the primary one below) -- referencing
        # the live `Approval` this urgency certification just made urgent (the request is
        # already APPROVED for `becomes_urgent_approval` to be true at all).
        live_approval = (
            Approval.objects.filter(request_id=request.id, undone_at__isnull=True)
            .order_by("-decided_at")
            .first()
        )
        assert live_approval is not None
        outbox_emit(
            "RequestUrgentApproval",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "approval_id": str(live_approval.id)},
        )

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
            payload={"request_id": str(request.id)},
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
        # Security M1/Q-181: while the decline that started this window can still be undone,
        # a reconsideration must not be requested -- `states.check_transition` already refuses
        # `DECISION_UNDO_WINDOW_OPEN`; the fact just wasn't being passed.
        decision_undo_open=decision_undo_open(request.id, now),
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
        # Security M1/Q-181: see `request_reconsideration`'s matching comment.
        decision_undo_open=decision_undo_open(request.id, now),
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
    # Fix 3A / UX B1 / Q-182: the same "I've already told them by phone" tick the initial
    # decision carries, for no-email requests only (PRD guardian minor 4).
    told_by_phone: bool = False,
    # PRD guardian B2 / Q-180: required by the Board route, same as `approve_request`/
    # `reject_request` -- the DB `approval_board_decided_on_required_for_board_route`
    # constraint otherwise rejects the row with an `IntegrityError`, not a clean refusal.
    board_decided_on: dt.date | None = None,
) -> CommandResult:
    if len(reason) > DECLINE_MESSAGE_MAX_CHARS:
        raise ValueError(
            f"request.reconsideration.decide: reason exceeds {DECLINE_MESSAGE_MAX_CHARS} characters"
        )
    if told_by_phone and _has_email(request_id):
        raise ValueError(
            "request.reconsideration.decide: told_by_phone is not allowed for an email requester"
        )
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    now = clock_now()
    recon = Reconsideration.objects.get(request_id=request.id)

    if recon.route == ApprovalRoute.BOARD.value:
        if board_decided_on is None:
            board_decided_on = _church_today(now)  # Q-180: prefilled today
        if board_decided_on > _church_today(now):
            raise ValueError(
                "request.reconsideration.decide: board_decided_on cannot be in the future"
            )
    else:
        board_decided_on = None

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
        board_decided_on=board_decided_on,
        reason_code=reason_code if not approve else "",
        reason=reason,
        urgent_approval=decision.urgent_approval,
        took_over_from_user_id=decision.took_over_from,
        # Q-183: the tick is recorded only for "unavailable_ticked"; "role_ended" never
        # carries one, even though it's also a take-over.
        unavailable_confirmed=decision.took_over_basis == "unavailable_ticked",
        took_over_basis=decision.took_over_basis or "",
        urgent_approval_emitted=decision.urgent_approval,
        requester_phoned_at=now if told_by_phone else None,
        requester_phoned_by_user_id=ctx.user_id if told_by_phone else None,
    )

    request.status = decision.target.value
    request.status_changed_at = now
    update_fields = ["status", "status_changed_at"]
    # Security L2: `closed_at` is set at decide time, not at `effective_at`, deliberately --
    # the SAME pattern `request.status` itself already follows for every other decision in
    # this module (set immediately; only the outbox events/side effects are held, contracts.md
    # §4). `_undo_approval`'s `outcome.reopens_request` clears it again on undo, exactly like
    # it restores `status`. The requester's OWN page never reads this raw field for "is it
    # closed" -- `ham.requester_portal.page._effective_status_and_closed` computes its own
    # held view from `Approval.effective_at`, and media/link-expiry clocks key off the
    # `Approval`/held-effects timeline (`run_held_decision_effects`), not off `closed_at`
    # directly. Moving this to `effective_at` would need its own deferred job and would only
    # duplicate that already-correct held-effects mechanism.
    if decision.closes_request:
        request.closed_at = now
        request.closed_by_user_id = ctx.user_id
        request.requester_access_ends_at = now + RULES.requester_access.REQUESTER_ACCESS_AFTER_CLOSE
        update_fields += ["closed_at", "closed_by_user_id", "requester_access_ends_at"]
    request.save(update_fields=update_fields)

    if decision.urgent_approval:
        # Coordinator fix round (gap 3): the dedicated immediate event, never `RequestApproved`
        # itself (see `approve_request`'s matching comment).
        outbox_emit(
            "RequestUrgentApproval",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "approval_id": str(approval.id)},
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
            # Q-183: the audit `after` carries both facts, not just whether a take-over
            # happened.
            "took_over": bool(decision.took_over_from),
            "take_over_basis": decision.took_over_basis or "",
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

    # PRD guardian minor 2 / Q-162: a decision-driven auto-withdrawal, distinct from a genuine
    # `cancel_request` close.
    close_open_questions(request.id, reason=QuestionCloseReason.REQUEST_DECIDED.value)

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
    # UX B1 / PRD guardian M5 / Q-182: key on the latest LIVE decision at either stage
    # (initial or reconsideration) -- not only the initial approval, which left a no-email
    # requester's reconsideration outcome unreachable and, worse, showed the *first*
    # decision's script even after a reconsideration reversed it.
    approval = (
        Approval.objects.select_for_update()
        .filter(request_id=request_id, undone_at__isnull=True)
        .order_by("-decided_at")
        .first()
    )
    if approval is None:
        raise ValueError("request.decision.record_phoned: no live decision")
    if _has_email(request_id):
        raise ValueError("request.decision.record_phoned: this requester has email")
    now = clock_now()
    # Security M3 / UX B2 / Q-181: refuse while the decision can still be undone -- the
    # requester must not be told anything until the held effects are released.
    if approval.effective_at > now:
        raise ValueError("request.decision.record_phoned: decision can still be undone")
    if approval.requester_phoned_at is not None:
        raise ValueError("request.decision.record_phoned: already recorded")
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


def _undo_approval(ctx: ActorContext, approval_id: UUID) -> CommandResult:
    approval = Approval.objects.select_for_update().get(pk=approval_id)
    request = AssistanceRequest.objects.select_for_update().get(pk=approval.request_id)
    now = clock_now()
    # Security L1: the held effects have already run (the requester's email may already be
    # on its way) -- undo is refused from this instant on, even if a clock skew or a
    # misfired early job run left a sliver of time where `decision_is_undoable` would
    # otherwise still say yes.
    if approval.effects_ran_at is not None:
        raise ValueError("request.decision.undo refused: undo_window_passed")
    kind = _decision_action_for_approval(approval)

    # Coordinator fix round (gap 1, Q-176/Q-178): `Approval.prior_urgency`/
    # `.accompanying_urgency` (set only when this decision also bundled a certify/decline)
    # let `check_undo` restore urgency alongside status, not status alone.
    accompanying_urgency = (
        UrgencyAction(approval.accompanying_urgency) if approval.accompanying_urgency else None
    )
    outcome = check_undo(
        kind,
        actor_id=str(ctx.user_id) if ctx.user_id else None,
        decided_by_id=str(approval.decided_by_user_id),
        decided_at=approval.decided_at,
        now=now,
        undone_at=approval.undone_at,
        current_status=request.status,
        current_urgency=request.urgency_status,
        prior_urgency=approval.prior_urgency,
        accompanying_urgency=accompanying_urgency,
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
    if outcome.restore_urgency is not None:
        request.urgency_status = outcome.restore_urgency.value
        request.urgency_reviewed_at = None
        request.urgency_reviewed_by_user_id = None
        update_fields += ["urgency_status", "urgency_reviewed_at", "urgency_reviewed_by_user_id"]
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


def _undo_urgency_review(ctx: ActorContext, review_id: UUID) -> CommandResult:
    """Coordinator fix round (gap 2, Q-176): undo a *standalone* urgency review (not bundled
    with an approval -- see `_undo_approval` above for that case)."""
    review = UrgencyReview.objects.select_for_update().get(pk=review_id)
    request = AssistanceRequest.objects.select_for_update().get(pk=review.request_id)
    now = clock_now()
    action = UrgencyAction(review.action)

    outcome = check_undo(
        action,
        actor_id=str(ctx.user_id) if ctx.user_id else None,
        decided_by_id=str(review.decided_by_user_id),
        decided_at=review.decided_at,
        now=now,
        undone_at=review.undone_at,
        current_status=request.status,
        current_urgency=request.urgency_status,
        prior_urgency=review.prior_urgency,
        is_impersonating=ctx.is_impersonating,
    )
    if not outcome.allowed:
        raise ValueError(f"request.decision.undo refused: {outcome.refusal}")
    assert outcome.restore_urgency is not None

    review.undone_at = now
    review.undone_by_user_id = ctx.user_id
    review.save(update_fields=["undone_at", "undone_by_user_id"])

    request.urgency_status = outcome.restore_urgency.value
    request.urgency_reviewed_at = None
    request.urgency_reviewed_by_user_id = None
    request.save(
        update_fields=["urgency_status", "urgency_reviewed_at", "urgency_reviewed_by_user_id"]
    )

    return CommandResult(
        value=review,
        audit_action="request.urgency_review_undone",
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        after={"review_id": str(review.id)},
        # Coordinator fix round: the follow-up event S3.5 turns into the Q-176 in-app "urgent
        # approval was undone" notice when this review's own certification had produced one
        # (S3.5 checks by looking up the review and the request's decision history by id --
        # ids/codes only in the payload itself, per the outbox PII rule).
        outbox=OutboxSpec(
            "RequestUrgencyReviewUndone",
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "review_id": str(review.id)},
        ),
    )


@command("request.decision.undo")
def undo_decision(
    ctx: ActorContext, *, approval_id: UUID | None = None, review_id: UUID | None = None
) -> CommandResult:
    """Undo a decision (Q-156/Q-176). Exactly one of `approval_id` (an `Approval` -- approve/
    reject/reconsider) or `review_id` (an `UrgencyReview` -- a standalone certify/decline) is
    required; the two record kinds carry their own undo bookkeeping (see `_undo_approval`/
    `_undo_urgency_review`)."""
    if (approval_id is None) == (review_id is None):
        raise ValueError(
            "request.decision.undo: exactly one of approval_id or review_id is required"
        )
    if approval_id is not None:
        return _undo_approval(ctx, approval_id)
    assert review_id is not None
    return _undo_urgency_review(ctx, review_id)


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
        if now < approval.effective_at:
            # Security L1: a job run before the window has actually closed (a misfired retry,
            # a clock skew) must never release the held effects early -- re-defer to the
            # correct instant instead of running now.
            from .jobs import defer_held_decision_effects

            defer_held_decision_effects(approval.id, effective_at=approval.effective_at)
            return
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

        close_open_questions(approval.request_id, reason=QuestionCloseReason.REQUEST_DECIDED.value)

        approval.effects_ran_at = now
        approval.save(update_fields=["effects_ran_at"])
