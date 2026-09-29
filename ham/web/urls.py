from django.urls import path

from . import (
    auth_views,
    urls_inbox,
    urls_requester,
    urls_requester_approvals,
    urls_requests,
    urls_requests_approvals,
    views,
    views_admin_settings,
    views_admin_users,
    views_audit,
    views_me,
)

app_name = "web"

# PUBLIC_ROUTES per foundation.md §7; the route-guard middleware itself lands with S3a. Views
# below carry `@requires_action(...)` where a guard attaches; sign-in family (S3b) is public.
urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("api/v1/me", views.api_me, name="api_me"),
    path("", views.home, name="home"),
    path("inbox", views.inbox, name="inbox"),
    path(
        "inbox/notifications/<uuid:notification_id>/acknowledge",
        views.notification_acknowledge,
        name="notification_acknowledge",
    ),
    path(
        "inbox/notifications/<uuid:notification_id>/open",
        views.notification_open,
        name="notification_open",
    ),
    path("admin", views.admin_index, name="admin_index"),
    path("more", views.more, name="more"),
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
    path("sign-in/cancel", auth_views.sign_in_cancel, name="sign_in_cancel"),
    path("me/security", auth_views.me_security, name="me_security"),
    path(
        "me/security/recovery-codes",
        auth_views.me_regenerate_recovery_codes,
        name="me_recovery_codes_regenerate",
    ),
    path("me/security/forget-devices", auth_views.me_forget_devices, name="me_forget_devices"),
    path(
        "me/security/sign-out-everywhere",
        auth_views.me_sign_out_everywhere,
        name="me_sign_out_everywhere",
    ),
    path("admin/users/<uuid:user_id>/mfa-reset", auth_views.admin_mfa_reset, name="user_mfa_reset"),
    path(
        "admin/users/<uuid:user_id>/impersonate",
        auth_views.admin_impersonate,
        name="impersonation_start",
    ),
    path("impersonation/stop", auth_views.impersonation_stop, name="impersonation_stop"),
    # Me (auth-and-access.md §F, non-security parts).
    path("me", views_me.me, name="me"),
    # Admin -> Users & roles (auth-and-access.md §G).
    path("admin/users", views_admin_users.admin_users_list, name="admin_users"),
    path("admin/users/new", views_admin_users.admin_users_invite, name="admin_users_invite"),
    path(
        "admin/users/new/sent",
        views_admin_users.admin_users_invite_sent,
        name="admin_users_invite_sent",
    ),
    path(
        "admin/users/<uuid:user_id>",
        views_admin_users.admin_user_detail,
        name="admin_user_detail",
    ),
    path(
        "admin/users/<uuid:user_id>/identity",
        views_admin_users.admin_user_identity_update,
        name="admin_user_identity_update",
    ),
    path(
        "admin/users/<uuid:user_id>/invitation/resend",
        views_admin_users.admin_user_invitation_resend,
        name="admin_user_invitation_resend",
    ),
    path(
        "admin/users/<uuid:user_id>/invitation/cancel",
        views_admin_users.admin_user_invitation_cancel,
        name="admin_user_invitation_cancel",
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
    path(
        "audit/export/download",
        views_audit.audit_export_download,
        name="audit_export_download",
    ),
    # --- Step 2 (Intake), S2.0 seams: real routes land in S2.7/S2.8 --------------------------
    *urls_requests.urlpatterns,
    *urls_requester.urlpatterns,
    *urls_inbox.urlpatterns,
    # --- Step 3 (Approvals), S3.0 seams: real routes land in S3.6/S3.7 ----------------------
    *urls_requests_approvals.urlpatterns,
    *urls_requester_approvals.urlpatterns,
]
