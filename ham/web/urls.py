from django.conf import settings
from django.urls import path

from ham.platform.env import is_production

from . import auth_views, views

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
    # --- Auth (S3b): sign-in family is public (PUBLIC_ROUTES, ham/authz/guard.py) ----------
    path("sign-in", auth_views.sign_in, name="sign_in"),
    path("sign-in/code", auth_views.sign_in_code, name="sign_in_code"),
    path("sign-in/link/<str:token>", auth_views.sign_in_link, name="sign_in_link"),
    path("sign-in/mfa", auth_views.sign_in_mfa, name="sign_in_mfa"),
    path("mfa/setup", auth_views.mfa_setup, name="mfa_setup"),
    path("mfa/setup/codes", auth_views.mfa_setup_codes, name="mfa_setup_codes"),
    path("step-up", auth_views.step_up, name="step_up"),
    path("sign-out", auth_views.sign_out, name="sign_out"),
    path("me/security", auth_views.me_security, name="me_security"),
    path(
        "me/security/recovery-codes",
        auth_views.me_regenerate_recovery_codes,
        name="me_recovery_codes_regenerate",
    ),
    path("me/security/forget-devices", auth_views.me_forget_devices, name="me_forget_devices"),
    path(
        "admin/users/<uuid:user_id>/mfa-reset", auth_views.admin_mfa_reset, name="admin_mfa_reset"
    ),
    path(
        "admin/users/<uuid:user_id>/impersonate",
        auth_views.admin_impersonate,
        name="admin_impersonate",
    ),
    path("impersonation/stop", auth_views.impersonation_stop, name="impersonation_stop"),
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
