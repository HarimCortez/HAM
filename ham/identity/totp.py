"""TOTP (RFC 6238, built on HOTP RFC 4226) for two-step sign-in (PRD §60.1).

Tech decision (amended, 2026-09-28 — see `docs/adr/0001-stack.md` amendment and Q-085): S3b's
build step 1 implemented RFC 6238 by hand against Python's own `hmac`/`hashlib` rather than
wiring django-allauth's MFA app (`allauth.mfa` drags the separate, legacy top-level `allauth`
app's own `EmailAddress`/`EmailConfirmation` models into Django's unmigrated-app table sync,
breaking test-database creation). That reasoning for *not* using allauth still holds, but a
hand-written HMAC counter loop is exactly the kind of code CLAUDE.md/PRD §3.4-§3.5 want out of
application code: it is real cryptographic-adjacent logic with no independent security review,
just because it happened to be a "few lines of stdlib". This module now uses `pyotp` (a small,
widely used, independently maintained TOTP/HOTP library) for the actual algorithm, while still
not depending on `allauth`/`allauth.mfa` being installed as a Django app. QR codes use `qrcode`
directly (no longer via the `django-allauth[mfa]` extra).

Replay protection (security review H2) lives in `ham.identity.mfa` (`TOTPDevice.last_used_step`,
checked/updated under `select_for_update()`), not here — this module only answers "is `code`
valid for `secret` at counter `X`", it does not know which counters a given device has already
spent.

Uses the injectable `ham.platform.clock` (never `time.time()`/`datetime.now()` directly) so
tests can time-travel deterministically (foundation.md §9).
"""

from __future__ import annotations

from io import BytesIO

import pyotp

from ham.platform.clock import now as clock_now

TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
TOTP_TOLERANCE_STEPS = 1  # accept one adjacent 30s window either side (clock drift)

__all__ = [
    "new_secret",
    "verify_code",
    "provisioning_uri",
    "qr_svg",
    "current_code",
    "current_step",
    "step_for_code",
]


def new_secret(length: int = 32) -> str:
    """`length` is base32 *characters* (pyotp's own unit), not bytes — 32 chars = 160 bits,
    matching the previous hand-rolled implementation's `base32.b32encode(token_bytes(20))`
    (20 bytes = 160 bits = 32 base32 characters)."""
    return pyotp.random_base32(length=length)


def _totp(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD_SECONDS)


def current_step() -> int:
    """The counter ("step") for the current instant, via the injectable Clock."""
    return int(clock_now().timestamp()) // TOTP_PERIOD_SECONDS


def current_code(secret: str) -> str:
    """The code valid right now (dev tooling only — `manage.py dev_totp`, and tests)."""
    return _totp(secret).at(current_step() * TOTP_PERIOD_SECONDS)


def verify_code(secret: str, code: str) -> bool:
    """Whether `code` is valid for `secret` at the current step or one adjacent step.

    Does not check/update replay state — callers that must prevent code reuse (sign-in
    challenge, step-up) use `ham.identity.mfa.verify_totp`, which does. Built on
    `step_for_code` (not `pyotp.TOTP.verify`) so both functions agree on exactly which steps
    count as "now" via the injectable Clock, and to sidestep `verify`'s stub typing a
    Unix-second `for_time` as datetime-only (its runtime behavior accepts either).
    """
    return step_for_code(secret, code) is not None


def step_for_code(secret: str, code: str) -> int | None:
    """The counter step `code` matches (within the tolerance window around now), or `None` if
    it doesn't match at all. Used by `ham.identity.mfa` to enforce replay protection: a step
    at or before the device's `last_used_step` is rejected even though the code itself would
    otherwise still be time-valid."""
    normalized = code.strip().replace(" ", "")
    if not normalized.isdigit() or len(normalized) != TOTP_DIGITS:
        return None
    totp = _totp(secret)
    base_step = current_step()
    for offset in range(-TOTP_TOLERANCE_STEPS, TOTP_TOLERANCE_STEPS + 1):
        step = base_step + offset
        if totp.at(step * TOTP_PERIOD_SECONDS) == normalized:
            return step
    return None


def provisioning_uri(*, secret: str, email: str, issuer: str) -> str:
    return pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD_SECONDS).provisioning_uri(
        name=email, issuer_name=issuer
    )


def qr_svg(uri: str) -> str:
    import qrcode
    from qrcode.image.svg import SvgPathImage

    image = qrcode.make(uri, image_factory=SvgPathImage)
    buf = BytesIO()
    image.save(buf)
    return buf.getvalue().decode("utf-8")
