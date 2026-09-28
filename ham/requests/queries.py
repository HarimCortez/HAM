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
from ham.platform import otp

from .matching import normalize_email
from .models import AssistanceRequest, Requester
from .states import RequestStatus, VerificationMethod

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
    need_category: str
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
            need_category=m.prior_request.need_category,
            status=m.prior_request.status,
            cancel_reason_code=m.prior_request.cancel_reason_code,
            submitted_at=m.prior_request.submitted_at,
            reasons=tuple(m.reasons),
        )
        for m in matches
    ]


@dataclasses.dataclass(frozen=True, slots=True)
class RequesterPageRow:
    """S2.7's secure request page (R10): the requester's *own* view of their own request,
    reached only through an already-resolved `RequesterContext` (a valid access link/token
    already scopes this to exactly one request — intake-contracts.md §1 `Scope.OWN_REQUEST`).
    Unlike `RequestDetailRow` (leadership), the contact fields here are the raw values on
    file: the view is responsible for masking them (`ham.requester_portal.projection.
    masked_contact`) before they ever reach a template — this dataclass itself is never
    passed straight into a response."""

    id: UUID
    reference_number: int
    display_number: str
    status: str
    need_category: str
    description: str
    urgent_requested: bool
    known_hazards: str
    preferred_availability: str
    preferred_contact_method: str
    property_type: str
    city: str
    postal_code: str
    line1: str
    full_name: str
    email: str | None
    phone: str
    submitted_at: dt.datetime
    closed_at: dt.datetime | None
    cancel_reason_code: str


def get_request_for_requester(request_id: UUID) -> RequesterPageRow | None:
    """`ham.web`'s secure-page view (S2.7) builds a `RequesterContext` from the link token
    first (`ham.requester_portal.services.resolve_token`), so by the time this is called the
    caller is already known to hold a live link for exactly this request; no further
    authorization decision happens here (foundation.md §7: the *route* declared
    `requester.request.view`, scoped `OWN_REQUEST`)."""
    try:
        r = AssistanceRequest.objects.select_related("property", "requester").get(pk=request_id)
    except AssistanceRequest.DoesNotExist:
        return None
    return RequesterPageRow(
        id=r.id,
        reference_number=r.reference_number,
        display_number=r.display_number,
        status=r.status,
        need_category=r.need_category,
        description=r.description,
        urgent_requested=r.urgent_requested,
        known_hazards=r.known_hazards,
        preferred_availability=r.preferred_availability,
        preferred_contact_method=r.preferred_contact_method,
        property_type=r.property.property_type,
        city=r.property.city,
        postal_code=r.property.postal_code,
        line1=r.property.line1,
        full_name=r.requester.full_name,
        email=r.requester.email,
        phone=r.requester.phone,
        submitted_at=r.submitted_at,
        closed_at=r.closed_at,
        cancel_reason_code=r.cancel_reason_code,
    )


# --------------------------------------------------------------------------------------
# Requester-portal lookups (intake-contracts.md §8.3): the three callables
# `ham.requester_portal.services` needs but may not import this app's models to build
# itself, since `ham.requester_portal` sits *above* `ham.requests` in the layer order
# (`web -> requester_portal -> media -> requests -> ...`). `ham.requests` may not import
# `ham.requester_portal` either (the same layers contract forbids the upward direction), so
# these return plain values only -- `ham.requester_portal.apps.RequesterPortalConfig.ready()`
# imports *this* module (a legal downward import) and wraps the plain values into its own
# `RequestLinkFacts` dataclass before calling `register_request_facts_lookup` etc.
# --------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True, slots=True)
class PortalRequestFacts:
    """Plain-value twin of `ham.requester_portal.services.RequestLinkFacts` -- this module
    cannot import that dataclass (upward import, forbidden by the layers contract)."""

    status: str
    closed_at: dt.datetime | None


def request_facts_for_portal(request_id: UUID) -> PortalRequestFacts:
    """`register_request_facts_lookup`: `AssistanceRequest.status`/`closed_at` (this app has
    no `completed_at` yet -- a later step's field, left `None` by the caller). Raises
    `ValueError` for an unknown id, matching the registration docstring."""
    row = AssistanceRequest.objects.filter(id=request_id).values("status", "closed_at").first()
    if row is None:
        raise ValueError(f"unknown request {request_id}")
    return PortalRequestFacts(status=row["status"], closed_at=row["closed_at"])


def request_contact_for_portal(request_id: UUID) -> str | None:
    """`register_request_contact_lookup`: the normalized email on file for ``request_id``, or
    `None` for a no-email (`NEEDS_PHONE_CHECK`) request or an unknown id -- never the caller's
    claimed email, only what's actually on file (intake-contracts.md §8.3, "no enumeration")."""
    email = Requester.objects.filter(request_id=request_id).values_list("email", flat=True).first()
    return normalize_email(email) if email else None


# --------------------------------------------------------------------------------------
# L1 search (§71 "search by request ID only") and L2's contact-verification/history data
# (S2.8). No P/C fields here -- verifications carry only method/time/actor.
# --------------------------------------------------------------------------------------
def get_request_by_id(ctx: ActorContext, request_id: UUID) -> AssistanceRequest | None:
    """The raw row, scoped the same way `list_requests` is (a pastor/Board rep may never
    fetch a still-`NEEDS_PHONE_CHECK` request by guessing its id, Q-025)."""
    qs = scope_queryset_for_requests(ctx, AssistanceRequest.objects.select_related("property"))
    return qs.filter(pk=request_id).first()


@dataclasses.dataclass(frozen=True, slots=True)
class ContactVerificationRow:
    method: str
    verified_at: dt.datetime
    verified_by_user_id: UUID | None


def contact_verifications(request_id: UUID) -> list[ContactVerificationRow]:
    from .models import RequestContactVerification

    return [
        ContactVerificationRow(
            method=v.method, verified_at=v.verified_at, verified_by_user_id=v.verified_by_user_id
        )
        for v in RequestContactVerification.objects.filter(request_id=request_id).order_by(
            "verified_at"
        )
    ]


@dataclasses.dataclass(frozen=True, slots=True)
class HistoryEntry:
    label: str
    occurred_at: dt.datetime
    actor_user_id: UUID | None = None


def request_history(request: AssistanceRequest) -> list[HistoryEntry]:
    """A small, PII-free lifecycle timeline (L2 "History") built from domain data, not the
    full audit log -- pastors and the Board rep may see it (`request.history.view`) without
    holding `audit.view` (Administrator/Director only, `ham.authz.matrix`)."""
    from .presentation import CANCEL_REASON_BANNER_LABELS, SOURCE_LABELS, VERIFICATION_METHOD_LABELS

    entries = [
        HistoryEntry(
            label=f"Sent by requester ({SOURCE_LABELS.get(request.source, request.source)})",
            occurred_at=request.submitted_at,
        )
    ]
    for v in contact_verifications(request.id):
        if v.method == VerificationMethod.STAFF_PHONE_CALL.value:
            entries.append(
                HistoryEntry(
                    label="Verified by phone call",
                    occurred_at=v.verified_at,
                    actor_user_id=v.verified_by_user_id,
                )
            )
        else:
            word = VERIFICATION_METHOD_LABELS.get(v.method, v.method)
            entries.append(
                HistoryEntry(label=f"Email confirmed ({word})", occurred_at=v.verified_at)
            )

    if request.status in (RequestStatus.AWAITING_APPROVAL.value,):
        entries.append(
            HistoryEntry(
                label="Awaiting Approval (automatic)", occurred_at=request.status_changed_at
            )
        )
    if request.status == RequestStatus.CANCELLED.value and request.closed_at is not None:
        reason = CANCEL_REASON_BANNER_LABELS.get(
            request.cancel_reason_code, request.cancel_reason_code
        )
        entries.append(HistoryEntry(label=reason, occurred_at=request.closed_at))
    if request.attested_at is not None:
        entries.append(
            HistoryEntry(
                label=f"Agreed to intake statements {request.attestation_version}",
                occurred_at=request.attested_at,
            )
        )
    entries.sort(key=lambda e: e.occurred_at)
    return entries


def request_ids_for_portal_email(email: str) -> list[UUID]:
    """`register_email_to_request_ids_lookup`: every request id with ``email`` (already
    normalized by the caller) on file, open or not -- matched by the same keyed HMAC used for
    duplicate matching (`Requester.email_key`), tried against every configured key
    (`ham.platform.otp.hash_candidates`) so a rotated key doesn't silently stop matching."""
    if not email:
        return []
    candidates = otp.hash_candidates(email)
    return list(
        Requester.objects.filter(email_key__in=candidates).values_list("request_id", flat=True)
    )
