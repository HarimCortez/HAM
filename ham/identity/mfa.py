"""Two-step sign-in (TOTP + recovery codes), trusted devices, step-up and MFA reset
(PRD §60.1, §59 step-up; foundation.md §3 "MFA", §8 step 8).

Enrollment/challenge/step-up are plain service functions (no `ActorContext` exists yet for the
enrollment/challenge case — the person is mid-sign-in). `reset_mfa` is a full `@command`
because it is one Admin acting on another signed-in person's account (Q-035, Q-044).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass

from django.db import transaction

from ham.audit.services import record as audit_record
from ham.authz.commands import CommandResult, PermissionDenied, command
from ham.authz.context import ActorContext
from ham.integrations.email.service import send_transactional_email
from ham.platform.church import church_profile
from ham.platform.clock import now as clock_now
from ham.rules import RULES

from . import totp
from .crypto import decrypt, encrypt
from .models import RecoveryCode, RoleAssignment, TOTPDevice, TrustedDevice, User

# PRD-GAP Q-072: docs/prd-open-questions.md Q-072 is still open; using the proposed default
# ("5, then restart email sign-in; audited") verbatim, since ham.rules.v1's
# MFA_CODE_MAX_ATTEMPTS is `Pending` (see ham/rules/types.py).
MFA_CODE_MAX_ATTEMPTS = 5

RECOVERY_CODE_COUNT = RULES.auth.MFA_RECOVERY_CODE_COUNT
TRUSTED_DEVICE_COOKIE_NAME = "ham_td"


def mfa_required(user: User) -> bool:
    """Whether `user` holds any role in PRD §60.1's mandatory list (any active role, since
    the check happens before `mfa_satisfied` can even be set)."""
    return RoleAssignment.objects.filter(
        user=user, role__in=RULES.auth.MFA_REQUIRED_ROLES, revoked_at__isnull=True
    ).exists()


def is_enrolled(user: User) -> bool:
    return TOTPDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


# ---------------------------------------------------------------------------------------
# Enrollment (C1-C3)
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class EnrollmentStart:
    secret: str
    provisioning_uri: str
    qr_svg: str


def start_enrollment(user: User) -> EnrollmentStart:
    secret = totp.new_secret()
    church = church_profile()
    uri = totp.provisioning_uri(secret=secret, email=user.email, issuer=f"{church.short_name} HAM")
    return EnrollmentStart(secret=secret, provisioning_uri=uri, qr_svg=totp.qr_svg(uri))


def _hash_code(code: str) -> str:
    normalized = code.strip().lower().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def _generate_recovery_codes() -> list[str]:
    return [
        f"{secrets.token_hex(5)[:5]}-{secrets.token_hex(5)[5:]}" for _ in range(RECOVERY_CODE_COUNT)
    ]


def confirm_enrollment(user: User, *, secret: str, code: str) -> list[str]:
    """Verifies the first code against `secret` and activates two-step sign-in, returning the
    plaintext recovery codes (shown to the person exactly once, docs/ux/auth-and-access.md C3).
    Raises `ValueError` if the code doesn't match."""
    if not totp.verify_code(secret, code):
        raise ValueError("That code didn't match.")
    now = clock_now()
    with transaction.atomic():
        TOTPDevice.objects.update_or_create(
            user=user,
            defaults={"secret_encrypted": encrypt(secret), "created_at": now, "confirmed_at": now},
        )
        RecoveryCode.objects.filter(user=user).delete()
        codes = _generate_recovery_codes()
        RecoveryCode.objects.bulk_create(
            RecoveryCode(user=user, code_hash=_hash_code(c), created_at=now) for c in codes
        )
    audit_record(
        ctx=None,
        actor_type="user",
        actor_user_id=user.id,
        action="auth.mfa.enrolled",
        target_type="user",
        target_id=str(user.id),
    )
    return codes


# ---------------------------------------------------------------------------------------
# Challenge (C4) and recovery codes (E1-E2)
# ---------------------------------------------------------------------------------------
def verify_totp(user: User, code: str) -> bool:
    device = TOTPDevice.objects.filter(user=user, confirmed_at__isnull=False).first()
    if device is None:
        return False
    return totp.verify_code(decrypt(device.secret_encrypted), code)


def verify_recovery_code(user: User, code: str) -> int | None:
    """Marks the code used if it matches an unused one; returns the remaining unused count,
    or `None` if the code didn't match."""
    normalized_hash = _hash_code(code)
    with transaction.atomic():
        row = (
            RecoveryCode.objects.select_for_update()
            .filter(user=user, code_hash=normalized_hash, used_at__isnull=True)
            .first()
        )
        if row is None:
            return None
        row.used_at = clock_now()
        row.save(update_fields=["used_at"])
    audit_record(
        ctx=None,
        actor_type="user",
        actor_user_id=user.id,
        action="auth.mfa.recovery_code_used",
        target_type="user",
        target_id=str(user.id),
    )
    return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


def regenerate_recovery_codes(user: User) -> list[str]:
    now = clock_now()
    with transaction.atomic():
        RecoveryCode.objects.filter(user=user).delete()
        codes = _generate_recovery_codes()
        RecoveryCode.objects.bulk_create(
            RecoveryCode(user=user, code_hash=_hash_code(c), created_at=now) for c in codes
        )
    return codes


def unused_recovery_code_count(user: User) -> int:
    return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


# ---------------------------------------------------------------------------------------
# Trusted devices (Q-010: "Trust this device for 30 days", unchecked by default)
# ---------------------------------------------------------------------------------------
def create_trusted_device(user: User, *, label: str = "") -> tuple[str, dt.datetime]:
    device_id = uuid.uuid4()
    secret = secrets.token_urlsafe(32)
    now = clock_now()
    expires_at = now + RULES.auth.MFA_TRUSTED_DEVICE_LIFETIME
    TrustedDevice.objects.create(
        id=device_id,
        user=user,
        token_hash=hashlib.sha256(secret.encode()).hexdigest(),
        label=label,
        created_at=now,
        expires_at=expires_at,
        last_seen_at=now,
    )
    return f"{device_id}:{secret}", expires_at


def check_trusted_device(user: User, cookie_value: str) -> bool:
    try:
        device_id_raw, secret = cookie_value.split(":", 1)
        device_id = uuid.UUID(device_id_raw)
    except (ValueError, AttributeError):
        return False
    now = clock_now()
    device = TrustedDevice.objects.filter(id=device_id, user=user, expires_at__gt=now).first()
    if device is None:
        return False
    if not secrets.compare_digest(hashlib.sha256(secret.encode()).hexdigest(), device.token_hash):
        return False
    device.last_seen_at = now
    device.save(update_fields=["last_seen_at"])
    return True


def forget_all_trusted_devices(user: User) -> None:
    TrustedDevice.objects.filter(user=user).delete()


def forget_trusted_device(user: User, device_id: uuid.UUID) -> None:
    TrustedDevice.objects.filter(user=user, id=device_id).delete()


# ---------------------------------------------------------------------------------------
# Step-up ("Confirm it's you", D)
# ---------------------------------------------------------------------------------------
def verify_step_up(ctx: ActorContext, *, code: str) -> bool:
    """Real actor only (step-up actions are blocked while impersonating, so `ctx.user_id` is
    always the signed-in person, never an impersonation target, whenever this runs)."""
    assert ctx.user_id is not None  # step-up is only reachable by an authenticated actor
    user = User.objects.get(pk=ctx.user_id)
    ok = verify_totp(user, code)
    if not ok:
        ok = verify_recovery_code(user, code) is not None
    audit_record(
        ctx=ctx,
        action="auth.step_up.succeeded" if ok else "auth.step_up.failed",
        target_type="user",
        target_id=str(ctx.user_id),
    )
    return ok


# ---------------------------------------------------------------------------------------
# Admin reset (E4; Q-035, Q-044) — a full command: another Administrator acting on someone
# else's account, step-up, audited, invalidates trust (foundation.md §3 "resetting MFA
# invalidates it").
# ---------------------------------------------------------------------------------------
@command("user.mfa_reset")
def reset_mfa(
    ctx: ActorContext, *, user_id: uuid.UUID, verification_method: str, note: str = ""
) -> CommandResult:
    if user_id == ctx.user_id:
        raise PermissionDenied("user.mfa_reset: an Administrator cannot reset their own MFA")
    if not verification_method.strip():
        raise ValueError(
            "user.mfa_reset: how the Administrator confirmed the person's identity is required"
        )
    target = User.objects.select_for_update().get(pk=user_id)
    with transaction.atomic():
        TOTPDevice.objects.filter(user=target).delete()
        RecoveryCode.objects.filter(user=target).delete()
        TrustedDevice.objects.filter(user=target).delete()
    church = church_profile()
    send_transactional_email(
        to=target.email,
        subject=f"{church.short_name} HAM: Your two-step sign-in was reset",
        text_body=(
            "Your two-step sign-in was reset by a HAM Administrator. If you didn't ask for "
            f"this, contact {church.email} right away."
        ),
        category="mfa_reset",
    )
    return CommandResult(
        value=target,
        audit_action="auth.mfa.reset",
        target_type="user",
        target_id=str(user_id),
        reason=note,
        context={"verification_method": verification_method},
    )
