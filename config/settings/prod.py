"""Production settings (Render). Every secret and host comes from the environment
(docs/adr/0001-stack.md §4-§6); nothing here should ever need a code change to deploy
another church's copy (Q-026) beyond setting HAM_BRAND and the usual secrets."""

from __future__ import annotations

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False
HAM_ENV = "production"

if env("DJANGO_SECRET_KEY", default=None) is None:
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production.")

# Security review M5: `ham.identity.crypto`/`ham.platform.crypto` only *discover* a missing
# `HAM_FIELD_ENCRYPTION_KEY` the first time something tries to encrypt/decrypt a TOTP secret —
# too late for a deploy-time check. Validate it eagerly, at process startup, so a
# misconfigured production deploy fails to boot rather than silently falling back (it can't;
# `ham.platform.crypto` already refuses the dev fallback in production) or 500ing on first use.
_field_key = env("HAM_FIELD_ENCRYPTION_KEY", default="")
if not _field_key:
    raise RuntimeError(
        "HAM_FIELD_ENCRYPTION_KEY must be set in production (encrypts TOTP secrets/recovery "
        "codes at rest, foundation.md §3 MFA)."
    )
from cryptography.fernet import Fernet as _Fernet  # noqa: E402

# Security review M5: validate *every* comma-separated key, not just the first — a bad key
# anywhere later in a MultiFernet rotation list only fails at decrypt time, for whichever old
# record happens to need it, which is a much worse time to discover a typo than deploy time.
for _key in _field_key.split(","):
    try:
        _Fernet(_key.strip().encode())
    except (ValueError, TypeError) as exc:  # pragma: no cover - misconfiguration, not a code path
        raise RuntimeError(
            "HAM_FIELD_ENCRYPTION_KEY is not a valid Fernet key (base64 urlsafe, 32 bytes)."
        ) from exc

# Security review round 3, N4: sign-in/invitation/role-change/impersonation-ended emails all
# build an absolute link from `HAM_BASE_URL` (`ham.identity.notifications`) — a missing value
# used to silently fall back to whatever `ham.platform` defaulted to (localhost), which is
# harmless in dev but sends a real invitee/Administrator a broken link in production.
_base_url = env("HAM_BASE_URL", default="")
if not _base_url:
    raise RuntimeError("HAM_BASE_URL must be set in production (used in emailed links).")
if "localhost" in _base_url or "127.0.0.1" in _base_url:
    raise RuntimeError("HAM_BASE_URL must not point at localhost in production.")

# Security review M5: `HAM_TOKEN_HMAC_KEYS` empty means `ham.platform.otp` silently falls
# back to a SECRET_KEY-derived key (fine for dev/test, never acceptable in production --
# rotating SECRET_KEY for an unrelated reason would then invalidate every live requester
# link/code with no warning). Fail at boot, not the first time a link is issued.
if not env("HAM_TOKEN_HMAC_KEYS", default=""):
    raise RuntimeError(
        "HAM_TOKEN_HMAC_KEYS must be set in production (requester link/code HMAC keys, "
        "ham.platform.otp)."
    )

# Security review M5: the local-filesystem object store adapter (S2.4a) is a dev/test
# convenience only -- it has no real access control beyond a signed URL and stores files on
# the web dyno's own (ephemeral) disk. Refuse to boot with it configured in production; the
# R2/S3-compatible adapter is required instead.
_object_store_backend = env(
    "HAM_OBJECT_STORE_BACKEND", default="ham.integrations.storage.local.LocalObjectStore"
)
if _object_store_backend == "ham.integrations.storage.local.LocalObjectStore":
    raise RuntimeError(
        "HAM_OBJECT_STORE_BACKEND must not be the local-filesystem adapter in production; "
        "set it to the R2/S3-compatible adapter (ham.integrations.storage.s3.R2ObjectStore)."
    )

# N2: `ham.integrations.storage.s3.R2ObjectStore.__init__` only discovers a missing
# bucket/endpoint/credential the first time `get_object_store()` is actually called (first
# upload/read) — too late for a deploy-time check, same reasoning as the encryption-key check
# above. Validate eagerly here too.
if _object_store_backend == "ham.integrations.storage.s3.R2ObjectStore":
    _missing_s3_settings = [
        name
        for name in (
            "HAM_S3_BUCKET",
            "HAM_S3_ENDPOINT_URL",
            "HAM_S3_ACCESS_KEY_ID",
            "HAM_S3_SECRET_ACCESS_KEY",
        )
        if not env(name, default="")
    ]
    if _missing_s3_settings:
        raise RuntimeError(
            "Missing required S3/R2 object store settings in production: "
            + ", ".join(_missing_s3_settings)
        )

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Security headers (foundation.md §2.1).
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# A minimal CSP; the reporting step (public scoreboard embed) widens `frame-ancestors` for the
# church's own site only (Q-005), never for arbitrary hosts.
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# django.contrib.admin stays installed (Django needs it for auth's admin-adjacent bits during
# migrations) but is never mounted as a URL in production — see config/urls.py. Do not add an
# "/admin/" path here.

# Security review M6: no CSP at all in production. Appended (not inserted first) so it runs
# after WhiteNoise/security middleware have already set other headers; see
# `ham.platform.csp` for the exact directives and why each one is what it is (service worker,
# manifest, self-hosted fonts must keep working).
MIDDLEWARE = [*MIDDLEWARE, "ham.platform.csp.ContentSecurityPolicyMiddleware"]  # noqa: F405
