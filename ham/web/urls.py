from django.urls import path

from . import views

# PUBLIC_ROUTES per foundation.md §7; the route-guard middleware itself lands with S3a.
urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
]
