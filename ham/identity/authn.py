"""Passwordless sign-in: emailed 6-digit code + one-click link (PRD §60.2, foundation.md §7,
docs/ux/auth-and-access.md §4.A).

Tech/spike note (S3b build step 1): the plan asked us to spike django-allauth's "login by
code" flow (`allauth.account` with `ACCOUNT_LOGIN_METHODS`/email-verification-by-code) plus a
companion one-click link. allauth's login-by-code is built entirely around its own
`allauth.account` login pipeline (`Stage`/`LoginStageController`, its own session keys, its
own templates and its own idea of "pending" login state) and does not have a "send both a
code and a scanner-safe POST link, either one redeems the other" primitive — building that on
top of allauth's stages would mean fighting the pipeline more than using it, and would still
require this same amount of HAM-specific code (challenge storage, rate limiting, the POST-only
Continue page). Per the plan's explicit fallback ("build codes + link in HAM's own small
module using allauth where it helps"), this module is that small HAM module. It reuses:
- `ham.identity.totp`/`ham.identity.crypto` (see their docstrings) for the MFA half;
- `ham.integrations.email.service.send_transactional_email` (foundation.md §1's one documented
  outbox exception) to actually send the emails.

No account enumeration (foundation.md §7): `request_sign_in` runs the same queries and enqueues
an email either way; only the *email body* differs by account state (docs/ux/auth-and-access.md
A6), never the HTTP response from the view.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import login as django_login
from django.db import transaction

from ham.audit.services import record as audit_record
from ham.integrations.email.service import send_transactional_email
from ham.platform.church import church_profile
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from .models import SignInChallenge, User

# PRD-GAP Q-070: proposed default in use; owner may change. The limit and cooldown live in
# ham.rules (RULES.auth.SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR / SIGN_IN_RESEND_COOLDOWN /
# SIGN_IN_REQUESTS_PER_IP_PER_HOUR / SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY).
# "Per hour"/"per day" are part of those rules' own definitions, so the rolling windows are
# fixed here as their units.
_SIGN_IN_RATE_WINDOW = dt.timedelta(hours=1)
_FAILED_ATTEMPT_WINDOW = dt.timedelta(days=1)


def _hash(value: str) -> str:
    """HMAC-SHA256 with a server-side secret (security review L1): a plain unsalted SHA-256
    of a 6-digit code or a random-but-fixed-format link token is fast enough to brute-force
    offline from a leaked `identity_sign_in_challenge` row alone; HMAC with `SECRET_KEY` means
    the secret itself would also have to leak."""
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def _generate_code() -> str:
    digits = RULES.auth.SIGN_IN_CODE_LENGTH
    return "".join(str(secrets.randbelow(10)) for _ in range(digits))


@dataclass(frozen=True, slots=True)
class SignInRequestResult:
    status: str  # "sent" | "cooldown" | "rate_limited"
    retry_at: dt.datetime | None = None


def request_sign_in(*, email: str, next_url: str = "", ip_address: str = "") -> SignInRequestResult:
    """Always looks and behaves the same whether or not `email` has an account.

    Security review M3: `ip_address` (best-effort; the view supplies it, this module never
    inspects request internals) throttles independently of the per-address limit, so one
    visitor can't route around the address limit by trying many addresses.
    """
    email = email.strip().lower()
    now = clock_now()

    last = SignInChallenge.objects.filter(email=email).order_by("-created_at").first()
    cooldown = RULES.auth.SIGN_IN_RESEND_COOLDOWN
    if last is not None and now - last.created_at < cooldown:
        return SignInRequestResult("cooldown", last.created_at + cooldown)

    window_start = now - _SIGN_IN_RATE_WINDOW
    recent_count = SignInChallenge.objects.filter(email=email, created_at__gte=window_start).count()
    if recent_count >= RULES.auth.SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR:
        return SignInRequestResult("rate_limited", window_start + _SIGN_IN_RATE_WINDOW)

    if ip_address:
        recent_from_ip = SignInChallenge.objects.filter(
            ip_address=ip_address, created_at__gte=window_start
        ).count()
        if recent_from_ip >= RULES.auth.SIGN_IN_REQUESTS_PER_IP_PER_HOUR:
            return SignInRequestResult("rate_limited", window_start + _SIGN_IN_RATE_WINDOW)

    code = _generate_code()
    link_token = secrets.token_urlsafe(32)
    SignInChallenge.objects.create(
        email=email,
        code_hash=_hash(code),
        link_token_hash=_hash(link_token),
        created_at=now,
        expires_at=now + RULES.auth.SIGN_IN_CODE_LIFETIME,
        next_url=next_url,
        ip_address=ip_address or None,
    )

    user = User.objects.filter(email=email).first()
    church = church_profile()
    minutes = int(RULES.auth.SIGN_IN_CODE_LIFETIME.total_seconds() // 60)
    formatted_code = f"{code[:3]} {code[3:]}" if len(code) == 6 else code
    if user is not None and user.is_active and not user.is_disabled:
        text = (
            f"Your code is {formatted_code}. Or use the link below.\n\n"
            f"{_sign_in_link_url(link_token)}\n\n"
            f"It works once, for {minutes} minutes. Signing in on another device? Type the "
            "code there instead. Didn't ask for this? You can ignore this email; no one can "
            "sign in without it."
        )
        subject = "Your HAM sign-in link"
    elif user is not None:
        text = (
            f"Your HAM account is turned off, so we can't sign you in. If you think that's a "
            f"mistake, contact {church.email}."
        )
        subject = "About your HAM sign-in"
    else:
        text = (
            "Someone tried to sign in to HAM with this email address, but there's no HAM "
            f"account for it. If you'd like to volunteer, ask a HAM leader to invite you, or "
            f"reply to {church.email}. If it wasn't you, you can ignore this email."
        )
        subject = "About your HAM sign-in"
    send_transactional_email(
        to=email,
        subject=f"{church.short_name} HAM: {subject}",
        text_body=text,
        category="sign_in_code",
    )
    return SignInRequestResult("sent")


def _sign_in_link_url(token: str) -> str:
    # PRD-guardian review B2: the emailed link must be a full, absolute URL (a relative path
    # is meaningless in an email client) — built from `HAM_BASE_URL` (env, `config/settings/
    # base.py`), never guessed from the current request (this runs from a background job with
    # no request in scope).
    from django.urls import reverse

    path = reverse("web:sign_in_link", kwargs={"token": token})
    return f"{settings.HAM_BASE_URL}{path}"


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    reason: str = ""  # "expired" | "wrong" | "locked" | "no_challenge"
    attempts_left: int = 0
    email: str = ""
    next_url: str = ""


def _consume(challenge: SignInChallenge) -> VerifyResult:
    challenge.consumed_at = clock_now()
    challenge.save(update_fields=["consumed_at"])
    return VerifyResult(ok=True, email=challenge.email, next_url=challenge.next_url)


def _record_lockout(challenge: SignInChallenge) -> None:
    audit_record(
        ctx=None,
        actor_type="system",
        actor_user_id=None,
        action="auth.sign_in.locked",
        target_type="sign_in_challenge",
        target_id=str(challenge.id),
    )


def _recent_failed_attempts(email: str, *, now: dt.datetime) -> int:
    """Security review M3: total wrong-code attempts across *every* challenge for `email` in
    the last 24 hours — a fresh challenge (e.g. from Resend) resets its own `attempts` column,
    so without this a person could keep asking for new codes to keep guessing indefinitely."""
    window_start = now - _FAILED_ATTEMPT_WINDOW
    total = SignInChallenge.objects.filter(email=email, created_at__gte=window_start).aggregate(
        total=_models_sum("attempts")
    )["total"]
    return total or 0


def _models_sum(field: str):
    from django.db.models import Sum

    return Sum(field)


def verify_code(*, email: str, code: str) -> VerifyResult:
    email = email.strip().lower()
    now = clock_now()

    daily_cap = RULES.auth.SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY
    if _recent_failed_attempts(email, now=now) >= daily_cap:
        return VerifyResult(ok=False, reason="locked")

    # Security review M2: two concurrent guesses against the same challenge must not both
    # read `attempts` before either write lands (a race that could let more than
    # `SIGN_IN_CODE_MAX_ATTEMPTS` guesses through). `select_for_update()` serializes them.
    with transaction.atomic():
        challenge = (
            SignInChallenge.objects.select_for_update()
            .filter(email=email, consumed_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if challenge is None:
            return VerifyResult(ok=False, reason="no_challenge")
        if now > challenge.expires_at:
            return VerifyResult(ok=False, reason="expired")
        max_attempts = RULES.auth.SIGN_IN_CODE_MAX_ATTEMPTS
        if challenge.attempts >= max_attempts:
            return VerifyResult(ok=False, reason="locked")

        normalized = code.strip().replace(" ", "").replace("-", "")
        if not secrets.compare_digest(_hash(normalized), challenge.code_hash):
            challenge.attempts += 1
            challenge.save(update_fields=["attempts"])
            if challenge.attempts >= max_attempts:
                _record_lockout(challenge)
                return VerifyResult(ok=False, reason="locked")
            return VerifyResult(
                ok=False, reason="wrong", attempts_left=max_attempts - challenge.attempts
            )

        return _consume(challenge)


def consume_link(*, token: str) -> VerifyResult:
    """POST-only (docs/ux/auth-and-access.md A1: "a Continue page with a POST button, so
    email link scanners can't use it up" — the GET view only *displays* the Continue page and
    never calls this)."""
    token_hash = _hash(token)
    # Security review M2: `select_for_update()` so two concurrent POSTs of the same link can't
    # both observe `consumed_at IS NULL` before either writes it (the credential is meant to
    # be single-use even under a race).
    with transaction.atomic():
        challenge = (
            SignInChallenge.objects.select_for_update()
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
    """GET-safe check for the Continue page (never consumes)."""
    token_hash = _hash(token)
    now = clock_now()
    return SignInChallenge.objects.filter(
        link_token_hash=token_hash, consumed_at__isnull=True, expires_at__gt=now
    ).exists()


from ham import jobs as _jobs  # noqa: E402 - kept near the job it defines, not the top imports


@_jobs.periodic_job(name="identity.purge_sign_in_challenges", cron="0 * * * *")
def purge_expired_sign_in_challenges(timestamp: int) -> int:
    """Security review L5: `identity_sign_in_challenge` rows are rate-limit/lockout
    bookkeeping, not a record worth keeping — deletes rows older than
    `RULES.auth.SIGN_IN_CHALLENGE_RETENTION`. Runs hourly via `ham.jobs.periodic_job`
    (the worker itself defers this on schedule; no separate cron process needed)."""
    cutoff = clock_now() - RULES.auth.SIGN_IN_CHALLENGE_RETENTION
    deleted, _ = SignInChallenge.objects.filter(created_at__lt=cutoff).delete()
    return deleted


def complete_sign_in(request, *, user: User) -> None:
    """Finish signing `user` in on `request` (foundation.md §3 "Invited -> Active (first
    sign-in)"). Call only after every required factor (email + MFA, if any) has passed."""
    now = clock_now()
    first_sign_in = user.first_sign_in_at is None
    user.last_sign_in_at = now
    update_fields = ["last_sign_in_at"]
    if first_sign_in:
        user.first_sign_in_at = now
        update_fields.append("first_sign_in_at")
    user.save(update_fields=update_fields)

    user.backend = "django.contrib.auth.backends.ModelBackend"  # type: ignore[attr-defined]
    django_login(request, user)
    request.session["ham_session_started_at"] = now.isoformat()
    request.session["ham_last_activity"] = now.isoformat()
    # Security review H3: captured once, at sign-in, so `ham.identity.middleware` can compare
    # it to the user's *current* `session_epoch` on every later request and force a fresh
    # sign-in the moment an Administrator resets/replaces this session's MFA, or the person
    # uses "Sign out everywhere" (UX M8) from some other browser.
    request.session["ham_session_epoch"] = user.session_epoch

    audit_record(
        ctx=None,
        actor_type="user",
        actor_user_id=user.id,
        action="auth.sign_in.succeeded",
        target_type="user",
        target_id=str(user.id),
        after={"first_sign_in": first_sign_in},
    )
