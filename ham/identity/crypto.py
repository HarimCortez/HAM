"""Encrypts TOTP secrets at rest (foundation.md §3 MFA: "TOTP secret and recovery codes are
**S**, encrypted at rest ... with `HAM_FIELD_ENCRYPTION_KEY`").

The actual Fernet/MultiFernet cipher lives in `ham.platform.crypto` (moved there so
`ham.integrations.email.service` can reuse the same key/rotation logic for encrypting
background-job payloads, security review C2, without `ham.integrations` importing
`ham.identity` and violating foundation.md §1's layering). This module re-exports it so
existing `from .crypto import encrypt, decrypt` call sites in `ham.identity` are unchanged.
"""

from __future__ import annotations

from ham.platform.crypto import decrypt, encrypt, reset_cache_for_tests

__all__ = ["encrypt", "decrypt", "reset_cache_for_tests"]
