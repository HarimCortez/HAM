from django.conf import settings
from django.urls import path

from ham.platform.env import is_production

from . import views

app_name = "web"

# PUBLIC_ROUTES per foundation.md §7; the route-guard middleware itself lands with S3a. Views
# below carry `# S3a: @requires_action(...)` where a guard will attach.
urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("", views.home, name="home"),
    path("inbox", views.inbox, name="inbox"),
    path("offline", views.offline, name="offline"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
]

# Dev-only preview of the signed-in shell, for visual QA before sign-in exists (S5 build
# note). Never mounted in production, regardless of DEBUG.
if settings.DEBUG and not is_production():
    urlpatterns += [
        path("__dev__/shell-preview/", views.dev_shell_preview, name="dev_shell_preview"),
        path(
            "__dev__/shell-preview/not-found/",
            views.dev_not_found_preview,
            name="dev_not_found_preview",
        ),
    ]
