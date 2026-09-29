"""S3.0 seam (approvals.md §8.1; approvals-contracts.md §2): the exact signatures S3.2 (the
real decisions-core implementation) commits to, so S3.3-S3.7 can code against them while S3.2
runs in a parallel worktree. Every function below raises ``NotImplementedError`` today; S3.2
fills in the body (wrapped in ``@command("...")``, per ``ham.authz.commands``'s one write
path) without changing this signature, or flags a coordination note here if it must.

Nothing here is authorized/audited yet -- these are plain functions, not yet
``@command``-wrapped (``tests/audit/test_command_registry.py``'s ``PLACEHOLDER_ACTIONS`` lists
the matching ``ham.authz.matrix`` action codes as declared-but-unwired for this reason).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from ham.authz.context import ActorContext, RequesterContext, SystemContext

    from .models import Approval, AssistanceRequest


def approve_request(
    ctx: ActorContext,
    *,
    request_id: UUID,
    route: str,
    board_decided_on=None,
    certify_urgent: bool = False,
) -> Approval:
    """`request.approve` (PAS pastoral route, BRD board route; Q-048/Q-153/Q-164).
    `certify_urgent=True` (pastor only) also writes `request.urgency_certified` and emits
    `UrgencyCertified` inside the same atomic block (approvals.md §2.2 "one command", the
    `complete_intake_checks` precedent)."""
    raise NotImplementedError("S3.2: ham.requests.services_decisions.approve_request")


def reject_request(
    ctx: ActorContext,
    *,
    request_id: UUID,
    route: str,
    reason_code: str,
    message: str,
    board_decided_on=None,
) -> Approval:
    """`request.reject` (Q-154: `reason_code` one of `RejectionReason`, `message` the kind,
    editable, pre-filled text the requester reads -- required, never audited/logged)."""
    raise NotImplementedError("S3.2: ham.requests.services_decisions.reject_request")


def review_urgency(ctx: ActorContext, *, request_id: UUID, certify: bool) -> AssistanceRequest:
    """`request.urgency.review` (PAS only; Q-160). `certify=True` -> CERTIFIED,
    `certify=False` -> NOT_CERTIFIED (`ham.requests.states`'s urgency sub-machine, S3.1)."""
    raise NotImplementedError("S3.2: ham.requests.services_decisions.review_urgency")


def request_reconsideration(ctx: RequesterContext, *, note: str = "") -> None:
    """`requester.reconsideration.request` (Q-155/Q-158; own request only, before the
    deadline, at most once -- `Reconsideration` row's own UNIQUE(request_id))."""
    raise NotImplementedError("S3.2: ham.requests.services_decisions.request_reconsideration")


def record_reconsideration_by_phone(ctx: ActorContext, *, request_id: UUID, note: str = "") -> None:
    """`request.reconsideration.record_phone` (DIR, AD only; Q-159, no-email requesters)."""
    raise NotImplementedError(
        "S3.2: ham.requests.services_decisions.record_reconsideration_by_phone"
    )


def decide_reconsideration(
    ctx: ActorContext,
    *,
    request_id: UUID,
    approve: bool,
    reason: str,
    reason_code: str = "",
    take_over: bool = False,
) -> Approval:
    """`request.reconsideration.decide` (Q-157: `take_over=True` records
    `Approval.took_over_from_user_id`/`.unavailable_confirmed`; routing -- Board route: any
    BRD, pastoral route: the original pastor or an explicit takeover -- is
    `ham.requests.states.may_decide_reconsideration`, S3.1)."""
    raise NotImplementedError("S3.2: ham.requests.services_decisions.decide_reconsideration")


def finalize_rejection(ctx: SystemContext, *, request_id: UUID) -> None:
    """`system.request.finalize_rejection` (Q-155; the hourly job past
    `AssistanceRequest.reconsideration_deadline_at` with no `Reconsideration` filed)."""
    raise NotImplementedError("S3.2: ham.requests.services_decisions.finalize_rejection")


def record_decision_phoned(ctx: ActorContext, *, request_id: UUID) -> None:
    """`request.decision.record_phoned` (DIR, AD only; Q-159 "Told them by phone" --
    equivalently the decider's own "I've already told them by phone" tick at decision time,
    which sets `Approval.requester_phoned_at`/`.requester_phoned_by_user_id` directly inside
    `approve_request`/`reject_request` instead of calling this separately)."""
    raise NotImplementedError("S3.2: ham.requests.services_decisions.record_decision_phoned")


def change_category(ctx: ActorContext, *, request_id: UUID, need_category: str) -> None:
    """`request.category.change` (owner box: DIR, AD only -- narrower than approvals.md
    §2.6/§3's own table, Q-109; NOT blocked while impersonating, Q-172)."""
    raise NotImplementedError("S3.2: ham.requests.services_decisions.change_category")


def undo_decision(ctx: ActorContext, *, approval_id: UUID) -> Approval:
    """`request.decision.undo` (Q-156/Q-176). Sets `Approval.undone_at`/`.undone_by_user_id`
    (`AppendOnlyOnceMixin`'s `ONCE_FIELDS`, settable once) -- never deletes or edits any other
    field on the record. Only the person who recorded the decision may undo, and only within
    `RULES.approvals.DECISION_UNDO_WINDOW` of `decided_at` (i.e. before `effective_at`); both
    are service-layer checks the matrix can't express, same shape as reconsideration routing.
    See `docs/architecture/approvals-contracts.md` §4 "Held effects" for exactly what
    cancelling on undo means for the requester email, media batch close, question withdrawal
    and leader "decision" update -- all held, none of them run if undo lands before
    `effective_at`; the urgent-approval alert is never held and is NOT undone by this call
    (Q-176: it gets an in-app "urgent approval was undone" follow-up instead)."""
    raise NotImplementedError("S3.2: ham.requests.services_decisions.undo_decision")
