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

try:
    # MultiFernet-style rotation: a comma-separated list, newest key first, all still
    # decryptable. A single key is the common case and still validates as exactly one Fernet.
    _Fernet(_field_key.split(",")[0].encode())
except (ValueError, TypeError) as exc:  # pragma: no cover - misconfiguration, not a code path
    raise RuntimeError(
        "HAM_FIELD_ENCRYPTION_KEY is not a valid Fernet key (base64 urlsafe, 32 bytes)."
    ) from exc

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
