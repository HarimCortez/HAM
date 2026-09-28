"""Shared field/payload encryption (`HAM_FIELD_ENCRYPTION_KEY`), used by more than one module
(`ham.identity.crypto` for TOTP secrets/recovery-code-adjacent fields at rest, and
`ham.integrations.email.service` so background-job arguments never carry a plaintext sign-in
code/link/email — security review C2). Lives in `ham.platform` (the bottom layer) so both can
depend on it without `ham.integrations` importing `ham.identity` (foundation.md §1 layering).

`HAM_FIELD_ENCRYPTION_KEY` (env var) must be a urlsafe-base64 32-byte `Fernet.generate_key()`
value in production (validated eagerly at process start, `config/settings/prod.py`). It may be
a comma-separated list (newest key first) to support rotation: `MultiFernet` tries every key
for decryption but only ever encrypts with the first. In development/test, an unset key falls
back to a key deterministically derived from `SECRET_KEY` purely for developer convenience —
refused outside development/test.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


@lru_cache(maxsize=1)
def _cipher() -> MultiFernet:
    raw = getattr(settings, "HAM_FIELD_ENCRYPTION_KEY", "") or ""
    if not raw:
        if settings.HAM_ENV == "production":
            raise RuntimeError(
                "HAM_FIELD_ENCRYPTION_KEY must be set in production (foundation.md §3 MFA)."
            )
        # Dev/test convenience only (never reached in production, guarded above): derive a
        # stable key from SECRET_KEY so local runs need no extra env var.
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        raw = base64.urlsafe_b64encode(digest).decode()
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    return MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in keys])


def encrypt(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _cipher().decrypt(token.encode()).decode()


def reset_cache_for_tests() -> None:
    """Test-only: clears the cached cipher after a settings override."""
    _cipher.cache_clear()
