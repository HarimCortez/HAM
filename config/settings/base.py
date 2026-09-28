"""12-factor base settings: everything that does not vary by environment.

`dev.py`, `test.py` and `prod.py` each start with `from .base import *` and override only
what has to differ (foundation.md §2.1). Every value that *does* vary comes from the
environment (docs/adr/0001-stack.md, "Render: Docker web service ... `render.yaml`").

Never put a fixed business rule here (deadlines, retention, weights) — those live in
`ham.rules` (CLAUDE.md "No magic numbers").
"""

from __future__ import annotations

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    HAM_ENV=(str, "development"),
    HAM_BRAND=(str, "miami-temple"),
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

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "procrastinate.contrib.django",
    "ham.platform",
    "ham.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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

# django-anymail backend selection lands with the S4 email adapter; base settings only
# reserve the setting so every environment defines *something* (12-factor).
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@example.org")

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
    },
}
