from __future__ import annotations

from django.urls import path

from . import dev_views

urlpatterns = [
    path("<str:token>", dev_views.local_storage_object, name="local-storage-object"),
]
