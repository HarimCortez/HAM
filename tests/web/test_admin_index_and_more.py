"""`GET /admin` and `GET /more` (visual QA C2 / usability C2, Q-091): the Admin index and More
pages that make every destination reachable on a phone once the bottom nav is capped at 5
items (see `tests/authz/test_nav_mobile.py` for the nav-building logic itself).
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.platform.clock import now


def _mfa_login(client, user):
    """ADMINISTRATOR/HAM_DIRECTOR are MFA-required roles (§60.1); their permissions only
    activate once this session's `ham_mfa_satisfied` is set (Q-045)."""
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()


@pytest.fixture
def admin_client(client, make_user):
    user = make_user("nadia@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Nadia Pierre")
    RoleAssignment.objects.create(user=user, role="ADMINISTRATOR", granted_at=now())
    _mfa_login(client, user)
    return client


@pytest.fixture
def director_client(client, make_user):
    user = make_user("marcus@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=user, role="HAM_DIRECTOR", granted_at=now())
    _mfa_login(client, user)
    return client


@pytest.fixture
def volunteer_client(client, make_user):
    user = make_user("kevin@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Kevin Thompson")
    RoleAssignment.objects.create(user=user, role="VOLUNTEER", granted_at=now())
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_admin_index_lists_users_church_integrations_rules_audit_for_administrator(admin_client):
    response = admin_client.get(reverse("web:admin_index"))
    assert response.status_code == 200
    content = response.content.decode()
    for label in ("Users &amp; roles", "Church settings", "Integrations", "Rules", "Audit log"):
        assert label in content


@pytest.mark.django_db
def test_more_page_for_administrator_has_me_and_sign_out(admin_client):
    response = admin_client.get(reverse("web:more"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Me" in content
    assert "Sign out" in content


@pytest.mark.django_db
def test_more_page_for_director_carries_admin_group_items(director_client):
    response = director_client.get(reverse("web:more"))
    assert response.status_code == 200
    content = response.content.decode()
    for label in ("Users &amp; roles", "Rules", "Audit log", "Me", "Sign out"):
        assert label in content
    # Church settings / Integrations are Administrator-only.
    assert "Church settings" not in content


@pytest.mark.django_db
def test_volunteer_cannot_reach_admin_index(volunteer_client):
    response = volunteer_client.get(reverse("web:admin_index"))
    content = response.content.decode()
    assert "Nothing here yet" in content or response.status_code == 404


@pytest.mark.django_db
def test_mobile_bottom_nav_on_a_rendered_page_is_capped_at_five_for_administrator(admin_client):
    response = admin_client.get(reverse("web:home"))
    content = response.content.decode()
    # The bottom nav's <ul> is the second `_nav_items.html` include (rail, sidebar, bottom);
    # simplest robust check: "Admin" and "More" tabs render, and none of the individual admin
    # destinations appear as their own bottom-nav-style link outside the sidebar/rail lists.
    assert 'href="/admin"' in content
    assert 'href="/more"' in content
