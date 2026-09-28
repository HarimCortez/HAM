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
    # S2.4a: local-filesystem ObjectStore adapter's stand-in for presigned PUT/GET (dev/test
    # only in practice — production always configures the R2 adapter instead, which talks
    # straight to R2 and never touches this app; the route is harmless to leave mounted since
    # every request needs a tamper-proof, time-limited, single-purpose signed token).
    path("dev/storage/", include("ham.integrations.storage.urls")),
]

if settings.DEBUG:
    from django.contrib import admin

    urlpatterns += [path("django-admin/", admin.site.urls)]

# navigation.md §6 "No permission / not found": same neutral screen, same status code, for a
# route that doesn't exist and one the viewer isn't allowed to see (§68). The real
# authz-denied case renders the same template from S3a's route guard; this handler only
# covers Django's own 404 (unknown URL).
handler404 = "ham.web.views.not_found"
handler500 = "ham.web.views.server_error"
