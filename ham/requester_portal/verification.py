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


def _code_email_text(*, code: str, link_url: str, church) -> tuple[str, str]:
    minutes = int(RULES.intake.REQUESTER_CODE_LIFETIME.total_seconds() // 60)
    formatted = f"{code[:3]} {code[3:]}" if len(code) == 6 else code
    subject = f"{church.short_name} HAM: Confirm your request"  # Q-102: neutral subject
    text = (
        f"Your code is {formatted}. Or use the button below.\n\n{link_url}\n\n"
        f"It works once, for {minutes} minutes. Your answers are saved. If you didn't ask "
        "for this, you can ignore this email."
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

    if not bypass_cooldown:
        last = (
            RequesterVerificationChallenge.objects.filter(email_key=email_key, purpose=purpose)
            .order_by("-created_at")
            .first()
        )
        cooldown = RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN
        if last is not None and now - last.created_at < cooldown:
            return ChallengeRequestResult("cooldown", retry_at=last.created_at + cooldown)

    window_start = now - dt.timedelta(hours=1)
    recent = RequesterVerificationChallenge.objects.filter(
        email_key=email_key, created_at__gte=window_start
    ).count()
    if recent >= RULES.intake.REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR:
        return ChallengeRequestResult("rate_limited", retry_at=window_start + dt.timedelta(hours=1))

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
        code=code, link_url=_confirm_url(link_token, purpose=purpose), church=church_profile()
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


def _recent_failed_attempts(email_key: str, purpose: str, *, now: dt.datetime) -> int:
    from django.db.models import Sum

    window_start = now - _FAILED_ATTEMPT_WINDOW
    total = RequesterVerificationChallenge.objects.filter(
        email_key=email_key, purpose=purpose, created_at__gte=window_start
    ).aggregate(total=Sum("failed_attempts"))["total"]
    return total or 0


def verify_code(*, purpose: str, email: str, code: str) -> VerifyResult:
    email_key = _email_key(email)
    now = clock_now()

    daily_cap = RULES.intake.REQUESTER_CODE_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY
    if _recent_failed_attempts(email_key, purpose, now=now) >= daily_cap:
        return VerifyResult(ok=False, reason="locked")

    with transaction.atomic():
        challenge = (
            RequesterVerificationChallenge.objects.select_for_update()
            .filter(email_key=email_key, purpose=purpose, consumed_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if challenge is None:
            return VerifyResult(ok=False, reason="no_challenge")
        if now > challenge.expires_at:
            return VerifyResult(ok=False, reason="expired")
        max_attempts = RULES.intake.REQUESTER_CODE_MAX_ATTEMPTS
        if challenge.failed_attempts >= max_attempts:
            return VerifyResult(ok=False, reason="locked")

        normalized = code.strip().replace(" ", "").replace("-", "")
        if not otp.hash_matches(normalized, challenge.code_hash):
            challenge.failed_attempts += 1
            challenge.save(update_fields=["failed_attempts"])
            if challenge.failed_attempts >= max_attempts:
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


def link_is_valid(*, token: str) -> bool:
    token_hash = otp.hash_value(token)
    now = clock_now()
    return RequesterVerificationChallenge.objects.filter(
        link_token_hash=token_hash, consumed_at__isnull=True, expires_at__gt=now
    ).exists()


__all__ = [
    "ChallengeRequestResult",
    "VerifyResult",
    "consume_link",
    "link_is_valid",
    "request_intake_verification",
    "request_link_regeneration_code",
    "verify_code",
]
