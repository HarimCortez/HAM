"""`ham.requester_portal`'s own write path (intake.md §2 "The portal orchestrates submission:
it verifies the draft, calls `requests.services.submit_request`, then issues the link, all in
one transaction").

Cross-app data this slice needs but doesn't own yet (S2.2's `ham.requests` models, built in a
different worktree in parallel) is reached through small registered lookups, not a direct
import of a not-yet-existing model class — the same "register a callable at app-startup"
pattern `ham.authz.commands` already uses to break its own cross-package cycle
(`_register_audit_recorder`/`_register_outbox_emitter`, `AuthzConfig.ready()`). See each
`register_*` function's docstring for exactly what `ham.requests` (`RequestsConfig.ready()`,
once merged) must call.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import transaction

from ham.audit.models import ACTOR_TYPE_SYSTEM
from ham.audit.services import record as audit_record
from ham.authz.commands import CommandResult, OutboxSpec, command
from ham.authz.context import RequesterContext
from ham.platform import otp
from ham.platform.clock import now as clock_now
from ham.platform.crypto import encrypt
from ham.requests.matching import normalize_email
from ham.requests.services import record_link_regeneration_verification
from ham.rules import RULES

from . import drafts, forms
from .models import IntakeSource, RequesterAccessLink, RequesterVerificationChallenge
from .validity import fixed_expiry, link_validity, normal_access_ends_at
from .verification import ChallengeRequestResult, request_link_regeneration_code


class IntakeSubmissionRateLimited(Exception):
    """M1/Q-146: raised by `submit_and_issue_link` when the daily submission cap for this
    email (`RULES.intake.INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY`) or, for the no-email path,
    this phone number (`RULES.intake.NO_EMAIL_SUBMISSIONS_PER_PHONE_PER_DAY`, Q-146) is
    already reached. Caught by `ham.web.views_requester`, which shows the same "answers are
    saved, try later" wording every other cap uses (H2: identical UI, never a hint about
    which specific limit tripped)."""


@dataclass(frozen=True, slots=True)
class IssuedLink:
    """What `issue_link` hands back — the raw token (shown/emailed exactly once; only its hash
    and an encrypted copy are ever stored, intake.md §3 `RequesterAccessLink`) plus the row."""

    token: str
    link: RequesterAccessLink


# ---------------------------------------------------------------------------------------
# Cross-app lookups `ham.requests` (S2.2) registers at Django startup
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RequestLinkFacts:
    """The handful of `AssistanceRequest` fields `ham.requester_portal.validity` needs."""

    status: str
    closed_at: dt.datetime | None
    completed_at: dt.datetime | None = None
    # M7: the "HAM #NNN" display number -- carried through the same registered lookup rather
    # than a direct `ham.requests.models.AssistanceRequest` import (this app sits *above*
    # `ham.requests` in the layers contract), so `find_my_request`'s E4 email can name the
    # request without a second, ad hoc cross-app query.
    display_number: str = ""


RequestFactsLookup = Callable[[UUID], RequestLinkFacts]
RequestContactLookup = Callable[[UUID], "str | None"]
EmailToRequestIdsLookup = Callable[[str], list[UUID]]

_request_facts_lookup: RequestFactsLookup | None = None
_request_contact_lookup: RequestContactLookup | None = None
_email_to_request_ids_lookup: EmailToRequestIdsLookup | None = None


def register_request_facts_lookup(fn: RequestFactsLookup) -> None:
    """`ham.requests` must call this from `RequestsConfig.ready()` with a function returning
    `RequestLinkFacts` for a `request_id` (`AssistanceRequest.status`/`closed_at`/
    `completed_at`) — needed to compute link validity (`ham.requester_portal.validity`)
    without this app importing a model it doesn't own. Raises `ValueError` for an unknown id."""
    global _request_facts_lookup
    _request_facts_lookup = fn


def register_request_contact_lookup(fn: RequestContactLookup) -> None:
    """`ham.requests` must call this with a function returning the normalized email **on
    file** for `request_id` (or `None` for a no-email/`NEEDS_PHONE_CHECK` request) — used only
    to decide where to send a regeneration code (`regenerate_link`); the caller-supplied email
    is never trusted directly (intake.md §9 "no enumeration")."""
    global _request_contact_lookup
    _request_contact_lookup = fn


def register_email_to_request_ids_lookup(fn: EmailToRequestIdsLookup) -> None:
    """`ham.requests` must call this with a function mapping a normalized email to every
    request id with that email on file (open or not) — used by `find_my_request` (Q-117 "one
    link-only verification email per matching request")."""
    global _email_to_request_ids_lookup
    _email_to_request_ids_lookup = fn


def _facts(request_id: UUID) -> RequestLinkFacts:
    if _request_facts_lookup is None:  # pragma: no cover - defensive; wired at app startup
        raise RuntimeError(
            "ham.requester_portal.services used before ham.requests registered its "
            "request-facts lookup (see register_request_facts_lookup)."
        )
    return _request_facts_lookup(request_id)


def _contact(request_id: UUID) -> str | None:
    if _request_contact_lookup is None:  # pragma: no cover - defensive
        raise RuntimeError(
            "ham.requester_portal.services used before ham.requests registered its "
            "request-contact lookup (see register_request_contact_lookup)."
        )
    return _request_contact_lookup(request_id)


def _requests_for_email(email: str) -> list[UUID]:
    if _email_to_request_ids_lookup is None:  # pragma: no cover - defensive
        raise RuntimeError(
            "ham.requester_portal.services used before ham.requests registered its "
            "email lookup (see register_email_to_request_ids_lookup)."
        )
    return _email_to_request_ids_lookup(email)


# ---------------------------------------------------------------------------------------
# Links: issue / resolve / regenerate / find (intake.md §4, §7.3; Q-102, Q-116, Q-117)
# ---------------------------------------------------------------------------------------
def issue_link(
    *,
    request_id: UUID,
    kind: str,
    verification_id: UUID | None = None,
) -> IssuedLink:
    """Creates a new `RequesterAccessLink`, revoking any still-live link for the same request
    in the same transaction (`revoke_reason="superseded"` — intake.md §4 auto-invalidate).
    Does not itself audit or email; the caller does (`kind` decides the audit action /
    outbox event name)."""
    now = clock_now()
    token = otp.generate_token()
    token_hash = otp.hash_value(token)
    facts = _facts(request_id)
    access_ends_at = normal_access_ends_at(
        status=facts.status, closed_at=facts.closed_at, completed_at=facts.completed_at
    )
    expires_at = fixed_expiry(kind=kind, issued_at=now, access_ends_at=access_ends_at)
    with transaction.atomic():
        RequesterAccessLink.objects.select_for_update().filter(
            request_id=request_id, revoked_at__isnull=True
        ).update(revoked_at=now, revoke_reason=RequesterAccessLink.REVOKE_SUPERSEDED)
        link = RequesterAccessLink.objects.create(
            request_id=request_id,
            token_hash=token_hash,
            token_ciphertext=encrypt(token),
            kind=kind,
            issued_at=now,
            expires_at=expires_at,
            verification_id=verification_id,
        )
    return IssuedLink(token=token, link=link)


def resolve_token(token: str, *, now: dt.datetime | None = None) -> RequesterContext | None:
    """Looks up a `RequesterAccessLink` by trying every configured `HAM_TOKEN_HMAC_KEYS`
    (`ham.platform.otp.hash_candidates`), checks validity (`ham.requester_portal.validity`),
    and returns a `RequesterContext` for the request it grants access to, or `None` for an
    unknown/expired/revoked token (intake.md §7: "Unknown and invalid tokens get the same
    page")."""
    now = now or clock_now()
    candidates = otp.hash_candidates(token)
    link = RequesterAccessLink.objects.filter(token_hash__in=candidates).first()
    if link is None:
        return None
    # L4: an orphaned link row (its request was purged, e.g. a spam delete before the
    # `RequestPurged` subscriber has caught up) is invalid, not a 500 -- same outcome as an
    # unknown token (intake.md §7: "unknown and invalid tokens get the same page").
    try:
        facts = _facts(link.request_id)
    except ValueError:
        return None
    validity = link_validity(
        kind=link.kind,
        issued_at=link.issued_at,
        revoked_at=link.revoked_at,
        status=facts.status,
        closed_at=facts.closed_at,
        completed_at=facts.completed_at,
        now=now,
    )
    if not validity.is_valid:
        return None
    # "written at most hourly" (intake.md §3) so an active reader doesn't write on every poll.
    if link.last_used_at is None or now - link.last_used_at >= dt.timedelta(hours=1):
        RequesterAccessLink.objects.filter(pk=link.pk).update(last_used_at=now)
    return RequesterContext(request_id=link.request_id, link_id=link.id)


def current_secure_page_path(request_id: UUID) -> str | None:
    """M8: the URL path to the requester's own currently-live access link, or `None` if there
    is none (e.g. a `NEEDS_PHONE_CHECK` request never has one). Used only when a caller has
    already independently established that *this exact browser* holds a valid session/link
    for this draft/request (`ham.web.views_requester`'s already-received handling) -- never
    surfaced to a browser that merely replayed an already-used code/link with no such proof."""
    link = (
        RequesterAccessLink.objects.filter(request_id=request_id, revoked_at__isnull=True)
        .order_by("-issued_at")
        .first()
    )
    if link is None:
        return None
    from django.urls import reverse

    from ham.platform.crypto import decrypt

    token = decrypt(link.token_ciphertext)
    return reverse("web:request_help_secure_page", kwargs={"token": token})


def _resource_own_request(ctx: RequesterContext, *args: Any, **kwargs: Any) -> RequesterContext:
    return ctx


@command("requester_link.regenerate", resource_from=_resource_own_request)
def regenerate_link_for_own_request(
    ctx: RequesterContext, *, verification_id: UUID, verification_method: str
) -> CommandResult:
    """Called once the requester has re-verified (fresh code/link) while already holding a
    `RequesterContext` for their own request (the common case: an about-to-expire but still
    resolvable link). `ham.requester_portal.services.regenerate_link` below is the public,
    email-driven entry point used when the old link has *already* expired.

    L8/M4: `verification_method` (``"email_code"``/``"email_link"``, `ham.requests.states.
    VerificationMethod`'s values) and `verification_id` (the challenge id) are recorded both
    in this command's own audit `context` and as an append-only `RequestContactVerification`
    row (`record_link_regeneration_verification`) -- before this fix, a link-regeneration
    re-verification left no trace in either place, unlike intake's own `submit_request`."""
    assert ctx.request_id is not None  # the matrix's OWN_REQUEST scope already guarantees this
    issued = issue_link(
        request_id=ctx.request_id,
        kind=RequesterAccessLink.KIND_REGENERATED,
        verification_id=verification_id,
    )
    on_file = _contact(ctx.request_id)
    if on_file is not None:
        record_link_regeneration_verification(
            request_id=ctx.request_id,
            method=verification_method,
            verified_value=on_file,
            challenge_id=verification_id,
        )
    audit_context = {
        "verification_method": verification_method,
        "challenge_id": str(verification_id),
    }
    return CommandResult(
        value=issued,
        audit_action="requester_link.regenerated",
        target_type="request",
        target_id=str(ctx.request_id),
        project_id=ctx.request_id,
        context=audit_context,
        after=audit_context,
        outbox=OutboxSpec(
            "RequesterAccessLinkIssued",
            aggregate_type="request",
            aggregate_id=ctx.request_id,
            payload={
                "request_id": str(ctx.request_id),
                "link_id": str(issued.link.id),
                "kind": "regenerated",
            },
        ),
    )


def regenerate_link(*, token: str, email: str, ip_address: str = "") -> ChallengeRequestResult:
    """R11a "your link expired": the person still has the *old* (now invalid) link/URL.
    Looks the request up by the old token — even revoked/expired rows still identify a real
    request — and, only if `email` matches the address on file (never trusting the caller's
    claim), sends a fresh code/link there. Identical `ChallengeRequestResult` either way
    (intake.md §9 "no enumeration"); the caller must show the same page regardless."""
    candidates = otp.hash_candidates(token)
    link = RequesterAccessLink.objects.filter(token_hash__in=candidates).first()
    if link is None:
        return ChallengeRequestResult("sent")
    on_file = _contact(link.request_id)
    normalized = normalize_email(email)
    if on_file is None or normalized is None or on_file != normalized:
        return ChallengeRequestResult("sent")
    return request_link_regeneration_code(
        request_id=link.request_id, email=on_file, ip_address=ip_address
    )


def link_owner_contact(*, token: str) -> tuple[UUID, str | None] | None:
    """R11a "link expired": looks up the request behind ``token`` even if the link itself is
    now expired/revoked/superseded (still-identifying rows are never deleted), so the expired-
    link page can offer "send a code to d•••@gmail.com" without the person retyping their
    address. Returns ``None`` only when the token is entirely unknown/malformed (R12) — the
    caller (S2.7) shows the same neutral page either way it can't help further (a `None`
    email here still means "this request exists but has no email on file")."""
    candidates = otp.hash_candidates(token)
    link = RequesterAccessLink.objects.filter(token_hash__in=candidates).first()
    if link is None:
        return None
    return link.request_id, _contact(link.request_id)


def find_my_request(*, email: str, ip_address: str = "") -> ChallengeRequestResult:
    """R11b "Check on your request" (Q-117): one link-only email per matching request; an
    address with no request gets none at all. The HTTP-visible response is identical
    regardless (intake.md §9); only whether/how many emails go out differs.

    Usability re-check M7: this used to send a verification *code* email (intake wording,
    with nowhere on R11b to type the code) and, once that code was entered, a *second*
    "new link" email (E3) via the generic link-regeneration path. R11b never asked anyone to
    prove anything beyond holding the inbox this link is emailed to (the same trust level as
    any "email me a reset link" flow) -- there is no code step here at all now: a fresh
    access link is issued directly and exactly one E4 email ("Here's the link to your
    request") is sent per matching request, never the code/E3 wording.

    M1: also enforces `RULES.intake.FIND_REQUEST_TRIES_PER_IP_PER_HOUR` -- counted from
    `FindRequestAttempt`, which logs every try (matched or not), not just the ones that
    happen to send an email (an unmatched address would otherwise never count against this
    cap at all)."""
    from .antiabuse import HONEYPOT_FIELD_NAME  # noqa: F401 - documents the caller's own check
    from .models import FindRequestAttempt

    now = clock_now()
    if ip_address:
        window_start = now - dt.timedelta(hours=1)
        recent = FindRequestAttempt.objects.filter(
            ip_address=ip_address, created_at__gte=window_start
        ).count()
        if recent >= RULES.intake.FIND_REQUEST_TRIES_PER_IP_PER_HOUR:
            # H2: identical-looking response either way; nothing is sent this time.
            return ChallengeRequestResult("sent")
    FindRequestAttempt.objects.create(ip_address=ip_address or None, created_at=now)

    normalized = normalize_email(email)
    if normalized is not None:
        for request_id in _requests_for_email(normalized):
            _issue_and_notify_found_link(request_id=request_id, email=normalized)
    return ChallengeRequestResult("sent")


def _issue_and_notify_found_link(*, request_id: UUID, email: str) -> None:
    """M7: issues a fresh access link directly (no code/verification step -- see
    `find_my_request`'s docstring) and emails E4 immediately, the same way
    `ham.requester_portal.verification`'s code emails are sent immediately rather than
    through the outbox -- this deliberately never touches the generic
    `RequesterAccessLinkIssued`/E3 ("new link") path (that event's own docstring in
    `notifications.py` flags the R11a/R11b ambiguity this resolves: R11b gets its own event/
    audit action and its own email wording, not a repurposed "your old link is dead" one)."""
    from .notifications import send_found_request_email

    display_number = _facts(request_id).display_number
    issued = issue_link(request_id=request_id, kind=RequesterAccessLink.KIND_REGENERATED)
    audit_record(
        ctx=None,
        actor_type=ACTOR_TYPE_SYSTEM,
        action="requester_link.found",
        target_type="request",
        target_id=str(request_id),
        project_id=request_id,
        context={"link_id": str(issued.link.id)},
    )
    send_found_request_email(display_number=display_number, email=email, link=issued.link)


# ---------------------------------------------------------------------------------------
# Orchestration: verify -> submit -> issue link, one transaction (intake.md §2)
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SubmissionResult:
    request: Any  # `ham.requests.models.AssistanceRequest` (S2.2)
    issued_link: IssuedLink | None  # None for a Q-025 no-email (NEEDS_PHONE_CHECK) submission


def _resolve_intake_source(code: str) -> tuple[UUID | None, str]:
    """PRD-GAP Q-114 / PRD-guardian M9: resolve an optional ``?c=`` church-issued code (Q-114
    "same form with an optional short code (link/QR) recording the source") to an active
    `IntakeSource` row. An unknown or deactivated code is not an error — it just falls back to
    the plain public-form source, same as no code at all (Q-114: "grants nothing extra").
    Code resolution is wired in this slice; the Director/AD create/deactivate management
    screen is a later slice's (see this module's own `IntakeSource` docstring)."""
    if not code:
        return None, "public_form"
    source = IntakeSource.objects.filter(code=code, deactivated_at__isnull=True).first()
    if source is None:
        return None, "public_form"
    return source.id, "church_link"


def _payload_from_cleaned(cleaned: dict, *, no_email: bool, method: str = "email_code") -> Any:
    """Builds `ham.requests.services.SubmittedRequestPayload` from
    `ham.requester_portal.forms.validate_intake_payload`'s ``cleaned`` dict. Free-text C
    fields (`known_hazards`/`preferred_availability`) are stored as the human-readable
    comma-joined answers; nothing here re-derives what `validate_intake_payload` already
    decided (this function only reshapes, never re-validates).

    PRD-guardian M1/UX M2/B1: need category, property type, and the certification statement
    codes used to need translating here, because the portal and `ham.requests` each had their
    own, differently-coded copy of the same vocabulary. There is now exactly one vocabulary
    for each (`ham.requests.models.NeedCategory`/`PropertyType`,
    `ham.requests.certifications`), so `cleaned["need_category"]`/`cleaned["property_type"]`/
    `cleaned["attested_statements"]` already carry the codes `ham.requests` persists —
    `attested_statements` is passed through exactly as ticked (never re-derived from
    "what this relationship requires"), so the stored record always matches what the
    requester actually accepted."""
    from ham.requests.services import SubmittedRequestPayload
    from ham.requests.states import VerificationMethod

    hazards = ", ".join(cleaned["hazards"])
    if cleaned.get("hazard_note"):
        hazards = f"{hazards} ({cleaned['hazard_note']})" if hazards else cleaned["hazard_note"]

    attested_statements = tuple(cleaned["attested_statements"])
    intake_source_id, source = _resolve_intake_source(cleaned.get("intake_source_code") or "")

    return SubmittedRequestPayload(
        full_name=cleaned["full_name"],
        phone=cleaned["phone"] or "",
        email=cleaned["email"],
        email_opt_out=no_email,
        line1=cleaned["line1"],
        line2=cleaned["line2"],
        city=cleaned["city"],
        state=cleaned["state"],
        postal_code=cleaned["postal_code"] or "",
        property_type=cleaned["property_type"],
        owner_name=cleaned["owner_name"],
        relationship_to_property=cleaned["relationship_to_property"],
        need_category=cleaned["need_category"],
        description=cleaned["description"],
        preferred_contact_method=cleaned["contact_preference"],
        attested_statements=attested_statements,
        urgent_requested=cleaned["urgent_requested"],
        urgency_reason=cleaned.get("urgency_reason") or "",
        urgency_justification=cleaned["urgency_justification"],
        known_hazards=hazards,
        preferred_availability=", ".join(cleaned["preferred_availability"]),
        contact_note=cleaned.get("contact_note") or "",
        # N7: which of the two emailed paths actually verified this address -- a typed code
        # (`VerificationMethod.EMAIL_CODE`) or a clicked scanner-safe link
        # (`VerificationMethod.EMAIL_LINK`) -- is now recorded accurately, not hard-coded to
        # "code" for every submission. `submit_and_issue_link`'s caller (`ham.web.
        # views_requester`) knows which one happened and passes it through.
        verification_method=(
            VerificationMethod.STAFF_PHONE_CALL if no_email else VerificationMethod(method)
        ),
        verified_value="" if no_email else (cleaned["email"] or ""),
        # PRD-GAP Q-114: see `_resolve_intake_source`'s docstring above.
        intake_source_id=intake_source_id,
        source=source,
    )


def submit_and_issue_link(
    *,
    draft_id: UUID,
    verification_id: UUID | None,
    verification_method: str = "email_code",
) -> SubmissionResult:
    """intake.md §2: "The portal orchestrates submission: it verifies the draft, calls
    `requests.services.submit_request`, then issues the link, all in one transaction."

    `verification_id` is `None` only for the Q-025 "I don't use email" path (no challenge was
    ever created; `ham.requests.services.submit_request` routes that request to
    `NEEDS_PHONE_CHECK`). Re-validates the draft's merged answers one last time before
    building `SubmittedRequestPayload` (CLAUDE.md's "AI suggestion -> user accepts -> HAM
    validates permissions/rules -> transaction" -- the caller's own pre-code-send validation
    is not trusted as the only gate).

    ``verification_method`` (N7): ``"email_code"`` (default, the R8 code-entry path) or
    ``"email_link"`` (the emailed one-click link) -- ignored for the no-email path, where
    `_payload_from_cleaned` always records `STAFF_PHONE_CALL`.
    """
    from ham.platform.church import church_profile
    from ham.requests.services import submit_request  # S2.2's `@command`-wrapped service

    raw = drafts.load_payload(draft_id)
    if raw is None:
        raise ValueError("submit_and_issue_link: unknown, consumed or expired draft")
    cleaned, errors = forms.validate_intake_payload(raw, church=church_profile())
    if cleaned is None:
        raise ValueError(
            f"submit_and_issue_link: draft answers no longer validate: {sorted(errors)}"
        )

    no_email = bool(cleaned["no_email"])
    if no_email != (verification_id is None):
        raise ValueError(
            "submit_and_issue_link: verification_id must be set iff the draft has an email"
        )

    # M1/Q-146: enforced right before the request is actually created (not just at
    # code-send time -- a person can hold several still-valid codes from earlier in the day).
    from ham.requests.queries import (
        recent_no_email_submission_count_for_phone,
        recent_submission_count_for_email,
    )

    since = clock_now() - dt.timedelta(hours=24)
    if no_email:
        if (
            recent_no_email_submission_count_for_phone(cleaned["phone"] or "", since=since)
            >= RULES.intake.NO_EMAIL_SUBMISSIONS_PER_PHONE_PER_DAY
        ):
            raise IntakeSubmissionRateLimited("no-email submission cap reached for this phone")
    else:
        if (
            recent_submission_count_for_email(cleaned["email"] or "", since=since)
            >= RULES.intake.INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY
        ):
            raise IntakeSubmissionRateLimited("submission cap reached for this email")

    payload = _payload_from_cleaned(cleaned, no_email=no_email, method=verification_method)

    ctx = RequesterContext(request_id=None)
    with transaction.atomic():
        # H1: the challenge named by `verification_id` must actually belong to THIS draft and
        # THIS submitted email -- otherwise a person could send a code to their own address,
        # change the draft's email to someone else's, and submit with the first code,
        # producing a request that falsely records the *victim's* email as "confirmed".
        # `select_for_update()` (inside this same atomic block) closes the race where two
        # concurrent submits try to spend the same challenge at once. Every check below is
        # required: purpose (only an intake challenge may create a request), already-consumed
        # (verify_code/consume_link already redeemed it -- this is not itself the redemption
        # step), belongs to this exact draft, matches the exact email now being submitted, and
        # has never already been used to create a request (one submission per verification;
        # `request_id` doubles as that one-time marker for purpose=intake rows, which
        # otherwise never set it at creation).
        if not no_email:
            assert verification_id is not None
            challenge = (
                RequesterVerificationChallenge.objects.select_for_update()
                .filter(pk=verification_id)
                .first()
            )
            if (
                challenge is None
                or challenge.purpose != RequesterVerificationChallenge.PURPOSE_INTAKE
                or challenge.consumed_at is None
                or challenge.draft_id != draft_id
                or challenge.request_id is not None
                or challenge.email_key != otp.hash_value((cleaned["email"] or "").strip().lower())
            ):
                raise ValueError(
                    "submit_and_issue_link: verification does not match this draft/email"
                )

        request = submit_request(
            ctx,
            draft_id=draft_id,
            verification_id=verification_id,
            payload=payload,
        )
        if not no_email:
            assert verification_id is not None
            # One-time marker: this verification has now been spent on a real request.
            RequesterVerificationChallenge.objects.filter(pk=verification_id).update(
                request_id=request.id
            )
        drafts.mark_consumed(draft_id, request_id=request.id)
        issued: IssuedLink | None = None
        if not no_email:
            issued = issue_link(
                request_id=request.id,
                kind=RequesterAccessLink.KIND_INITIAL,
                verification_id=verification_id,
            )
            # `issue_link` deliberately never audits itself (its own docstring: "Does not
            # itself audit or email; the caller does") -- this is that caller, same shape as
            # `regenerate_link_for_own_request`'s `@command`-driven "requester_link.regenerated"
            # audit, written by hand here since this whole function is a plain orchestration,
            # not a single `@command` (intake.md §2: it calls two commands in one transaction).
            audit_record(
                ctx=ctx,
                action="requester_link.issued",
                target_type="request",
                target_id=str(request.id),
                project_id=request.id,
                context={"link_id": str(issued.link.id), "kind": RequesterAccessLink.KIND_INITIAL},
            )
    return SubmissionResult(request=request, issued_link=issued)


__all__ = [
    "IntakeSubmissionRateLimited",
    "IssuedLink",
    "RequestLinkFacts",
    "SubmissionResult",
    "current_secure_page_path",
    "find_my_request",
    "issue_link",
    "link_owner_contact",
    "regenerate_link",
    "regenerate_link_for_own_request",
    "register_email_to_request_ids_lookup",
    "register_request_contact_lookup",
    "register_request_facts_lookup",
    "resolve_token",
    "submit_and_issue_link",
]
