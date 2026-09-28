"""TOTP (RFC 6238, built on HOTP RFC 4226) for two-step sign-in (PRD §60.1).

Tech note (S3b build step 1, see `ham/identity/authn.py`'s module docstring for the fuller
spike write-up): we tried reusing `allauth.mfa.totp.internal.auth`'s algorithm functions
directly, but importing that module requires `"allauth.mfa"` in `INSTALLED_APPS`, and doing so
also (surprisingly) drags the *separate*, legacy top-level `allauth` app's own `EmailAddress`/
`EmailConfirmation` models into Django's unmigrated-app table sync — those have nothing to do
with HAM and broke test-database creation (a FK to `identity_user` created before HAM's own
migrations run). Rather than fight that, this module implements the algorithm directly: RFC
6238 is a simple, standard, publicly specified construction (a counter-based HMAC, RFC 4226,
where the counter is time // 30s) — this composes Python's own audited `hmac`/`hashlib`, it
does not invent any cryptographic primitive. QR codes still use `qrcode` (a
`django-allauth[mfa]` transitive dependency already in `pyproject.toml`, importable without
`allauth` being an installed app).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from io import BytesIO
from urllib.parse import quote, urlencode

TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
TOTP_TOLERANCE_STEPS = 1  # accept one adjacent 30s window either side (clock drift)

__all__ = ["new_secret", "verify_code", "provisioning_uri", "qr_svg", "current_code"]


def new_secret(length: int = 20) -> str:
    return base64.b32encode(secrets.token_bytes(length)).decode("ascii")


def _hotp(secret: str, counter: int) -> str:
    key = base64.b32decode(secret.encode("ascii"), casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = bytearray(digest[offset : offset + 4])
    truncated[0] &= 0x7F
    value = struct.unpack(">I", bytes(truncated))[0] % (10**TOTP_DIGITS)
    return f"{value:0{TOTP_DIGITS}d}"


def current_code(secret: str) -> str:
    """The code valid right now (dev tooling only — `manage.py dev_totp`)."""
    return _hotp(secret, int(time.time()) // TOTP_PERIOD_SECONDS)


def verify_code(secret: str, code: str) -> bool:
    normalized = code.strip().replace(" ", "")
    if not normalized.isdigit():
        return False
    counter = int(time.time()) // TOTP_PERIOD_SECONDS
    for step in range(-TOTP_TOLERANCE_STEPS, TOTP_TOLERANCE_STEPS + 1):
        if secrets.compare_digest(normalized, _hotp(secret, counter + step)):
            return True
    return False


def provisioning_uri(*, secret: str, email: str, issuer: str) -> str:
    label = quote(f"{issuer}:{email}")
    params = urlencode({"secret": secret, "issuer": issuer})
    return f"otpauth://totp/{label}?{params}"


def qr_svg(uri: str) -> str:
    import qrcode
    from qrcode.image.svg import SvgPathImage

    image = qrcode.make(uri, image_factory=SvgPathImage)
    buf = BytesIO()
    image.save(buf)
    return buf.getvalue().decode("utf-8")
