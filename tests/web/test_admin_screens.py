"""S5 screens (foundation.md §7, §8; auth-and-access.md §F, §G, §H): Me, Admin -> Users &
roles / Church settings / Integrations / Rules, and the Audit log. Each page renders for an
allowed persona and is a neutral 404 for a disallowed one; grant/revoke exercises the
step-up redirect; CSV export requires step-up; integration status carries no PII.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.platform.clock import now


def _mfa_login(client, user):
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()


@pytest.fixture
def admin_user(make_user):
    user = make_user("nadia@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Nadia Pierre")
    RoleAssignment.objects.create(user=user, role="ADMINISTRATOR", granted_at=now())
    return user


@pytest.fixture
def director_user(make_user):
    user = make_user("marcus@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=user, role="HAM_DIRECTOR", granted_at=now())
    return user


@pytest.fixture
def volunteer_user(make_user):
    user = make_user("kevin@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Kevin Thompson")
    RoleAssignment.objects.create(user=user, role="VOLUNTEER", granted_at=now())
    return user


@pytest.fixture
def admin_client(client, admin_user):
    _mfa_login(client, admin_user)
    return client


@pytest.fixture
def director_client(client, director_user):
    _mfa_login(client, director_user)
    return client


@pytest.fixture
def volunteer_client(client, volunteer_user):
    client.force_login(volunteer_user)
    return client


# ---------------------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------------------
@pytest.mark.django_db
def test_me_renders_and_updates(volunteer_client):
    response = volunteer_client.get(reverse("web:me"))
    assert response.status_code == 200
    assert b"Kevin Thompson" in response.content

    response = volunteer_client.post(
        reverse("web:me"),
        {"full_name": "Kevin T.", "mobile_phone": "3055550100", "notify_email": "on"},
    )
    assert response.status_code == 302
    response = volunteer_client.get(reverse("web:me"))
    assert b"Kevin T." in response.content


@pytest.mark.django_db
def test_me_requires_name(volunteer_client):
    response = volunteer_client.post(reverse("web:me"), {"full_name": "", "mobile_phone": ""})
    assert response.status_code == 200
    assert b"Enter your name" in response.content


# ---------------------------------------------------------------------------------------
# Admin -> Users & roles
# ---------------------------------------------------------------------------------------
@pytest.mark.django_db
def test_admin_sees_users_list(admin_client, volunteer_user):
    response = admin_client.get(reverse("web:admin_users"))
    assert response.status_code == 200
    assert b"kevin@example.org" in response.content


@pytest.mark.django_db
def test_volunteer_gets_neutral_404_on_admin_users(volunteer_client):
    response = volunteer_client.get(reverse("web:admin_users"))
    assert response.status_code == 404
    assert b"isn't available to your account" in response.content


@pytest.mark.django_db
def test_volunteer_gets_neutral_404_on_audit_log(volunteer_client):
    response = volunteer_client.get(reverse("web:audit_log"))
    assert response.status_code == 404


@pytest.mark.django_db
def test_admin_invites_a_volunteer(admin_client):
    response = admin_client.post(
        reverse("web:admin_users_invite"),
        {"email": "grace@example.org", "first_name": "Grace", "last_name": "G."},
    )
    assert response.status_code == 302
    response = admin_client.get(reverse("web:admin_users"))
    assert b"grace@example.org" in response.content


@pytest.mark.django_db
def test_grant_role_requires_step_up_then_succeeds(admin_client, volunteer_user):
    detail_url = reverse("web:admin_user_detail", args=[volunteer_user.id])
    review = admin_client.post(detail_url, {"stage": "review", "roles": ["VOLUNTEER", "PASTOR"]})
    assert review.status_code == 200
    assert b"Confirm changes" in review.content

    confirm_url = reverse("web:admin_user_roles_confirm", args=[volunteer_user.id])
    confirm = admin_client.post(confirm_url, {"add": ["PASTOR"], "remove": []})
    assert confirm.status_code == 302
    assert confirm["Location"].startswith("/step-up")

    step_up = admin_client.post(
        confirm["Location"], {"next": confirm["Location"], "kind": "role_change"}
    )
    assert step_up.status_code == 302
    resumed = admin_client.get(step_up["Location"])
    assert resumed.status_code == 302  # roles/resume -> detail page

    detail = admin_client.get(detail_url)
    assert b"Pastor" in detail.content
    assert any(
        ra.role == "PASTOR"
        for ra in RoleAssignment.objects.filter(user=volunteer_user, revoked_at__isnull=True)
    )


@pytest.mark.django_db
def test_administrator_cannot_change_own_role(admin_client, admin_user):
    """G2 "Roles the viewer can't change render read-only": every box is locked for one's own
    account, so a submitted diff is always empty rather than reaching the server twice."""
    detail_url = reverse("web:admin_user_detail", args=[admin_user.id])
    response = admin_client.post(detail_url, {"stage": "review", "roles": []})
    assert response.status_code == 200
    assert b"No changes selected" in response.content
    assert b"Only an Administrator can change this" in response.content


@pytest.mark.django_db
def test_disable_and_enable_account(admin_client, volunteer_user):
    disable_url = reverse("web:admin_user_disable", args=[volunteer_user.id])
    response = admin_client.post(disable_url, {})
    assert response.status_code == 302
    volunteer_user.refresh_from_db()
    assert volunteer_user.is_disabled

    enable_url = reverse("web:admin_user_enable", args=[volunteer_user.id])
    response = admin_client.post(enable_url, {})
    assert response.status_code == 302
    volunteer_user.refresh_from_db()
    assert not volunteer_user.is_disabled


# ---------------------------------------------------------------------------------------
# Admin -> Church settings / Integrations / Rules
# ---------------------------------------------------------------------------------------
@pytest.mark.django_db
def test_admin_updates_church_settings(admin_client):
    response = admin_client.post(
        reverse("web:admin_church_settings"),
        {
            "ham_phone": "305-555-0100",
            "ham_email": "ham@example.org",
            "time_zone": "America/New_York",
            "website_url": "https://example.org",
        },
    )
    assert response.status_code == 302
    response = admin_client.get(reverse("web:admin_church_settings"))
    assert b"305-555-0100" in response.content


@pytest.mark.django_db
def test_director_gets_neutral_404_on_church_settings(director_client):
    response = director_client.get(reverse("web:admin_church_settings"))
    assert response.status_code == 404


@pytest.mark.django_db
def test_integrations_page_has_no_pii(admin_client, volunteer_user):
    response = admin_client.get(reverse("web:admin_integrations"))
    assert response.status_code == 200
    assert b"kevin@example.org" not in response.content
    assert b"Kevin Thompson" not in response.content


@pytest.mark.django_db
def test_rules_page_renders_for_director(director_client):
    response = director_client.get(reverse("web:admin_rules"))
    assert response.status_code == 200
    assert b"2026.09.27-1" in response.content


@pytest.mark.django_db
def test_rules_page_denied_for_volunteer(volunteer_client):
    response = volunteer_client.get(reverse("web:admin_rules"))
    assert response.status_code == 404


# ---------------------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------------------
@pytest.mark.django_db
def test_director_can_view_audit_log_with_filters(director_client, admin_client, volunteer_user):
    admin_client.post(
        reverse("web:admin_user_disable", args=[volunteer_user.id]), {"reason": "test"}
    )
    response = director_client.get(reverse("web:audit_log"), {"action": "user.disabled"})
    assert response.status_code == 200
    assert b"user.disabled" in response.content


@pytest.mark.django_db
def test_audit_export_requires_step_up(director_client):
    response = director_client.post(reverse("web:audit_export"), {})
    assert response.status_code == 302
    assert response["Location"].startswith("/step-up")

    step_up = director_client.post(
        response["Location"], {"next": reverse("web:audit_export"), "kind": "audit_export"}
    )
    assert step_up.status_code == 302

    export = director_client.post(reverse("web:audit_export"), {})
    assert export.status_code == 200
    assert export["Content-Type"].startswith("text/csv")
