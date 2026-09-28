"""PWA manifest + service worker (S5 build note item 4)."""

from __future__ import annotations

import json

import pytest
from django.urls import reverse

from ham.platform.brand import load_brand


@pytest.mark.django_db
def test_manifest_content_comes_from_the_church_profile(client, settings):
    settings.HAM_BRAND = "miami-temple"
    load_brand.cache_clear()

    response = client.get(reverse("web:manifest"))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/manifest+json"

    data = json.loads(response.content)
    brand = load_brand("miami-temple")
    assert data["name"] == f"{brand.short_name} HAM"
    assert data["short_name"] == "HAM"
    assert data["description"] == brand.mission_line
    assert brand.id in data["icons"][0]["src"]
    # PRD §68: a public endpoint's response never carries requester/volunteer PII.
    assert "phone" not in json.dumps(data).lower()


@pytest.mark.django_db
def test_service_worker_is_served_with_correct_headers(client):
    response = client.get(reverse("web:service_worker"))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/javascript"
    assert response["Service-Worker-Allowed"] == "/"


@pytest.mark.django_db
def test_service_worker_route_is_public(client):
    # No session at all: must not redirect to a sign-in page that doesn't exist yet.
    response = client.get(reverse("web:service_worker"))
    assert response.status_code == 200
