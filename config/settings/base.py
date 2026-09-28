"""12-factor base settings: everything that does not vary by environment.

`dev.py`, `test.py` and `prod.py` each start with `from .base import *` and override only
what has to differ (foundation.md §2.1). Every value that *does* vary comes from the
environment (docs/adr/0001-stack.md, "Render: Docker web service ... `render.yaml`").

Never put a fixed business rule here (deadlines, retention, weights) — those live in
`ham.rules` (CLAUDE.md "No magic numbers").
"""

from __future__ import annotations

import json
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    HAM_ENV=(str, "development"),
    HAM_BRAND=(str, "miami-temple"),
    HAM_TRUSTED_PROXY_COUNT=(int, 0),
)
# A .env file is only ever read in development; prod/Render inject real environment
# variables directly, and CI sets its own. Reading a missing .env is not an error.
environ.Env.read_env(str(BASE_DIR / ".env"))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-secret-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG")

# HAM_ENV gates behaviour that must never run in production regardless of DEBUG:
# Django admin mount (CLAUDE.md "Stack" guardrail) and seed commands (foundation.md §2.11).
HAM_ENV = env("HAM_ENV")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Security review round 3, N5: how many `X-Forwarded-For` hops (right-to-left) were added by
# proxies HAM itself controls -- everything to the *left* of that many hops is attacker-
# controlled input a client can fake, so `ham.web.auth_views._client_ip`'s sign-in throttle
# must never trust more hops than this. `0` (the default, correct for `make run`/tests
# without a proxy in front) means "don't trust the header at all, use `REMOTE_ADDR`"; Render
# terminates TLS and adds exactly one hop, so `render.yaml` sets this to `1`.
HAM_TRUSTED_PROXY_COUNT = env.int("HAM_TRUSTED_PROXY_COUNT")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "procrastinate.contrib.django",
    # S3b auth: HAM does NOT install `allauth`/`allauth.mfa` as Django apps — see
    # `ham/identity/totp.py`'s module docstring: doing so pulls in the unrelated legacy
    # `allauth` app's own `EmailAddress`/`EmailConfirmation` models via Django's unmigrated-app
    # table sync, which broke test-database creation. `django-allauth[mfa]` stays a pyproject
    # dependency only for `qrcode` (QR provisioning) and as a spike reference; HAM's own
    # `ham.identity.totp`/`ham.identity.models.TOTPDevice`/`RecoveryCode` do the rest.
    "ham.platform",
    "ham.outbox",
    "ham.integrations",
    "ham.identity",
    "ham.authz",
    "ham.audit",
    "ham.web",
]

# Custom user model (foundation.md §3 "User"): no usable password, sign-in is by emailed
# code + MFA (S3b). Only ham.identity may read auth tables (foundation.md §1).
AUTH_USER_MODEL = "identity.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Build request.actor (foundation.md §1, §7): must run after AuthenticationMiddleware
    # (needs request.user) and before the route guard (needs request.actor).
    "ham.identity.middleware.ActorContextMiddleware",
    # Session/idle lifetimes (Q-032) and the impersonation idle timeout (§59, Q-053): needs
    # request.actor (just built above) and must run before the route guard so an expired
    # session is signed out before any view executes.
    "ham.identity.middleware.SessionLifetimeMiddleware",
    # Q-030/§70.5: activate the one church time zone for every request (screens, emails and
    # day-based rules use it, never the server's or the browser's own time zone).
    "ham.platform.timezone_middleware.ChurchTimeZoneMiddleware",
    # Route guard (foundation.md §7): every URL must declare an action or be public.
    "ham.authz.guard.RouteGuardMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "ham" / "web" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "ham.platform.context_processors.church",
                "ham.web.context_processors.shell",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres:///ham"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DJANGO_CONN_MAX_AGE", default=60)

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = [
    # HAM has no usable password (foundation.md §3, User model): sign-in is by emailed code
    # (django-allauth, S3b). This list stays empty on purpose rather than validating a
    # password field nothing ever sets.
]

# Store timestamps in UTC everywhere; convert to church-local time only for display (§70.5).
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False  # Multilingual is deferred (CLAUDE.md scope; PRD §74).
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# WhiteNoiseMiddleware checks this directory at process start and warns loudly if it is
# missing (harmless before the first `collectstatic`, but noisy in every test run). Creating
# it up front costs nothing — `collectstatic` still fills it normally in prod/CI — and avoids
# a spurious "No directory at: staticfiles/" warning on every test (S5 build note).
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
STATICFILES_DIRS = [
    d for d in [BASE_DIR / "design-system", BASE_DIR / "frontend" / "dist"] if d.exists()
]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------------------
# HAM-specific settings
# ---------------------------------------------------------------------------------------

# Q-026: which design-system/brands/<id>/ folder this deployment is for. Never hard-code a
# church name anywhere else in the codebase.
HAM_BRAND = env("HAM_BRAND")

# PRD-guardian review B2: the emailed sign-in link must be a full, absolute URL — a relative
# path would leave the person nowhere to go when they open the email in a different client
# than the browser tab they started from (or an email client with no "base" context at all).
# Also used to build the invitation email's absolute sign-in link (Q-037/Q-071/Q-084) since a
# background job has no request to build one from. Dev default matches `make run`'s
# `runserver 0.0.0.0:8000`; every real deployment sets this. `.rstrip("/")` so callers can
# always do `f"{settings.HAM_BASE_URL}{path}"` without checking for a double slash.
HAM_BASE_URL = env("HAM_BASE_URL", default="http://localhost:8000").rstrip("/")

# Email adapter (ham.integrations.email, foundation.md §8 S4): dev = console, test = locmem
# (overridden below/in test.py), prod = whichever Anymail ESP backend the environment names —
# never a hard-coded provider (CLAUDE.md "Secrets come from environment variables").
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@example.org")

# Anymail's own per-ESP settings (e.g. an API key), as a JSON object so this stays a single
# secret store lookup and never needs a code change to add another environment variable per
# provider. Empty by default; dev/test never use an Anymail backend so it is never read.
ANYMAIL: dict = json.loads(env("ANYMAIL_SETTINGS_JSON", default="{}"))

# Auth (S3b, foundation.md §3 "MFA"): encrypts TOTP secrets at rest (`ham.identity.crypto`).
# Must be a `Fernet.generate_key()` value in production; dev/test fall back to a key derived
# from SECRET_KEY (guarded against in `ham.identity.crypto`, never reachable when
# HAM_ENV=production). Never a fixed business *rule* (CLAUDE.md "no magic numbers") — it's a
# secret, so it belongs here, not in `ham.rules`.
HAM_FIELD_ENCRYPTION_KEY = env("HAM_FIELD_ENCRYPTION_KEY", default="")

# Session cookie ceiling: the *longest* possible HAM session (Q-032's standard/passwordless
# lifetime). `ham.identity.middleware.SessionLifetimeMiddleware` enforces the shorter
# MFA-role idle/absolute lifetimes and signs people out well before the browser cookie would
# expire on its own; this is only the outer bound, read from the rules module rather than
# hard-coded (CLAUDE.md "no magic numbers").
from ham.rules import RULES as _RULES  # noqa: E402

SESSION_COOKIE_AGE = int(_RULES.auth.SESSION_IDLE_LIFETIME_STANDARD.total_seconds())
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SAMESITE = "Lax"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        # CLAUDE.md / PRD §68: logs never contain names, emails or phone numbers.
        "scrub_pii": {"()": "ham.platform.logging.ScrubPIIFilter"},
    },
    "formatters": {
        "structured": {
            "()": "ham.platform.logging.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["scrub_pii"],
            "formatter": "structured",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Security review C2: Procrastinate logs "Starting job ...(kwargs)" at INFO, which
        # would otherwise print full task args (e.g. an encrypted email payload's ciphertext
        # is harmless, but this also caught other jobs' plain kwargs before they existed).
        # WARNING+ only, so routine per-job start/finish lines never reach the log at all;
        # failures still surface. Belt and suspenders with the encrypted job args themselves
        # and `JSONFormatter`'s nested-extra scrubbing above.
        "procrastinate": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
