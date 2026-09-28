from django.urls import path

from . import views, views_admin_settings, views_admin_users, views_audit, views_me
from .stepup import step_up_stub

app_name = "web"

# PUBLIC_ROUTES per foundation.md §7; the route-guard middleware itself lands with S3a. Views
# below carry `@requires_action(...)` (S5) where a guard attaches; sign-in family (S3b) is not
# built in this worktree yet.
urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("", views.home, name="home"),
    path("inbox", views.inbox, name="inbox"),
    path("offline", views.offline, name="offline"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    # Temporary stand-in for S3b's real step-up screen (ham/web/stepup.py module docstring).
    path("step-up", step_up_stub, name="step_up"),
    # Me (auth-and-access.md §F, non-security parts).
    path("me", views_me.me, name="me"),
    # Admin -> Users & roles (auth-and-access.md §G).
    path("admin/users", views_admin_users.admin_users_list, name="admin_users"),
    path("admin/users/new", views_admin_users.admin_users_invite, name="admin_users_invite"),
    path(
        "admin/users/<uuid:user_id>",
        views_admin_users.admin_user_detail,
        name="admin_user_detail",
    ),
    path(
        "admin/users/<uuid:user_id>/roles/confirm",
        views_admin_users.admin_user_roles_confirm,
        name="admin_user_roles_confirm",
    ),
    path(
        "admin/users/<uuid:user_id>/roles/resume",
        views_admin_users.admin_user_roles_resume,
        name="admin_user_roles_resume",
    ),
    path(
        "admin/users/<uuid:user_id>/disable",
        views_admin_users.admin_user_disable,
        name="admin_user_disable",
    ),
    path(
        "admin/users/<uuid:user_id>/enable",
        views_admin_users.admin_user_enable,
        name="admin_user_enable",
    ),
    # Admin -> Church settings, Integrations, Rules.
    path(
        "admin/settings/church",
        views_admin_settings.admin_church_settings,
        name="admin_church_settings",
    ),
    path("admin/integrations", views_admin_settings.admin_integrations, name="admin_integrations"),
    path(
        "admin/integrations/deliveries/<uuid:delivery_id>/retry",
        views_admin_settings.admin_integrations_retry,
        name="admin_integrations_retry",
    ),
    path("admin/rules", views_admin_settings.admin_rules, name="admin_rules"),
    # Audit log.
    path("audit", views_audit.audit_log_list, name="audit_log"),
    path("audit/<uuid:event_id>", views_audit.audit_log_detail, name="audit_log_detail"),
    path("audit/export", views_audit.audit_export, name="audit_export"),
]
