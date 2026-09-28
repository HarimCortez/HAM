"""Every shell page renders (S5 build note "Templates: templates render at each page")."""

from __future__ import annotations

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_home_renders(client):
    response = client.get(reverse("web:home"))
    assert response.status_code == 200
    assert b"Your to-do list will appear here" in response.content


@pytest.mark.django_db
def test_home_marks_active_nav_item(client):
    response = client.get(reverse("web:home"))
    content = response.content.decode()
    # navigation.md §3.3 "Mark active item (aria-current='page')".
    assert 'aria-current="page"' in content


@pytest.mark.django_db
def test_inbox_renders(client):
    response = client.get(reverse("web:inbox"))
    assert response.status_code == 200
    assert b"Nothing in your inbox" in response.content


@pytest.mark.django_db
def test_offline_page_renders(client):
    response = client.get(reverse("web:offline"))
    assert response.status_code == 200
    assert b"offline" in response.content.lower()


@pytest.mark.django_db
def test_neutral_not_found_page_is_a_404(client):
    """navigation.md §6 'No permission / not found': same neutral screen, same status code,
    no project title, for both an unknown route and a denied one."""
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    assert b"isn't available to your account" in response.content
    assert b"Go home" in response.content
    # §68: never leak whether *something specific* exists.
    assert b"does-not-exist" not in response.content


@pytest.mark.django_db
def test_healthz_still_public_and_unaffected_by_shell(client):
    response = client.get(reverse("web:healthz"))
    assert response.status_code == 200
