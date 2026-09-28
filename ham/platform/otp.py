"""Shared one-time-code/token helpers: HMAC hashing and cryptographically random code/token
generation (foundation.md §1 bottom layer; moved out of ``ham.identity.authn`` in S2.0 so
``ham.requester_portal``'s own email-code verification (PRD §7.1, intake.md §3
``RequesterVerificationChallenge``) can reuse the exact same, already-reviewed construction
without a domain module importing another domain module — ``ham.identity`` and
``ham.requester_portal`` are siblings, not a dependency of one on the other).

Security review L1 (round 3, still applies): never store a raw code/token, and never hash one
with a plain unsalted digest — HMAC with a server-side secret means a leaked DB row alone can't
be brute-forced offline; the secret would also have to leak.

Key material: ``settings.HAM_TOKEN_HMAC_KEYS`` (comma-separated, first = current signing key,
every key tried on lookup so rotating the setting doesn't invalidate months-old links/codes
already sent out — intake.md §3 ``RequesterAccessLink``). Empty/unset (dev, test, and every
environment before this setting is introduced) falls back to a single key derived from
``SECRET_KEY``, which reproduces ``ham.identity.authn``'s pre-S2.0 hash exactly — this is a
deliberate "no behaviour change" fallback, not a production-safe default; ``HAM_TOKEN_HMAC_KEYS``
should be set explicitly in production, same as ``HAM_FIELD_ENCRYPTION_KEY``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from django.conf import settings


def _keys() -> list[bytes]:
    raw = getattr(settings, "HAM_TOKEN_HMAC_KEYS", "") or ""
    keys = [part.strip().encode() for part in raw.split(",") if part.strip()]
    if keys:
        return keys
    # Fallback (dev/test, or before HAM_TOKEN_HMAC_KEYS is configured): reproduces
    # ham.identity.authn's pre-S2.0 `_hash`, which HMAC'd with the bare SECRET_KEY.
    return [settings.SECRET_KEY.encode()]


def hash_value(value: str) -> str:
    """HMAC-SHA256 of ``value`` with the *first* configured key. New hashes always use this
    one; see ``hash_matches`` for verifying against a hash that may have used an older key."""
    return hmac.new(_keys()[0], value.encode(), hashlib.sha256).hexdigest()


def hash_matches(value: str, expected_hash: str) -> bool:
    """Constant-time check that ``value`` hashes to ``expected_hash`` under *any* configured
    key (current or a previously-rotated-out one) — intake.md §3 ``RequesterAccessLink``:
    "Lookups try every key.". Also the right primitive for verifying an emailed code/token
    hashed with the single current key in the common (non-rotated) case."""
    for key in _keys():
        candidate = hmac.new(key, value.encode(), hashlib.sha256).hexdigest()
        if secrets.compare_digest(candidate, expected_hash):
            return True
    return False


def hash_candidates(value: str) -> list[str]:
    """Every configured key's HMAC of ``value`` (S2.3, intake.md §3 ``RequesterAccessLink``
    "Lookups try every key"). Unlike ``hash_matches`` (which checks against one already-known
    hash), a *lookup by token* needs a set of candidate hashes to filter a table on —
    ``RequesterAccessLink.objects.filter(token_hash__in=hash_candidates(token))`` — since the
    caller doesn't know in advance which key originally hashed a given stored row."""
    return [hmac.new(key, value.encode(), hashlib.sha256).hexdigest() for key in _keys()]


def generate_code(length: int) -> str:
    """A cryptographically random decimal code of ``length`` digits (e.g. a 6-digit sign-in
    or requester-verification code); each digit drawn independently via ``secrets``."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def generate_token(nbytes: int = 32) -> str:
    """A cryptographically random URL-safe token (e.g. a sign-in link or requester access
    link token) — intake.md §3: "Token: ``secrets.token_urlsafe(32)``"."""
    return secrets.token_urlsafe(nbytes)


__all__ = ["generate_code", "generate_token", "hash_candidates", "hash_matches", "hash_value"]
