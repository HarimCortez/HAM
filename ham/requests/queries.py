"""Leadership list/detail queries (intake.md §7 `/requests`, `/requests/<uuid>`,
`/requests/new-by-phone`'s "Needs a phone check" list) and `outcome_summary` (the duplicate
panel's "prior request, outcome, cancel reason" -- intake.md §2 table row "Duplicates").

**No P or C field ever appears here** (intake.md §7: "List ... No P or C fields"; detail
queries include C fields -- shown to any `request.view` holder, including the Administrator,
per the Q-124 decision that only *contact* details are masked/reveal-gated for them, never
the description/hazards/etc.). P fields are reached only through
`ham.requests.services.reveal_requester_pii`.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import QuerySet

from ham.authz import roles
from ham.authz.matrix import authorize

from .models import AssistanceRequest
from .states import RequestStatus

if TYPE_CHECKING:
    from ham.authz.context import ActorContext

_DIR_AD = frozenset({roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR})


def can_see_needs_phone_check(ctx: ActorContext) -> bool:
    return bool(ctx.effective_roles & _DIR_AD)


def can_reveal(ctx: ActorContext, request: AssistanceRequest) -> bool:
    return authorize(ctx, "requester_pii.reveal", request).allowed


_LEADERSHIP_REQUEST_ROLES = _DIR_AD | {roles.PASTOR, roles.BOARD_REPRESENTATIVE}


def is_masked_view(ctx: ActorContext) -> bool:
    """Q-124: true only when the Administrator role is what's granting access here, and no
    leadership role also would -- contact details always masked, no reveal button, photo
    count only (Q-138)."""
    return roles.ADMINISTRATOR in ctx.effective_roles and not (
        ctx.effective_roles & _LEADERSHIP_REQUEST_ROLES
    )


@dataclasses.dataclass(frozen=True, slots=True)
class RequestListRow:
    """intake.md §7 `/requests`: "ID, category, urgent, status, age, media count, 'possible
    earlier request' flag. No P or C fields" (Q-132: HAM # + category only)."""

    id: UUID
    reference_number: int
    display_number: str
    need_category: str
    urgent_requested: bool
    status: str
    submitted_at: dt.datetime
    has_possible_duplicate: bool


def _visible_statuses(ctx: ActorContext) -> list[str]:
    statuses = [s.value for s in RequestStatus]
    if not can_see_needs_phone_check(ctx):
        statuses = [s for s in statuses if s != RequestStatus.NEEDS_PHONE_CHECK.value]
    return statuses


def scope_queryset_for_requests(ctx: ActorContext, queryset: QuerySet) -> QuerySet:
    """Registered with `ham.authz.scopes` for `request.list` (Q-025: "Needs a phone check"
    requests are Director/Assistant Director only, never shown to Pastor/Board rep or the
    Administrator)."""
    return queryset.filter(status__in=_visible_statuses(ctx))


def list_requests(
    ctx: ActorContext,
    *,
    status: str | None = None,
    urgent: bool | None = None,
    reference_number: int | None = None,
) -> list[RequestListRow]:
    qs: QuerySet[AssistanceRequest] = AssistanceRequest.objects.all().order_by(
        "-urgent_requested", "-submitted_at"
    )
    qs = scope_queryset_for_requests(ctx, qs)
    if status:
        qs = qs.filter(status=status)
    if urgent is not None:
        qs = qs.filter(urgent_requested=urgent)
    if reference_number is not None:
        qs = qs.filter(reference_number=reference_number)

    duplicate_ids = set(qs.filter(matches__isnull=False).values_list("id", flat=True))
    return [
        RequestListRow(
            id=r.id,
            reference_number=r.reference_number,
            display_number=r.display_number,
            need_category=r.need_category,
            urgent_requested=r.urgent_requested,
            status=r.status,
            submitted_at=r.submitted_at,
            has_possible_duplicate=r.id in duplicate_ids,
        )
        for r in qs
    ]


def needs_phone_check_list(ctx: ActorContext) -> list[RequestListRow]:
    """intake.md §7/§10 "GET /requests/new-by-phone" companion list, Director/AD only
    (`request.needs_phone_check.list`)."""
    if not can_see_needs_phone_check(ctx):
        return []
    qs = AssistanceRequest.objects.filter(status=RequestStatus.NEEDS_PHONE_CHECK.value).order_by(
        "-urgent_requested", "submitted_at"
    )
    return [
        RequestListRow(
            id=r.id,
            reference_number=r.reference_number,
            display_number=r.display_number,
            need_category=r.need_category,
            urgent_requested=r.urgent_requested,
            status=r.status,
            submitted_at=r.submitted_at,
            has_possible_duplicate=False,
        )
        for r in qs
    ]


@dataclasses.dataclass(frozen=True, slots=True)
class RequestDetailRow:
    """intake.md §7 `/requests/<uuid>`: "C fields, relationship, property type, media gallery,
    status history; duplicate panel if `request.history.view`." No P fields; those come only
    from `reveal_requester_pii`."""

    id: UUID
    reference_number: int
    display_number: str
    status: str
    need_category: str
    description: str
    urgent_requested: bool
    urgency_justification: str
    urgency_status: str
    known_hazards: str
    preferred_availability: str
    preferred_contact_method: str
    relationship_to_property: str
    property_type: str
    attestation_version: str
    submitted_at: dt.datetime
    status_changed_at: dt.datetime
    closed_at: dt.datetime | None
    cancel_reason_code: str
    can_reveal_contact: bool
    is_masked_view: bool
    photo_count_only: bool  # Q-138: the Administrator sees a count, never the gallery


def get_request_detail(ctx: ActorContext, request_id: UUID) -> RequestDetailRow | None:
    try:
        r = AssistanceRequest.objects.select_related("property").get(pk=request_id)
    except AssistanceRequest.DoesNotExist:
        return None
    return RequestDetailRow(
        id=r.id,
        reference_number=r.reference_number,
        display_number=r.display_number,
        status=r.status,
        need_category=r.need_category,
        description=r.description,
        urgent_requested=r.urgent_requested,
        urgency_justification=r.urgency_justification,
        urgency_status=r.urgency_status,
        known_hazards=r.known_hazards,
        preferred_availability=r.preferred_availability,
        preferred_contact_method=r.preferred_contact_method,
        relationship_to_property=r.relationship_to_property,
        property_type=r.property.property_type,
        attestation_version=r.attestation_version,
        submitted_at=r.submitted_at,
        status_changed_at=r.status_changed_at,
        closed_at=r.closed_at,
        cancel_reason_code=r.cancel_reason_code,
        can_reveal_contact=can_reveal(ctx, r),
        is_masked_view=is_masked_view(ctx),
        photo_count_only=roles.ADMINISTRATOR in ctx.effective_roles,
    )


# --------------------------------------------------------------------------------------
# outcome_summary (intake.md §2: "outcome_summary(request) in ham.requests" -- the duplicate
# panel's "prior request, outcome, cancel reason, assistance history once it exists")
# --------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True, slots=True)
class PriorRequestOutcome:
    request_id: UUID
    display_number: str
    status: str
    cancel_reason_code: str
    submitted_at: dt.datetime
    reasons: tuple[str, ...]


def outcome_summary(request: AssistanceRequest) -> list[PriorRequestOutcome]:
    """Every earlier request flagged as a possible match for ``request`` (PRD §9), newest
    match first -- step 3 will add the approval/rejection reason automatically once those
    decisions exist (intake.md §2: "Approval/rejection reason appears in the panel
    automatically")."""
    matches = request.matches.select_related("prior_request").order_by("-detected_at")
    return [
        PriorRequestOutcome(
            request_id=m.prior_request.id,
            display_number=m.prior_request.display_number,
            status=m.prior_request.status,
            cancel_reason_code=m.prior_request.cancel_reason_code,
            submitted_at=m.prior_request.submitted_at,
            reasons=tuple(m.reasons),
        )
        for m in matches
    ]
