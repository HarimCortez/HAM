"""Local development settings. Run with DJANGO_SETTINGS_MODULE=config.settings.dev (the default
in manage.py)."""

from __future__ import annotations

from .base import *  # noqa: F401,F403

DEBUG = True
HAM_ENV = "development"

# Django's built-in admin is a break-glass tool for the solo owner in dev only — it bypasses
# HAM's authorization and audit layer, so it is never mounted in prod (config/urls.py).
