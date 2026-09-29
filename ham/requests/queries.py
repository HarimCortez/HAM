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
from ham.platform.clock import now as clock_now

from .matching import normalize_email
from .models import (
    Approval,
    ApprovalOutcome,
    ApprovalStage,
    AssistanceRequest,
    Reconsideration,
    RejectionReason,
    Requester,
)
from .states import RequestStatus, VerificationMethod, decision_is_undoable

if TYPE_CHECKING:
    from ham.authz.context import ActorContext

_DIR_AD = frozenset({roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR})


def can_see_needs_phone_check(ctx: ActorContext) -> bool:
    return bool(ctx.effective_roles & _DIR_AD)


def can_reveal(ctx: ActorContext, request: AssistanceRequest) -> bool:
    return authorize(ctx, "requester_pii.reveal", request).allowed


def can_view_history(ctx: ActorContext) -> bool:
    """M2/N5: whether this viewer holds `request.history.view` -- gates both the detail
    page's History section/duplicate panel and the list row's "possible earlier request"
    marker (`has_possible_duplicate`, below). Never true for the Administrator, even while
    impersonating a role that would otherwise qualify (`is_masked_view` already encodes that
    exact rule, Q-151) -- `authorize()` alone is blind to it, since `ctx.effective_roles`
    reflects the impersonation *target's* roles while impersonating, not the real actor's."""
    if is_masked_view(ctx):
        return False
    return authorize(ctx, "request.history.view", None).allowed


_LEADERSHIP_REQUEST_ROLES = _DIR_AD | {roles.PASTOR, roles.BOARD_REPRESENTATIVE}


def is_masked_view(ctx: ActorContext) -> bool:
    """Q-124: true only when the Administrator role is what's granting access here, and no
    leadership role also would -- contact details always masked, no reveal button, photo
    count only (Q-138).

    N5/Q-151: also true whenever the *real* signed-in actor is an Administrator who is
    currently impersonating someone else (a Pastor, Director, ...). `ctx.roles`/
    `effective_roles` reflect the impersonation *target's* roles while impersonating (never
    the real actor's), so the plain role check above would otherwise unmask the gallery/
    contact fields the moment an Administrator starts impersonating a leadership role --
    exactly the loophole `reveal_requester_pii`'s own L7/Q-151 fix already closed for the
    reveal button itself. Same mechanism: `ham.identity.services.user_holds_global_role` on
    `ctx.real_user_id`, since the matrix has no notion of "the real actor while
    impersonating"."""
    if roles.ADMINISTRATOR in ctx.effective_roles and not (
        ctx.effective_roles & _LEADERSHIP_REQUEST_ROLES
    ):
        return True
    if ctx.is_impersonating:
        from ham.identity.services import user_holds_global_role

        if user_holds_global_role(ctx.real_user_id, roles.ADMINISTRATOR):
            return True
    return False


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
    # S3.2 (docs/ux/approvals.md L1 status chips): a plain word, never more than the status
    # already implies -- "" for a status with no decision chip of its own.
    decision_chip: str = ""


# S3.2 (approvals.md §6 L1 "New status chips Approved / Not approved / Taking another look").
_DECISION_CHIPS: dict[str, str] = {
    RequestStatus.APPROVED.value: "Approved",
    RequestStatus.REJECTED.value: "Not approved",
    RequestStatus.RECONSIDERATION_PENDING.value: "Taking another look",
}

# S3.2 (approvals.md §6 L1 "views Awaiting approval, Waiting on requester, Reconsideration,
# Decided" -- "Waiting on requester" is S3.3's own query, not duplicated here).
VIEW_STATUS_FILTERS: dict[str, tuple[str, ...]] = {
    "awaiting_approval": (RequestStatus.AWAITING_APPROVAL.value,),
    "reconsideration": (RequestStatus.RECONSIDERATION_PENDING.value,),
    "decided": (
        RequestStatus.APPROVED.value,
        RequestStatus.REJECTED.value,
        RequestStatus.CANCELLED.value,
    ),
}


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
    view: str | None = None,
) -> list[RequestListRow]:
    qs: QuerySet[AssistanceRequest] = AssistanceRequest.objects.all().order_by(
        "-urgent_requested", "-submitted_at"
    )
    qs = scope_queryset_for_requests(ctx, qs)
    if status:
        qs = qs.filter(status=status)
    if view is not None:
        qs = qs.filter(status__in=VIEW_STATUS_FILTERS.get(view, ()))
    if urgent is not None:
        qs = qs.filter(urgent_requested=urgent)
    if reference_number is not None:
        qs = qs.filter(reference_number=reference_number)

    # M2: the marker is only ever computed for a viewer who actually holds
    # `request.history.view` -- never for the Administrator (view-only, masked -- Q-124),
    # even while impersonating a role that would otherwise qualify (N5/Q-151).
    show_marker = can_view_history(ctx)
    duplicate_ids = (
        set(qs.filter(matches__isnull=False).values_list("id", flat=True)) if show_marker else set()
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
            has_possible_duplicate=r.id in duplicate_ids,
            decision_chip=_DECISION_CHIPS.get(r.status, ""),
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
    urgency_reason: str
    urgency_justification: str
    urgency_status: str
    known_hazards: str
    preferred_availability: str
    contact_note: str  # Q-148: R5's "anything else about reaching you or visiting?"
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
    # S3.2 (approvals-contracts.md §4, Q-156/Q-176): non-None only when ``ctx`` is the person
    # who recorded the request's latest live decision and that decision is still inside its
    # undo window -- "pending, can be undone until {pending_undo_deadline}".
    pending_undo_approval_id: UUID | None = None
    pending_undo_deadline: dt.datetime | None = None


def _latest_live_approval(request_id: UUID) -> Approval | None:
    return (
        Approval.objects.filter(request_id=request_id, undone_at__isnull=True)
        .order_by("-decided_at")
        .first()
    )


def get_request_detail(ctx: ActorContext, request_id: UUID) -> RequestDetailRow | None:
    try:
        r = AssistanceRequest.objects.select_related("property").get(pk=request_id)
    except AssistanceRequest.DoesNotExist:
        return None
    masked = is_masked_view(ctx)
    pending_undo_approval_id: UUID | None = None
    pending_undo_deadline: dt.datetime | None = None
    latest_approval = _latest_live_approval(r.id)
    if (
        latest_approval is not None
        and ctx.user_id is not None
        and ctx.user_id == latest_approval.decided_by_user_id
        and decision_is_undoable(latest_approval.decided_at, clock_now(), latest_approval.undone_at)
    ):
        pending_undo_approval_id = latest_approval.id
        pending_undo_deadline = latest_approval.effective_at
    return RequestDetailRow(
        id=r.id,
        reference_number=r.reference_number,
        display_number=r.display_number,
        status=r.status,
        need_category=r.need_category,
        description=r.description,
        urgent_requested=r.urgent_requested,
        urgency_reason=r.urgency_reason,
        urgency_justification=r.urgency_justification,
        urgency_status=r.urgency_status,
        known_hazards=r.known_hazards,
        preferred_availability=r.preferred_availability,
        # NEW-1: R5's "anything else about reaching you or visiting?" (helper name, best time
        # to call) is close enough to contact info that it's blanked from the Administrator's
        # masked view too, not just P-field name/phone/email/street -- never reaches the
        # template, so `{% if detail.contact_note %}` in `_request_detail.html` simply doesn't
        # render for them, the same as an unset value.
        contact_note="" if masked else r.contact_note,
        preferred_contact_method=r.preferred_contact_method,
        relationship_to_property=r.relationship_to_property,
        property_type=r.property.property_type,
        attestation_version=r.attestation_version,
        submitted_at=r.submitted_at,
        status_changed_at=r.status_changed_at,
        closed_at=r.closed_at,
        cancel_reason_code=r.cancel_reason_code,
        can_reveal_contact=can_reveal(ctx, r),
        is_masked_view=masked,
        # N9 (coordinator handoff from FIX-B): higher privilege wins -- an Administrator who
        # also holds a leadership role must not be masked. `is_masked_view` (this module,
        # above) already encodes "Administrator AND no leadership role also grants access",
        # matching `ham.media.services.media_gallery_for`'s identical fix.
        photo_count_only=masked,
        pending_undo_approval_id=pending_undo_approval_id,
        pending_undo_deadline=pending_undo_deadline,
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
    # S3.2 (approvals-contracts.md §6, Q-167): the prior request's latest live decision, if
    # any -- outcome, reason label/code, and the rejection message. Callers must gate this
    # dataclass on `can_view_history(ctx)` (already true at both call sites) -- never shown to
    # the Administrator (Q-167).
    decision_outcome: str = ""
    decision_reason_code: str = ""
    decision_reason_label: str = ""
    decision_message: str = ""


_REJECTION_REASON_LABELS: dict[str, str] = dict(RejectionReason.choices)


def outcome_summary(request: AssistanceRequest) -> list[PriorRequestOutcome]:
    """Every earlier request flagged as a possible match for ``request`` (PRD §9), newest
    match first, with the prior request's own latest live decision outcome/reason/message
    (Q-167) -- gated by the caller on `can_view_history(ctx)`, never the Administrator."""
    matches = request.matches.select_related("prior_request").order_by("-detected_at")
    prior_ids = [m.prior_request_id for m in matches]
    latest_by_request: dict[UUID, Approval] = {}
    for a in Approval.objects.filter(request_id__in=prior_ids, undone_at__isnull=True).order_by(
        "decided_at"
    ):
        latest_by_request[a.request_id] = a  # last write (by decided_at ASC) wins: latest
    result = []
    for m in matches:
        decision = latest_by_request.get(m.prior_request_id)
        result.append(
            PriorRequestOutcome(
                request_id=m.prior_request.id,
                display_number=m.prior_request.display_number,
                need_category=m.prior_request.need_category,
                status=m.prior_request.status,
                cancel_reason_code=m.prior_request.cancel_reason_code,
                submitted_at=m.prior_request.submitted_at,
                reasons=tuple(m.reasons),
                decision_outcome=decision.outcome if decision else "",
                decision_reason_code=decision.reason_code if decision else "",
                decision_reason_label=(
                    _REJECTION_REASON_LABELS.get(decision.reason_code, "")
                    if decision and decision.reason_code
                    else ""
                ),
                decision_message=(
                    decision.reason
                    if decision and decision.outcome == ApprovalOutcome.REJECTED.value
                    else ""
                ),
            )
        )
    return result


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
    display_number: str = ""


def request_facts_for_portal(request_id: UUID) -> PortalRequestFacts:
    """`register_request_facts_lookup`: `AssistanceRequest.status`/`closed_at` (this app has
    no `completed_at` yet -- a later step's field, left `None` by the caller) plus the
    "HAM #NNN" display number (M7: `find_my_request`'s E4 email names the request without a
    second, ad hoc cross-app query). Raises `ValueError` for an unknown id, matching the
    registration docstring."""
    row = (
        AssistanceRequest.objects.filter(id=request_id)
        .values("status", "closed_at", "reference_number")
        .first()
    )
    if row is None:
        raise ValueError(f"unknown request {request_id}")
    return PortalRequestFacts(
        status=row["status"],
        closed_at=row["closed_at"],
        display_number=f"HAM #{row['reference_number']:03d}",
    )


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
    # Usability re-check Minor 3: a `title` tooltip (never shown in the plain label text)
    # for details that belong in the record but not the sentence -- e.g. the exact
    # attestation version on the "Agreed to the intake statements" entry.
    title: str = ""


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

    # PRD-guardian N8: `awaiting_approval_at` is set once and never cleared, so this entry
    # stays on the timeline even after a later cancellation moves `request.status` away from
    # AWAITING_APPROVAL (checking the *current* status here used to make the entry vanish).
    if request.awaiting_approval_at is not None:
        entries.append(
            HistoryEntry(
                label="Awaiting approval (automatic)", occurred_at=request.awaiting_approval_at
            )
        )
    if request.status == RequestStatus.CANCELLED.value and request.closed_at is not None:
        reason = CANCEL_REASON_BANNER_LABELS.get(
            request.cancel_reason_code, request.cancel_reason_code
        )
        entries.append(
            HistoryEntry(
                label=reason,
                occurred_at=request.closed_at,
                actor_user_id=request.closed_by_user_id,
            )
        )
    if request.attested_at is not None:
        entries.append(
            HistoryEntry(
                # Usability re-check Minor 3: plain wording in the timeline sentence -- the
                # version string stays in the record (`request.attestation_version`) and in
                # this entry's `title` tooltip, not the visible text.
                label="Agreed to the intake statements",
                occurred_at=request.attested_at,
                title=request.attestation_version,
            )
        )
    # S3.2 (approvals-contracts.md §5, §6): decisions, undo and reconsideration requests on
    # the same PII-free timeline, entries never carry the message/note/reason text.
    approvals = list(Approval.objects.filter(request_id=request.id).order_by("decided_at"))
    for a in approvals:
        if a.stage == ApprovalStage.RECONSIDERATION.value:
            label = (
                "Approved after reconsideration"
                if a.outcome == "approved"
                else "Reconsideration decided: not approved"
            )
        else:
            label = "Approved" if a.outcome == "approved" else "Not approved"
        entries.append(
            HistoryEntry(label=label, occurred_at=a.decided_at, actor_user_id=a.decided_by_user_id)
        )
        if a.undone_at is not None:
            entries.append(
                HistoryEntry(
                    label="Decision undone",
                    occurred_at=a.undone_at,
                    actor_user_id=a.undone_by_user_id,
                )
            )
    try:
        recon = request.reconsideration
    except Reconsideration.DoesNotExist:
        recon = None
    if recon is not None:
        via = "phone" if recon.requested_via == "phone" else "secure page"
        entries.append(
            HistoryEntry(
                label=f"Asked us to take another look ({via})",
                occurred_at=recon.requested_at,
                actor_user_id=recon.recorded_by_user_id,
            )
        )
    if (
        request.status == RequestStatus.REJECTED.value
        and request.closed_at is not None
        and not any(a.stage == ApprovalStage.RECONSIDERATION.value for a in approvals)
    ):
        entries.append(
            HistoryEntry(label="Rejection made final (automatic)", occurred_at=request.closed_at)
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


def recent_submission_count_for_email(email: str, *, since: dt.datetime) -> int:
    """M1: `RULES.intake.INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY` -- how many requests with this
    normalized email on file (any configured HMAC key) were submitted on or after ``since``.
    Called by `ham.requester_portal.services.submit_and_issue_link` right before it actually
    creates a request, not just at code-send time (a person can hold several still-valid
    verification codes from earlier in the day)."""
    if not email:
        return 0
    candidates = otp.hash_candidates(email)
    return Requester.objects.filter(
        email_key__in=candidates, request__submitted_at__gte=since
    ).count()


def recent_no_email_submission_count_for_phone(phone: str, *, since: dt.datetime) -> int:
    """Q-146 (proposed default in use): `RULES.intake.NO_EMAIL_SUBMISSIONS_PER_PHONE_PER_DAY`
    -- how many "I don't use email" requests with this phone number on file were submitted on
    or after ``since``. The per-email cap above cannot reach this path since there is no
    email."""
    if not phone:
        return 0
    candidates = otp.hash_candidates(phone)
    return Requester.objects.filter(
        phone_key__in=candidates, request__submitted_at__gte=since
    ).count()
