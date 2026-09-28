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

from ham.authz.commands import CommandResult, OutboxSpec, command
from ham.authz.context import RequesterContext
from ham.platform import otp
from ham.platform.clock import now as clock_now
from ham.platform.crypto import encrypt
from ham.requests.matching import normalize_email

from . import drafts
from .models import RequesterAccessLink
from .validity import fixed_expiry, link_validity, normal_access_ends_at
from .verification import ChallengeRequestResult, request_link_regeneration_code


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
    facts = _facts(link.request_id)
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


def _resource_own_request(ctx: RequesterContext, *args: Any, **kwargs: Any) -> RequesterContext:
    return ctx


@command("requester_link.regenerate", resource_from=_resource_own_request)
def regenerate_link_for_own_request(
    ctx: RequesterContext, *, verification_id: UUID
) -> CommandResult:
    """Called once the requester has re-verified (fresh code/link) while already holding a
    `RequesterContext` for their own request (the common case: an about-to-expire but still
    resolvable link). `ham.requester_portal.services.regenerate_link` below is the public,
    email-driven entry point used when the old link has *already* expired."""
    assert ctx.request_id is not None  # the matrix's OWN_REQUEST scope already guarantees this
    issued = issue_link(
        request_id=ctx.request_id,
        kind=RequesterAccessLink.KIND_REGENERATED,
        verification_id=verification_id,
    )
    return CommandResult(
        value=issued,
        audit_action="requester_link.regenerated",
        target_type="request",
        target_id=str(ctx.request_id),
        project_id=ctx.request_id,
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


def find_my_request(*, email: str, ip_address: str = "") -> ChallengeRequestResult:
    """R11b "Check on your request" (Q-117): one link-only email per matching request; an
    address with no request gets none at all. The HTTP-visible response is identical
    regardless (intake.md §9); only whether/how many emails go out differs."""
    from .antiabuse import HONEYPOT_FIELD_NAME  # noqa: F401 - documents the caller's own check

    normalized = normalize_email(email)
    if normalized is not None:
        for request_id in _requests_for_email(normalized):
            request_link_regeneration_code(
                request_id=request_id,
                email=normalized,
                ip_address=ip_address,
                bypass_cooldown=True,
            )
    return ChallengeRequestResult("sent")


# ---------------------------------------------------------------------------------------
# Orchestration: verify -> submit -> issue link, one transaction (intake.md §2)
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SubmissionResult:
    request: Any  # `ham.requests.models.AssistanceRequest` (S2.2)
    issued_link: IssuedLink | None  # None for a Q-025 no-email (NEEDS_PHONE_CHECK) submission


def submit_and_issue_link(*, draft_id: UUID, verification_id: UUID | None) -> SubmissionResult:
    """intake.md §2: "The portal orchestrates submission: it verifies the draft, calls
    `requests.services.submit_request`, then issues the link, all in one transaction."

    `verification_id` is `None` only for the Q-025 "I don't use email" path (no challenge was
    ever created; `ham.requests.services.submit_request` must accept that and route the
    request to `NEEDS_PHONE_CHECK` — see this slice's handback for the exact coordination note
    with S2.2 on that signature).
    """
    from ham.requests.services import submit_request  # S2.2's `@command`-wrapped service

    ctx = RequesterContext(request_id=None)
    with transaction.atomic():
        # PRD-GAP coordination note (see handback): S2.2's committed `submit_request` stub
        # signature types `verification_id` as required (`UUID`); the Q-025 no-email path has
        # no challenge to reference at all. `type: ignore` until S2.2/the merge relaxes it.
        request = submit_request(
            ctx,
            draft_id=draft_id,
            verification_id=verification_id,  # type: ignore[arg-type]
        )
        drafts.mark_consumed(draft_id, request_id=request.id)
        no_email = getattr(request, "status", "") == "NEEDS_PHONE_CHECK"
        issued: IssuedLink | None = None
        if not no_email:
            issued = issue_link(
                request_id=request.id,
                kind=RequesterAccessLink.KIND_INITIAL,
                verification_id=verification_id,
            )
    return SubmissionResult(request=request, issued_link=issued)


__all__ = [
    "IssuedLink",
    "RequestLinkFacts",
    "SubmissionResult",
    "find_my_request",
    "issue_link",
    "regenerate_link",
    "regenerate_link_for_own_request",
    "register_email_to_request_ids_lookup",
    "register_request_contact_lookup",
    "register_request_facts_lookup",
    "resolve_token",
    "submit_and_issue_link",
]
