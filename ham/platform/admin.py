"""Django admin registration for ChurchProfile.

This is only ever reachable when `settings.DEBUG` is True (config/urls.py doesn't mount
`/django-admin/` in production) — it exists for local development convenience, not as a
production editing path. The real `church_profile.update` command (audited, step-up'd,
`ADM` only per foundation.md §4) lands with S3a/S5 and will be the only production path."""

from __future__ import annotations

from django.contrib import admin

from ham.platform.models import ChurchProfile


@admin.register(ChurchProfile)
class ChurchProfileAdmin(admin.ModelAdmin):
    list_display = ("ham_email", "ham_phone", "time_zone", "website_url", "updated_at")
