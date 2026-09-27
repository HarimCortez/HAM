"""Root URLconf.

foundation.md §7: "every route declares an action or is listed in `PUBLIC_ROUTES`" — that
route-guard middleware lands with S3a (authz). Until then, S1 only exposes the public health
check; nothing here requires a signed-in user yet.

Django's built-in admin is a break-glass tool for the solo owner and is **never mounted in
production** (docs/adr/0001-stack.md §6): it bypasses HAM's authorization and audit layer.
"""

from __future__ import annotations

from django.conf import settings
from django.urls import include, path

urlpatterns = [
    path("", include("ham.web.urls")),
]

if settings.DEBUG:
    from django.contrib import admin

    urlpatterns += [path("django-admin/", admin.site.urls)]
