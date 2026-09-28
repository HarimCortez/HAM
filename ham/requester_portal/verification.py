"""Requester email verification (PRD §7.1; Q-100, Q-121). Emailed 6-digit code + a
scanner-safe one-click link — the same shape and rules as `ham.identity.authn`'s staff
sign-in challenge, reusing `ham.platform.otp` for hashing/generation and
`RULES.intake.REQUESTER_CODE_*` for its limits (intake.md §8: requester codes deliberately
have their own rule names, so tightening staff sign-in later never silently changes what an
older requester has to cope with).

Two purposes, same challenge shape (`RequesterVerificationChallenge.purpose`):
- ``"intake"``: verifies a draft before ``request.submit`` (Q-100) — keyed to ``draft_id``.
- ``"link_regeneration"``: verifies before a new access link is issued for an existing,
  already-submitted request (Q-116/Q-117) — keyed to ``request_id``.

No account enumeration (intake.md §9): callers of `request_link_regeneration_code` /
`find_my_request` always get the same response regardless of whether the address matches
anything; only the *content* of what gets emailed differs, never the HTTP-visible outcome.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.db import transaction

from ham.integrations.email.service import send_transactional_email
from ham.platform import otp
from ham.platform.church import church_profile
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from .models import RequesterVerificationChallenge

_FAILED_ATTEMPT_WINDOW = dt.timedelta(days=1)


def _email_key(email: str) -> str:
    return otp.hash_value(email.strip().lower())


def _code_email_text(*, code: str, link_url: str, church, purpose: str) -> tuple[str, str]:
    """Usability re-check M6: the intake wording ("your answers are saved", "to send your
    request") only fits the *first* code the person ever sees -- a new-link/regeneration code
    (R11a, "my link expired") is never about sending anything, so it gets its own, neutral
    wording instead ("open your request page")."""
    minutes = int(RULES.intake.REQUESTER_CODE_LIFETIME.total_seconds() // 60)
    formatted = f"{code[:3]} {code[3:]}" if len(code) == 6 else code
    # UX minor: the email is plain text -- no button exists, just this link -- so "use the
    # button below" was never accurate. "Or open this link" describes what's actually there.
    if purpose == RequesterVerificationChallenge.PURPOSE_INTAKE:
        subject = f"{church.short_name} HAM: Confirm your request"  # Q-102: neutral subject
        text = (
            f"Your code is {formatted}. Or open this link:\n\n{link_url}\n\n"
            f"It works once, for {minutes} minutes. Your answers are saved. If you didn't ask "
            "for this, you can ignore this email."
        )
    else:
        subject = f"{church.short_name} HAM code"  # Q-102: neutral subject
        text = (
            f"Your code is {formatted}. Use it to open your request page, or open this "
            f"link:\n\n{link_url}\n\n"
            f"It works once, for {minutes} minutes. If you didn't ask for this, you can "
            "ignore this email."
        )
    return subject, text


# intake.md §7's route table (literal paths, not `reverse()`): the public routes these codes/
# links point at are S2.7's to build (`ham/web/urls_requester.py`, still an empty stub as of
# this slice) — S2.7 must add exactly these paths (see this slice's handback / intake-
# contracts.md "S2.3"), so hard-coding them here (rather than a URL name that doesn't exist
# yet) keeps this module usable/testable before that lands, same as `ham.identity.authn`
# hard-codes nothing only because its sign-in routes already exist.
_CONFIRM_PATH_TEMPLATES: dict[str, str] = {
    RequesterVerificationChallenge.PURPOSE_INTAKE: "/request-help/verify/link/{token}",
    RequesterVerificationChallenge.PURPOSE_LINK_REGENERATION: "/request-help/new-link/{token}",
    # FIX-G NM1: "find" reuses the exact same click-through route as link regeneration -- the
    # route itself never branches on `purpose` (`ham.web.views_requester.
    # request_help_new_link`), only the rate-limit budgets and the wording of the first,
    # unverified email differ (`request_find_verification` below).
    RequesterVerificationChallenge.PURPOSE_FIND: "/request-help/new-link/{token}",
}


def _confirm_url(token: str, *, purpose: str) -> str:
    path = _CONFIRM_PATH_TEMPLATES[purpose].format(token=token)
    return f"{settings.HAM_BASE_URL}{path}"


@dataclass(frozen=True, slots=True)
class ChallengeRequestResult:
    status: str  # "sent" | "cooldown" | "rate_limited"
    challenge_id: UUID | None = None
    retry_at: dt.datetime | None = None


def request_intake_verification(
    *, draft_id: UUID, email: str, ip_address: str = ""
) -> ChallengeRequestResult:
    """Send (or refuse to send, silently, per the rate limit) a code+link for an intake
    draft. Only ever called after `ham.requester_portal.forms.validate_intake_payload`
    succeeded with a real email (never for the Q-025 "I don't use email" path, which has no
    challenge at all)."""
    return _request(
        purpose=RequesterVerificationChallenge.PURPOSE_INTAKE,
        draft_id=draft_id,
        request_id=None,
        email=email,
        ip_address=ip_address,
    )


def request_link_regeneration_code(
    *, request_id: UUID, email: str, ip_address: str = "", bypass_cooldown: bool = False
) -> ChallengeRequestResult:
    """Q-116/Q-117: verify before issuing a new link. Caller must already know the email *on
    file* for this request (never taken from user input here) — see
    `ham.requester_portal.services.regenerate_link`.

    ``bypass_cooldown``: `ham.requester_portal.services.find_my_request` calls this once per
    *matching request* for the same address in one go (Q-117 "one email per matching
    request") — the per-address resend cooldown exists to stop repeated re-sends for the
    *same* request, not to cap how many different requests one "Check on your request" can
    surface at once. The hourly per-address cap (`REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR`)
    still applies either way."""
    return _request(
        purpose=RequesterVerificationChallenge.PURPOSE_LINK_REGENERATION,
        draft_id=None,
        request_id=request_id,
        email=email,
        ip_address=ip_address,
        bypass_cooldown=bypass_cooldown,
    )


def request_find_verification(
    *, request_id: UUID, email: str, ip_address: str = "", display_number: str = ""
) -> ChallengeRequestResult:
    """FIX-G NM1/PRD NEW-2: "Check on your request" (R11b) verification. Sends a one-time
    link only (no code entry UI exists for R11b) that lands on the exact same click-through
    route as link regeneration (`/request-help/new-link/<token>`) -- clicking it, then
    confirming, is what actually issues a fresh link and revokes the old one
    (`ham.web.views_requester.request_help_new_link` -> `regenerate_link_for_own_request`,
    which already records `verification_method="email_link"` and a `RequestContactVerification`
    row). This function itself never issues or reveals a live link, unlike the old
    `_issue_and_notify_found_link` it replaces.

    Its own purpose (`PURPOSE_FIND`) keeps its rate-limit budgets independent of R11a's "my
    link expired" resends: at most one email per *request* per
    `RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN`, and at most
    `RULES.intake.FIND_REQUEST_EMAILS_PER_ADDRESS_PER_DAY` per *address* per rolling 24 hours.
    Callers (`ham.requester_portal.services.find_my_request`) must render the same response
    regardless of status (intake.md §9 "no enumeration")."""
    email = email.strip().lower()
    email_key = _email_key(email)
    now = clock_now()
    purpose = RequesterVerificationChallenge.PURPOSE_FIND

    cooldown = RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN
    last_for_request = (
        RequesterVerificationChallenge.objects.filter(request_id=request_id, purpose=purpose)
        .order_by("-created_at")
        .first()
    )
    if last_for_request is not None and now - last_for_request.created_at < cooldown:
        return ChallengeRequestResult("cooldown", retry_at=last_for_request.created_at + cooldown)

    day_start = now - dt.timedelta(hours=24)
    recent_for_address = RequesterVerificationChallenge.objects.filter(
        email_key=email_key, purpose=purpose, created_at__gte=day_start
    ).count()
    if recent_for_address >= RULES.intake.FIND_REQUEST_EMAILS_PER_ADDRESS_PER_DAY:
        return ChallengeRequestResult("rate_limited", retry_at=day_start + dt.timedelta(hours=24))

    code = otp.generate_code(RULES.intake.REQUESTER_CODE_LENGTH)
    link_token = otp.generate_token()
    challenge = RequesterVerificationChallenge.objects.create(
        purpose=purpose,
        request_id=request_id,
        email_key=email_key,
        code_hash=otp.hash_value(code),
        link_token_hash=otp.hash_value(link_token),
        created_at=now,
        expires_at=now + RULES.intake.REQUESTER_CODE_LIFETIME,
        ip_address=ip_address or None,
    )
    minutes = int(RULES.intake.REQUESTER_CODE_LIFETIME.total_seconds() // 60)
    link_url = _confirm_url(link_token, purpose=purpose)
    subject = f"Your {display_number}" if display_number else "Your HAM request"
    text = (
        f"Open my request page: {link_url}\n\n"
        f"It works once, for {minutes} minutes. If you didn't ask for this, you can ignore "
        "this email."
    )
    send_transactional_email(
        to=email, subject=subject, text_body=text, category="requester_found_link"
    )
    return ChallengeRequestResult("sent", challenge_id=challenge.id)


def _request(
    *,
    purpose: str,
    draft_id: UUID | None,
    request_id: UUID | None,
    email: str,
    ip_address: str,
    bypass_cooldown: bool = False,
) -> ChallengeRequestResult:
    email = email.strip().lower()
    email_key = _email_key(email)
    now = clock_now()

    # H2: every budget below is scoped to THIS purpose only (never shared across "intake" and
    # "link_regeneration") -- a shared counter let someone run several "Check on your
    # request"/regeneration sends for an address that DOES have a request (incrementing a
    # purpose-blind counter), then try the *intake* form with the same address and observe a
    # distinctly different ("too many codes") outcome only when a request existed. Splitting
    # the counters by purpose closes that oracle regardless of what the caller does with the
    # result (see the second half of this fix, below).
    # FIX-G Low: for the intake purpose (the only one with a `draft_id`), both the cooldown and
    # the hourly per-address cap are additionally scoped to THIS draft -- otherwise anyone
    # could type a victim's real email into a draft *they* control and burn the victim's own
    # cooldown/hourly budget (both are keyed by `email_key` alone), blocking the victim's own
    # "resend code" for up to an hour. Link regeneration/find (`draft_id is None`) are
    # unaffected -- those purposes are already scoped by `request_id`, not a browser-supplied
    # draft anyone can create at will.
    if not bypass_cooldown:
        last_qs = RequesterVerificationChallenge.objects.filter(
            email_key=email_key, purpose=purpose
        )
        if draft_id is not None:
            last_qs = last_qs.filter(draft_id=draft_id)
        last = last_qs.order_by("-created_at").first()
        cooldown = RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN
        if last is not None and now - last.created_at < cooldown:
            return ChallengeRequestResult("cooldown", retry_at=last.created_at + cooldown)

    window_start = now - dt.timedelta(hours=1)
    recent_qs = RequesterVerificationChallenge.objects.filter(
        email_key=email_key, purpose=purpose, created_at__gte=window_start
    )
    if draft_id is not None:
        recent_qs = recent_qs.filter(draft_id=draft_id)
    recent = recent_qs.count()
    if recent >= RULES.intake.REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR:
        return ChallengeRequestResult("rate_limited", retry_at=window_start + dt.timedelta(hours=1))

    # M1: a per-internet-address cap alongside the per-email one above -- one address mashing
    # "resend" against many different made-up email addresses would otherwise never trip the
    # per-email cap at all. Also purpose-scoped, for the same H2 reason as above.
    if ip_address:
        recent_from_ip = RequesterVerificationChallenge.objects.filter(
            ip_address=ip_address, purpose=purpose, created_at__gte=window_start
        ).count()
        if recent_from_ip >= RULES.intake.REQUESTER_CODE_EMAILS_PER_IP_PER_HOUR:
            return ChallengeRequestResult(
                "rate_limited", retry_at=window_start + dt.timedelta(hours=1)
            )

    code = otp.generate_code(RULES.intake.REQUESTER_CODE_LENGTH)
    link_token = otp.generate_token()
    challenge = RequesterVerificationChallenge.objects.create(
        purpose=purpose,
        draft_id=draft_id,
        request_id=request_id,
        email_key=email_key,
        code_hash=otp.hash_value(code),
        link_token_hash=otp.hash_value(link_token),
        created_at=now,
        expires_at=now + RULES.intake.REQUESTER_CODE_LIFETIME,
        ip_address=ip_address or None,
    )
    subject, text = _code_email_text(
        code=code,
        link_url=_confirm_url(link_token, purpose=purpose),
        church=church_profile(),
        purpose=purpose,
    )
    send_transactional_email(to=email, subject=subject, text_body=text, category="requester_code")
    return ChallengeRequestResult("sent", challenge_id=challenge.id)


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    reason: str = ""  # "expired" | "wrong" | "locked" | "no_challenge"
    attempts_left: int = 0
    challenge: RequesterVerificationChallenge | None = None


def _consume(challenge: RequesterVerificationChallenge) -> VerifyResult:
    challenge.consumed_at = clock_now()
    challenge.save(update_fields=["consumed_at"])
    return VerifyResult(ok=True, challenge=challenge)


def _recent_failed_attempts(
    *,
    purpose: str,
    draft_id: UUID | None,
    request_id: UUID | None,
    ip_address: str,
    now: dt.datetime,
) -> int:
    """L6: scoped to the draft (or request, for link regeneration) plus IP -- never to the
    bare email address, which anyone can type into a draft they control without proving they
    own it. A shared per-address counter let an attacker lock a real person's address out of
    intake for a day just by guessing wrong codes against their own drafts."""
    from django.db.models import Sum

    window_start = now - _FAILED_ATTEMPT_WINDOW
    qs = RequesterVerificationChallenge.objects.filter(
        purpose=purpose, created_at__gte=window_start
    )
    qs = qs.filter(draft_id=draft_id) if draft_id is not None else qs.filter(request_id=request_id)
    if ip_address:
        qs = qs.filter(ip_address=ip_address)
    total = qs.aggregate(total=Sum("failed_attempts"))["total"]
    return total or 0


def _audit_locked(
    *, purpose: str, draft_id: UUID | None, request_id: UUID | None, reason: str
) -> None:
    """M6/N13: `requester_verification.locked` was declared in the audit label table (S2.0)
    but never actually written. No email/address anywhere in the event -- the target is the
    draft/request id (non-PII UUIDs), never `email_key` (an HMAC digest is still "no address"
    per M6, but the draft/request id is more useful and equally address-free)."""
    from ham.audit.models import ACTOR_TYPE_SYSTEM
    from ham.audit.services import record as audit_record

    target_id = str(draft_id) if draft_id is not None else str(request_id)
    audit_record(
        ctx=None,
        actor_type=ACTOR_TYPE_SYSTEM,
        action="requester_verification.locked",
        target_type="intake_draft" if draft_id is not None else "request",
        target_id=target_id,
        project_id=request_id,
        context={"purpose": purpose, "reason": reason},
    )


def verify_code(
    *,
    purpose: str,
    email: str,
    code: str,
    draft_id: UUID | None = None,
    request_id: UUID | None = None,
    ip_address: str = "",
) -> VerifyResult:
    """N3 fix: the challenge is selected by ``draft_id`` (intake) or ``request_id`` (link
    regeneration), never by ``email`` alone. Selecting by email only let an attacker type a
    victim's real email into their *own* draft/session, burn the victim's real challenge's
    wrong-attempt budget (the most-recent challenge for that email was always the victim's --
    a cooldown blocks a second one from being sent for the same address+purpose), and lock
    the victim out of their own, correct code -- the PoC this closes
    (``test_poc_cross_draft.py``, `docs/ux/reviews/step2-privacy-security.md`)."""
    email_key = _email_key(email)
    now = clock_now()

    if draft_id is None and request_id is None:
        return VerifyResult(ok=False, reason="no_challenge")

    daily_cap = RULES.intake.REQUESTER_CODE_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY
    recent = _recent_failed_attempts(
        purpose=purpose,
        draft_id=draft_id,
        request_id=request_id,
        ip_address=ip_address,
        now=now,
    )
    if recent >= daily_cap:
        _audit_locked(purpose=purpose, draft_id=draft_id, request_id=request_id, reason="daily_cap")
        return VerifyResult(ok=False, reason="locked")

    with transaction.atomic():
        qs = RequesterVerificationChallenge.objects.select_for_update().filter(
            purpose=purpose, consumed_at__isnull=True, email_key=email_key
        )
        qs = (
            qs.filter(draft_id=draft_id)
            if draft_id is not None
            else qs.filter(request_id=request_id)
        )
        challenge = qs.order_by("-created_at").first()
        if challenge is None:
            return VerifyResult(ok=False, reason="no_challenge")
        if now > challenge.expires_at:
            return VerifyResult(ok=False, reason="expired")
        max_attempts = RULES.intake.REQUESTER_CODE_MAX_ATTEMPTS
        if challenge.failed_attempts >= max_attempts:
            _audit_locked(
                purpose=purpose,
                draft_id=challenge.draft_id,
                request_id=challenge.request_id,
                reason="max_attempts",
            )
            return VerifyResult(ok=False, reason="locked")

        normalized = code.strip().replace(" ", "").replace("-", "")
        if not otp.hash_matches(normalized, challenge.code_hash):
            challenge.failed_attempts += 1
            challenge.save(update_fields=["failed_attempts"])
            if challenge.failed_attempts >= max_attempts:
                _audit_locked(
                    purpose=purpose,
                    draft_id=challenge.draft_id,
                    request_id=challenge.request_id,
                    reason="max_attempts",
                )
                return VerifyResult(ok=False, reason="locked")
            return VerifyResult(
                ok=False, reason="wrong", attempts_left=max_attempts - challenge.failed_attempts
            )
        return _consume(challenge)


def consume_link(*, token: str) -> VerifyResult:
    """POST-only (docs/ux/auth-and-access.md A1 pattern): the GET view only shows the Continue
    button; this consumes."""
    token_hash = otp.hash_value(token)
    with transaction.atomic():
        challenge = (
            RequesterVerificationChallenge.objects.select_for_update()
            .filter(link_token_hash=token_hash, consumed_at__isnull=True)
            .first()
        )
        if challenge is None:
            return VerifyResult(ok=False, reason="no_challenge")
        now = clock_now()
        if now > challenge.expires_at:
            return VerifyResult(ok=False, reason="expired")
        return _consume(challenge)


def challenge_for_link_token(token: str) -> RequesterVerificationChallenge | None:
    """M8: looks up the challenge a link token belongs to regardless of whether it has
    already been consumed -- used only to detect "this link/draft was already turned into a
    request" (`ham.web.views_requester`'s already-received handling), never to grant access
    on its own (the token hash is still the only credential; an unknown token yields
    `None` exactly like every other lookup here)."""
    token_hash = otp.hash_value(token)
    return RequesterVerificationChallenge.objects.filter(link_token_hash=token_hash).first()


def link_is_valid(*, token: str) -> bool:
    token_hash = otp.hash_value(token)
    now = clock_now()
    return RequesterVerificationChallenge.objects.filter(
        link_token_hash=token_hash, consumed_at__isnull=True, expires_at__gt=now
    ).exists()


__all__ = [
    "ChallengeRequestResult",
    "VerifyResult",
    "challenge_for_link_token",
    "consume_link",
    "link_is_valid",
    "request_find_verification",
    "request_intake_verification",
    "request_link_regeneration_code",
    "verify_code",
]
