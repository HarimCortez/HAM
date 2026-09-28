"""Encrypts TOTP secrets at rest (foundation.md §3 MFA: "TOTP secret and recovery codes are
**S**, encrypted at rest through the allauth adapter with `HAM_FIELD_ENCRYPTION_KEY`").

Tech note (S3b): we did not end up wiring django-allauth's `allauth.mfa` Django app (its
enrollment/challenge views and `stages` pipeline assume allauth's own `allauth.account`
login flow, which conflicts with HAM's custom passwordless code+link sign-in — see
`ham/identity/authn.py` module docstring for the full spike note). We do reuse allauth's own
TOTP algorithm implementation (`ham/identity/totp.py`) and, here, the same "encrypt secrets
before they hit the database" requirement, using `cryptography`'s `Fernet` (an established,
audited primitive — this module only composes it; it invents no cryptography of its own).

`HAM_FIELD_ENCRYPTION_KEY` (env var, `config/settings/base.py`) must be a urlsafe-base64
32-byte key (i.e. `Fernet.generate_key()`) in production. In development/test, an unset key
falls back to a key deterministically derived from `SECRET_KEY` purely for developer
convenience — `ham.platform.env.refuse_in_production`-style guard below refuses this
fallback outside development/test.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = getattr(settings, "HAM_FIELD_ENCRYPTION_KEY", "") or ""
    if not key:
        if settings.HAM_ENV == "production":
            raise RuntimeError(
                "HAM_FIELD_ENCRYPTION_KEY must be set in production (foundation.md §3 MFA)."
            )
        # Dev/test convenience only (never reached in production, guarded above): derive a
        # stable key from SECRET_KEY so local runs need no extra env var.
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    key_bytes = key.encode() if isinstance(key, str) else key
    return Fernet(key_bytes)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def reset_cache_for_tests() -> None:
    """Test-only: clears the cached Fernet instance after a settings override."""
    _fernet.cache_clear()
