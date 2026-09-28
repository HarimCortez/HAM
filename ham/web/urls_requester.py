"""Public requester-portal screens (intake.md §7, S2.7). Every route here is public (no
account, PRD §7) — see `ham/authz/guard.py`'s `PUBLIC_ROUTES`, which lists every url name
below by name, the same pattern `ham.web.auth_views`'s sign-in family uses.

The two emailed, scanner-safe links use the exact literal paths
`ham.requester_portal.verification._CONFIRM_PATH_TEMPLATES` hard-codes
(intake-contracts.md §8.2): `/request-help/verify/link/<token>` and
`/request-help/new-link/<token>`.
"""

from __future__ import annotations

from django.urls import path

from . import views_requester as views

urlpatterns = [
    path("request-help", views.request_help_start, name="request_help_start"),
    path("request-help/begin", views.request_help_begin, name="request_help_begin"),
    path(
        "request-help/start-over",
        views.request_help_start_over,
        name="request_help_start_over",
    ),
    path("request-help/step/<str:step>", views.request_help_step, name="request_help_step"),
    path("request-help/verify", views.request_help_verify, name="request_help_verify"),
    path(
        "request-help/verify/link/<str:token>",
        views.request_help_verify_link,
        name="request_help_verify_link",
    ),
    path(
        "request-help/new-link/<str:token>",
        views.request_help_new_link,
        name="request_help_new_link",
    ),
    path("request-help/saved", views.request_help_saved, name="request_help_saved"),
    path(
        "request-help/r/<str:token>",
        views.request_help_secure_page,
        name="request_help_secure_page",
    ),
    path(
        "request-help/r/<str:token>/photos", views.request_help_photos, name="request_help_photos"
    ),
    path(
        "request-help/r/<str:token>/media/reserve",
        views.request_help_media_reserve,
        name="request_help_media_reserve",
    ),
    path(
        "request-help/r/<str:token>/media/<uuid:item_id>/complete",
        views.request_help_media_complete,
        name="request_help_media_complete",
    ),
    path(
        "request-help/r/<str:token>/media/<uuid:item_id>/remove",
        views.request_help_media_remove,
        name="request_help_media_remove",
    ),
    path(
        "request-help/r/<str:token>/link-expired/send",
        views.request_help_link_expired_send,
        name="request_help_link_expired_send",
    ),
    path("request-help/find", views.request_help_find, name="request_help_find"),
]
