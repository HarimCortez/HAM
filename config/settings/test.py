"""Settings for `pytest` / CI. Fast, deterministic, and isolated from real email/integrations."""

from __future__ import annotations

import environ

from .base import *  # noqa: F401,F403

DEBUG = False
HAM_ENV = "test"
SECRET_KEY = "test-secret-key"

_env = environ.Env()
_default_test_db = "postgres://postgres:postgres@localhost:5432/ham_test"
DATABASES = {
    "default": _env.db("DATABASE_URL", default=_default_test_db),
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Speed only; no real passwords exist (HAM has no usable password, see base.py).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGGING["root"]["level"] = "WARNING"  # noqa: F405
