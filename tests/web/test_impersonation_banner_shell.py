"""The impersonation banner shows on every route, including the neutral not-found page
(visual QA C1, PRD §59): a signed-in person acting as someone else never loses that context,
even landing somewhere that doesn't exist.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.identity.models import ImpersonationSession, RoleAssignment, SharedIdentityProfile
from ham.platform.clock import now


@pytest.fixture
def impersonating_client(client, make_user):
    admin = make_user("nadia@example.org")
    SharedIdentityProfile.objects.create(user=admin, full_name="Nadia Pierre")
    RoleAssignment.objects.create(user=admin, role="ADMINISTRATOR", granted_at=now())

    kevin = make_user("kevin@example.org")
    SharedIdentityProfile.objects.create(user=kevin, full_name="Kevin Thompson")
    RoleAssignment.objects.create(user=kevin, role="VOLUNTEER", granted_at=now())

    client.force_login(admin)
    session_row = ImpersonationSession.objects.create(
        admin_user_id=admin.id,
        target_user_id=kevin.id,
        reason="smoke test",
        started_at=now(),
        last_activity_at=now(),
    )
    session = client.session
    session["ham_impersonation_id"] = str(session_row.id)
    session["ham_mfa_satisfied"] = True
    session.save()
    return client


@pytest.mark.django_db
def test_banner_shows_on_home_while_impersonating(impersonating_client):
    response = impersonating_client.get(reverse("web:home"))
    content = response.content.decode()
    assert "Acting as" in content
    assert "Kevin Thompson" in content


@pytest.mark.django_db
def test_banner_shows_on_not_found_while_impersonating(impersonating_client):
    """Visual QA C1: the banner (and 'Return to my account') must not disappear just because
    the route the person landed on doesn't exist or isn't permitted."""
    response = impersonating_client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    content = response.content.decode()
    assert "Acting as" in content
    assert "Kevin Thompson" in content
    assert "Return to my account" in content
    # C1: a signed-in person keeps the shell (nav still renders) instead of dropping to the
    # no-nav public layout.
    assert 'class="nav nav--bottom"' in content


@pytest.mark.django_db
def test_not_found_for_a_signed_out_visitor_has_no_banner_and_no_nav(client):
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    content = response.content.decode()
    assert "Acting as" not in content
    assert 'class="nav nav--bottom"' not in content
