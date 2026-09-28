"""Leadership request screens (intake.md §7, docs/ux/intake.md L1-L11). S2.8."""

from __future__ import annotations

from django.urls import path

from . import views_requests as views

urlpatterns = [
    path("requests", views.requests_list, name="requests"),
    path(
        "requests/new-by-phone",
        views.requests_needs_phone_check,
        name="requests_needs_phone_check",
    ),
    path("requests/<uuid:request_id>", views.request_detail, name="request_detail"),
    path(
        "requests/<uuid:request_id>/reveal",
        views.request_reveal_contact,
        name="request_reveal_contact",
    ),
    path(
        "requests/<uuid:request_id>/phone-check",
        views.request_phone_check,
        name="request_phone_check",
    ),
    path("requests/<uuid:request_id>/close", views.request_close, name="request_close"),
    path(
        "requests/<uuid:request_id>/more-photos",
        views.request_more_photos,
        name="request_more_photos",
    ),
]
