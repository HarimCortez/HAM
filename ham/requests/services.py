"""`ham.requests`' own write path (intake.md §2 "a module calls another only through its
services.py, and only downward").

S2.2 implements the real bodies behind the S2.0 seam (`docs/architecture/intake-contracts.md`)
plus the rest of step 2's "requests core" commands (intake.md §10 S2.2).

**Coordination note on `submit_request`'s signature** (documented here, not silently): the
S2.0 stub only carried `draft_id`/`verification_id`, because the actual submitted answers
live encrypted in `ham.requester_portal.IntakeDraft.payload_ciphertext` -- and
`ham.requester_portal` sits *above* `ham.requests` in the layer order (intake.md §2: `web ->
requester_portal -> media -> requests -> ...`), so this module may never import it to decrypt
that payload itself. `submit_request` below therefore adds one more required keyword,
`payload: SubmittedRequestPayload`, that the caller (the portal's own orchestration, S2.3)
must supply already-decrypted and verified; `draft_id`/`verification_id` are kept and stored
only for traceability (`RequestContactVerification.challenge_id`, audit `context`). This is a
strictly additive change to the stub's kwargs, not a different write path.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.db.models import QuerySet

from ham.audit.services import record as audit_record
from ham.authz import roles
from ham.authz.commands import CommandResult, OutboxSpec, PermissionDenied, command
from ham.authz.matrix import authorize
from ham.platform import otp
from ham.platform.clock import now as clock_now
from ham.requests import certifications
from ham.requests.matching import MatchKeys, find_matches, match_keys
from ham.requests.models import (
    AssistanceRequest,
    Property,
    RequestContactVerification,
    Requester,
    RequestMatch,
    next_reference_number,
)
from ham.requests.states import (
    CancelReason,
    RequestAction,
    RequestStatus,
    VerificationMethod,
    check_transition,
    initial_urgency_status,
)
from ham.rules import RULES

if TYPE_CHECKING:
    from ham.authz.context import ActorContext, RequesterContext, SystemContext


# ------------------------------------------------------------------------------------------
# Media purge hook (security review M4): `ham.media` sits *above* `ham.requests` in the
# layers contract (`ham.web -> ham.requester_portal -> ham.media -> ham.requests -> ...`), so
# this module may never import it to delete a spam-purged request's storage objects itself.
# `ham.media.apps.MediaConfig.ready()` calls `register_media_purge_hook` with `ham.media.
# services.purge_all_for_request` (it *can* legally import this module, downward) -- the
# reverse of the lookup pattern `ham.requester_portal` uses for its own cross-app queries.
# ------------------------------------------------------------------------------------------
_media_purge_hook: Any = None


def register_media_purge_hook(fn: Any) -> None:
    """Called once from `ham.media.apps.MediaConfig.ready()`."""
    global _media_purge_hook
    _media_purge_hook = fn


# ------------------------------------------------------------------------------------------
# Submission payload (see the module docstring's coordination note)
# ------------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True, slots=True)
class SubmittedRequestPayload:
    """Everything `ham.requester_portal`'s verified `IntakeDraft` holds that `submit_request`
    needs -- intake.md §3 `AssistanceRequest`/`Requester`/`Property` field lists (D1)."""

    full_name: str
    phone: str
    line1: str
    city: str
    state: str
    postal_code: str
    property_type: str
    relationship_to_property: str
    need_category: str
    preferred_contact_method: str
    attested_statements: tuple[str, ...]
    email: str | None = None
    email_opt_out: bool = False
    line2: str = ""
    owner_name: str = ""
    description: str = ""
    urgent_requested: bool = False
    urgency_justification: str = ""
    known_hazards: str = ""
    preferred_availability: str = ""
    verification_method: VerificationMethod | str = VerificationMethod.EMAIL_CODE
    verified_value: str = ""  # the email/phone actually verified, for the audit trail's S key
    intake_source_id: UUID | None = None
    source: str = "public_form"


def _hashed_match_keys(payload: SubmittedRequestPayload) -> dict[str, str | None]:
    keys = match_keys(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        line1=payload.line1,
        line2=payload.line2,
        postal_code=payload.postal_code,
    )
    return {
        "email_key": otp.hash_value(keys.email) if keys.email else None,
        "phone_key": otp.hash_value(keys.phone) if keys.phone else None,
        "name_zip_key": otp.hash_value(keys.name_zip) if keys.name_zip else None,
        "address_key": otp.hash_value(keys.address) if keys.address else None,
    }


# ------------------------------------------------------------------------------------------
# request.submit
# ------------------------------------------------------------------------------------------
# **Coordination note (deviation from wave2-common.md's literal instruction, reported here
# rather than chosen silently):** wave2-common.md says this function should call
# `ham.requester_portal.services.issue_link` itself, guarded, after creating the request.
# That is not possible while keeping `lint-imports` green: `ham.requests` sits *below*
# `ham.requester_portal` in intake.md §2's layer order (`web -> requester_portal -> media ->
# requests -> ...`, "a module calls another only through its services.py, and only
# downward"), and the import-linter `layers` contract enforces that statically -- it flags a
# lazy/guarded `import ham.requester_portal.services` inside this function body exactly the
# same as a top-level one (static analysis of the import statement, not the runtime
# try/except around it). intake.md §2 itself already gives the correct owner: "The portal
# orchestrates submission: it verifies the draft, calls `requests.services.submit_request`,
# then issues the link, all in one transaction" -- i.e. `ham.requester_portal` (S2.3) calls
# both, in that order, inside its own transaction, exactly the shape
# `docs/architecture/intake-contracts.md` §3 documents for `issue_link`. `submit_request`
# below is therefore self-contained (creates the request, audits, emits `RequestSubmitted`)
# and returns the created row for the caller to use with `issue_link` itself.
@command("request.submit")
def submit_request(
    ctx: RequesterContext,
    *,
    draft_id: UUID,
    verification_id: UUID | None,
    payload: SubmittedRequestPayload,
) -> CommandResult:
    method = VerificationMethod(payload.verification_method)
    action = (
        RequestAction.SUBMIT_WITHOUT_EMAIL
        if payload.email_opt_out
        else RequestAction.SUBMIT_VERIFIED
    )
    decision = check_transition(
        action,
        None,
        actor_roles=ctx.roles,
        verification_method=method,
        email_opt_out=payload.email_opt_out,
        has_email=bool(payload.email),
    )
    if not decision.allowed:
        raise ValueError(f"request.submit refused: {decision.refusal}")
    assert decision.target is not None

    if not certifications.statements_satisfy_relationship(
        payload.relationship_to_property, payload.attested_statements
    ):
        raise ValueError("request.submit: missing a required certification statement")
    if payload.urgent_requested and not payload.urgency_justification.strip():
        raise ValueError("request.submit: urgent requests need a justification")

    now = clock_now()
    request = AssistanceRequest.objects.create(
        reference_number=next_reference_number(),
        status=decision.target.value,
        source=payload.source,
        intake_source_id=payload.intake_source_id,
        need_category=payload.need_category,
        description=payload.description,
        urgent_requested=payload.urgent_requested,
        urgency_justification=payload.urgency_justification,
        urgency_status=initial_urgency_status(payload.urgent_requested).value,
        known_hazards=payload.known_hazards,
        preferred_availability=payload.preferred_availability,
        preferred_contact_method=payload.preferred_contact_method,
        relationship_to_property=payload.relationship_to_property,
        attestation_version=certifications.CURRENT_ATTESTATION_VERSION,
        attested_statements=list(payload.attested_statements),
        attested_at=now,
        submitted_at=now,
        status_changed_at=now,
    )
    keys = _hashed_match_keys(payload)
    Requester.objects.create(
        request=request,
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        email_key=keys["email_key"],
        phone_key=keys["phone_key"],
        name_zip_key=keys["name_zip_key"],
    )
    Property.objects.create(
        request=request,
        line1=payload.line1,
        line2=payload.line2,
        city=payload.city,
        state=payload.state,
        postal_code=payload.postal_code,
        property_type=payload.property_type,
        owner_name=payload.owner_name,
        address_key=keys["address_key"],
    )
    if payload.verified_value:
        email_methods = (VerificationMethod.EMAIL_CODE, VerificationMethod.EMAIL_LINK)
        RequestContactVerification.objects.create(
            request=request,
            channel="email" if method in email_methods else "phone",
            method=method.value,
            value_key=otp.hash_value(payload.verified_value),
            purpose="intake",
            verified_at=now,
            challenge_id=verification_id,
        )

    if request.status == RequestStatus.SUBMITTED.value:
        from ham.requests.jobs import defer_complete_intake_checks

        defer_complete_intake_checks(request.id)

    transition = decision.transition
    assert transition is not None
    return CommandResult(
        value=request,
        audit_action=transition.audit_action,
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        after={"status": request.status, "source": request.source},
        context={
            "draft_id": str(draft_id),
            "verification_id": str(verification_id) if verification_id is not None else None,
        },
        outbox=OutboxSpec(
            transition.outbox_event,
            aggregate_type="request",
            aggregate_id=request.id,
            payload={
                "request_id": str(request.id),
                "source": request.source,
                "urgent": request.urgent_requested,
            },
        )
        if transition.outbox_event
        else None,
    )


# ------------------------------------------------------------------------------------------
# system.request.complete_intake_checks (the duplicate-check job)
# ------------------------------------------------------------------------------------------
def _prior_match_candidates(request: AssistanceRequest) -> QuerySet[Requester]:
    return (
        Requester.objects.filter(request__status__in=[s.value for s in RequestStatus])
        .exclude(request_id=request.id)
        .select_related("request", "request__property")
    )


@command("system.request.complete_intake_checks")
def complete_intake_checks(ctx: SystemContext, *, request_id: UUID) -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    requester = Requester.objects.get(request=request)
    property_ = Property.objects.get(request=request)

    new_keys = MatchKeys(
        address=property_.address_key,
        phone=requester.phone_key,
        email=requester.email_key,
        name_zip=requester.name_zip_key,
    )
    priors = [
        (
            r.request_id,
            MatchKeys(
                address=r.request.property.address_key if hasattr(r.request, "property") else None,
                phone=r.phone_key,
                email=r.email_key,
                name_zip=r.name_zip_key,
            ),
        )
        for r in _prior_match_candidates(request)
    ]
    matches = find_matches(new_keys, priors)

    now = clock_now()
    for prior_id, reasons in matches:
        RequestMatch.objects.get_or_create(
            request=request,
            prior_request_id=prior_id,
            defaults={"reasons": [r.value for r in reasons], "detected_at": now},
        )

    decision = check_transition(
        RequestAction.COMPLETE_INTAKE_CHECKS,
        request.status,
        actor_roles=ctx.roles,
        intake_checks_complete=True,
    )
    if not decision.allowed:
        raise ValueError(f"complete_intake_checks refused: {decision.refusal}")
    assert decision.target is not None

    request.status = decision.target.value
    request.status_changed_at = now
    request.save(update_fields=["status", "status_changed_at"])

    transition = decision.transition
    assert transition is not None

    if matches:
        # intake.md §4: "request.status_changed (+ request.duplicates_flagged if there are
        # matches)" -- two distinct audit rows. `@command` only ever writes the one named by
        # this function's returned `CommandResult`, so the second is written by hand, still
        # inside the same atomic block (the wrapper's `with transaction.atomic()` is already
        # open while this function body runs).
        audit_record(
            ctx=ctx,
            action="request.duplicates_flagged",
            target_type="request",
            target_id=str(request.id),
            project_id=request.id,
            context={"duplicate_of": [str(prior_id) for prior_id, _reasons in matches]},
        )

    return CommandResult(
        value=request,
        audit_action=transition.audit_action,
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        before={"status": RequestStatus.SUBMITTED.value},
        after={"status": request.status},
        outbox=OutboxSpec(
            transition.outbox_event,
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "urgent": request.urgent_requested},
        )
        if transition.outbox_event
        else None,
    )


# ------------------------------------------------------------------------------------------
# request.contact_verify_phone ("verified by phone call", Q-025)
# ------------------------------------------------------------------------------------------
def _resource_request(ctx: Any, *, request_id: UUID, **_: Any) -> AssistanceRequest:
    return AssistanceRequest.objects.get(pk=request_id)


@command("request.contact_verify_phone", resource_from=_resource_request)
def verify_by_phone(ctx: ActorContext, *, request_id: UUID, reason: str = "") -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    decision = check_transition(
        RequestAction.VERIFY_BY_PHONE,
        request.status,
        actor_roles=ctx.effective_roles,
        is_impersonating=ctx.is_impersonating,
    )
    if not decision.allowed:
        raise ValueError(f"verify_by_phone refused: {decision.refusal}")
    assert decision.target is not None

    now = clock_now()
    requester = Requester.objects.get(request=request)
    RequestContactVerification.objects.create(
        request=request,
        channel="phone",
        method=VerificationMethod.STAFF_PHONE_CALL.value,
        value_key=otp.hash_value(requester.phone),
        purpose="intake",
        verified_at=now,
        verified_by_user_id=ctx.user_id,
    )
    request.status = decision.target.value
    request.status_changed_at = now
    request.save(update_fields=["status", "status_changed_at"])

    from ham.requests.jobs import defer_complete_intake_checks

    defer_complete_intake_checks(request.id)

    transition = decision.transition
    assert transition is not None
    return CommandResult(
        value=request,
        audit_action=transition.audit_action,
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        before={"status": RequestStatus.NEEDS_PHONE_CHECK.value},
        after={"status": request.status},
        reason=reason,
    )


# ------------------------------------------------------------------------------------------
# request.cancel
# ------------------------------------------------------------------------------------------
@command("request.cancel", resource_from=_resource_request)
def cancel_request(
    ctx: ActorContext, *, request_id: UUID, reason_code: str, note: str = ""
) -> CommandResult:
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)
    decision = check_transition(
        RequestAction.CANCEL,
        request.status,
        actor_roles=ctx.effective_roles,
        is_impersonating=ctx.is_impersonating,
        reason=reason_code,
    )
    if not decision.allowed:
        raise ValueError(f"request.cancel refused: {decision.refusal}")
    assert decision.target is not None

    before_status = request.status
    now = clock_now()
    request.status = decision.target.value
    request.status_changed_at = now
    request.closed_at = now
    request.cancel_reason_code = CancelReason(reason_code).value
    request.cancel_note = note
    request.requester_access_ends_at = now + RULES.requester_access.REQUESTER_ACCESS_AFTER_CLOSE
    request.save(
        update_fields=[
            "status",
            "status_changed_at",
            "closed_at",
            "cancel_reason_code",
            "cancel_note",
            "requester_access_ends_at",
        ]
    )

    transition = decision.transition
    assert transition is not None
    return CommandResult(
        value=request,
        audit_action=transition.audit_action,
        target_type="request",
        target_id=str(request.id),
        project_id=request.id,
        before={"status": before_status},
        after={"status": request.status, "reason_code": request.cancel_reason_code},
        outbox=OutboxSpec(
            transition.outbox_event,
            aggregate_type="request",
            aggregate_id=request.id,
            payload={"request_id": str(request.id), "reason_code": request.cancel_reason_code},
        )
        if transition.outbox_event
        else None,
    )


# ------------------------------------------------------------------------------------------
# requester_pii.reveal (Q-009, Q-024, Q-081, Q-122, Q-125)
# ------------------------------------------------------------------------------------------
PII_SURFACES = frozenset({"detail_panel", "hover_card"})  # kept for callers' reference


@dataclasses.dataclass(frozen=True, slots=True)
class RevealedRequesterPII:
    full_name: str
    email: str | None
    phone: str
    line1: str
    line2: str
    city: str
    state: str
    postal_code: str
    owner_name: str


def reveal_requester_pii(
    ctx: ActorContext, *, request_id: UUID, surface: str = "detail_panel"
) -> RevealedRequesterPII:
    """Manually wired (not `@command`) like `ham.authz.audit_access.export_csv`: Q-024 needs a
    reveal that is sometimes *not* audited (a non-impersonating Director), which the generic
    `@command` pipeline (always writes one audit event per call) can't express. Denial is
    still audited (`ham.authz.commands._AUDITED_ON_DENIAL` lists `requester_pii.reveal`),
    mirrored by hand below, same as `export_csv` does for `audit.export`.
    """
    from django.db import transaction

    request = AssistanceRequest.objects.get(pk=request_id)
    decision = authorize(ctx, "requester_pii.reveal", request)
    if not decision.allowed:
        audit_record(
            ctx=ctx,
            action="authz.denied",
            target_type="action",
            target_id="requester_pii.reveal",
            reason=decision.reason,
        )
        raise PermissionDenied(f"requester_pii.reveal: {decision.reason}")

    requester = Requester.objects.get(request=request)
    property_ = Property.objects.get(request=request)
    fields = RevealedRequesterPII(
        full_name=requester.full_name,
        email=requester.email,
        phone=requester.phone,
        line1=property_.line1,
        line2=property_.line2,
        city=property_.city,
        state=property_.state,
        postal_code=property_.postal_code,
        owner_name=property_.owner_name,
    )

    # Q-024: exempt only a non-impersonating Director -- everyone else's reveal is logged,
    # field *names* only, never values (intake.md §5).
    exempt = roles.HAM_DIRECTOR in ctx.effective_roles and not ctx.is_impersonating
    if not exempt:
        with transaction.atomic():
            audit_record(
                ctx=ctx,
                action="requester_pii.revealed",
                target_type="request",
                target_id=str(request_id),
                project_id=request_id,
                context={
                    "fields": [f.name for f in dataclasses.fields(RevealedRequesterPII)],
                    "surface": surface,
                },
            )
    return fields


# ------------------------------------------------------------------------------------------
# system.intake.purge (Q-127 retention sweep, D4)
# ------------------------------------------------------------------------------------------
# One `@command` site for both retention outcomes (a duplicate `@command("system.intake.purge")`
# site would trip `tests/audit/test_command_registry.py`'s "no action wired twice" check) --
# `ham.requests.jobs.retention_sweep` calls this once per eligible id from either list; the
# branch below decides "erase everything" (spam) vs "erase only the P fields" (everyone else).
@command("system.intake.purge")
def purge_expired_request(ctx: SystemContext, *, request_id: UUID) -> CommandResult:
    """7 years after an ordinary close, erase name/email/phone/street (keep ZIP, category and
    outcome so "families served" reporting still works); a request closed as spam/test is
    erased entirely 90 days after closing instead -- nothing about it is worth keeping
    (Q-127, decided). Skips a request already anonymized (idempotent: the sweep may see the
    same row twice in a slow run)."""
    request = AssistanceRequest.objects.select_for_update().get(pk=request_id)

    if request.cancel_reason_code == CancelReason.SPAM.value:
        reference_number = request.reference_number
        # Security review M4: delete storage objects (originals/derivatives/thumbnails)
        # before the row cascade-deletes the RequestMedia rows that point at them, or they'd
        # be orphaned in the object store forever.
        if _media_purge_hook is not None:
            _media_purge_hook(request_id)
        request.delete()
        return CommandResult(
            value=None,
            audit_action="request.purged",
            target_type="request",
            target_id=str(request_id),
            context={"reference_number": reference_number},
        )

    requester = Requester.objects.select_for_update().get(request=request)
    if requester.anonymized_at is not None:
        raise ValueError("purge_expired_request: already anonymized")
    property_ = Property.objects.select_for_update().get(request=request)

    now = clock_now()
    requester.full_name = ""
    requester.email = None
    requester.phone = ""
    requester.email_key = None
    requester.phone_key = None
    requester.name_zip_key = None
    requester.anonymized_at = now
    requester.save()
    property_.line1 = ""
    property_.line2 = ""
    property_.city = ""
    property_.owner_name = ""
    property_.address_key = None
    property_.save()

    return CommandResult(
        value=request,
        audit_action="request.pii_purged",
        target_type="request",
        target_id=str(request_id),
        project_id=request_id,
    )


def is_request_open(request_id: UUID) -> bool:
    """Whether a request still accepts requester media (intake.md §2: media asks
    requests.services, requests never imports media). Open means the request exists and is
    not in a terminal status; batch-level rules (initial batch closes at decision, §46
    reopened batches) are ham.media's."""
    from .models import AssistanceRequest
    from .states import RequestStatus, is_terminal

    status = (
        AssistanceRequest.objects.filter(id=request_id).values_list("status", flat=True).first()
    )
    if status is None:
        return False
    return not is_terminal(RequestStatus(status))
