"""S5 screens (foundation.md §7, §8; auth-and-access.md §F, §G, §H): Me, Admin -> Users &
roles / Church settings / Integrations / Rules, and the Audit log. Each page renders for an
allowed persona and is a neutral 404 for a disallowed one; grant/revoke exercises the
step-up redirect; CSV export requires step-up; integration status carries no PII.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.identity import totp
from ham.identity.crypto import encrypt
from ham.identity.models import RoleAssignment, SharedIdentityProfile, TOTPDevice
from ham.platform.clock import now

_DEV_SECRET = totp.new_secret()


def _mfa_login(client, user):
    client.force_login(user)
    TOTPDevice.objects.update_or_create(
        user=user,
        defaults={
            "secret_encrypted": encrypt(_DEV_SECRET),
            "created_at": now(),
            "confirmed_at": now(),
        },
    )
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()


def _current_totp_code() -> str:
    return totp.current_code(_DEV_SECRET)


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


@pytest.mark.django_db
def test_me_shows_effective_identity_and_is_read_only_while_impersonating(
    admin_client, admin_user, volunteer_user
):
    """Item 6: Me displays and would save the same (effective/impersonated) identity, and
    `me.update` is blocked while impersonating rather than silently editing the wrong
    person's profile (the views_me.py:19-vs-28 mismatch the review flagged)."""
    from ham.identity.models import ImpersonationSession
    from ham.platform.clock import now as clock_now

    session = ImpersonationSession.objects.create(
        admin_user=admin_user,
        target_user=volunteer_user,
        reason="troubleshooting",
        started_at=clock_now(),
        last_activity_at=clock_now(),
    )
    s = admin_client.session
    s["ham_impersonation_id"] = str(session.id)
    s.save()

    response = admin_client.get(reverse("web:me"))
    assert response.status_code == 200
    assert b"Kevin Thompson" in response.content or b"Kevin T." in response.content
    assert b"read-only" in response.content

    post = admin_client.post(reverse("web:me"), {"full_name": "Someone Else", "mobile_phone": ""})
    assert post.status_code == 302
    from ham.identity.models import SharedIdentityProfile

    assert SharedIdentityProfile.objects.get(user=volunteer_user).full_name == "Kevin Thompson"


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
        confirm["Location"],
        {"next": confirm["Location"], "kind": "role_change", "code": _current_totp_code()},
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
    # UX C5: GET shows a confirmation with a required reason; posting without one re-renders.
    confirm = admin_client.get(disable_url)
    assert confirm.status_code == 200
    missing_reason = admin_client.post(disable_url, {})
    assert missing_reason.status_code == 200
    response = admin_client.post(disable_url, {"reason": "left the ministry"})
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
    from ham.rules import RULES_VERSION

    assert RULES_VERSION.encode() in response.content
    # Values running on an open question's proposed default are marked as such (Q-001 etc.).
    assert "Proposed default — may change (Q-001)".encode() in response.content


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
        response["Location"],
        {"next": reverse("web:audit_export"), "kind": "audit_export", "code": _current_totp_code()},
    )
    assert step_up.status_code == 302

    export = director_client.post(reverse("web:audit_export"), {})
    assert export.status_code == 200
    assert export["Content-Type"].startswith("text/csv")


# ---------------------------------------------------------------------------------------
# Item 7: /api/v1/me, identity update form, invite-sent confirmation
# ---------------------------------------------------------------------------------------
@pytest.mark.django_db
def test_api_me_returns_effective_identity_no_email_or_phone(volunteer_client, volunteer_user):
    response = volunteer_client.get(reverse("web:api_me"))
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(volunteer_user.id)
    assert data["display_name"] == "Kevin T."  # SharedIdentityProfile.display_name (§68)
    assert data["roles"] == ["VOLUNTEER"]
    assert data["impersonation"]["active"] is False
    assert "rules_version" in data
    body = response.content.decode()
    assert volunteer_user.email not in body


@pytest.mark.django_db
def test_admin_can_update_someone_elses_identity(admin_client, volunteer_user):
    url = reverse("web:admin_user_identity_update", args=[volunteer_user.id])
    response = admin_client.post(url, {"full_name": "Kevin T.", "mobile_phone": "3055550100"})
    assert response.status_code == 302
    profile = SharedIdentityProfile.objects.get(user=volunteer_user)
    assert profile.full_name == "Kevin T."


@pytest.mark.django_db
def test_director_cannot_update_identity(director_client, volunteer_user):
    url = reverse("web:admin_user_identity_update", args=[volunteer_user.id])
    response = director_client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_invite_sent_confirmation_reachable_without_user_view(admin_client):
    # Simulates the Assistant Director's redirect target (Q-082): the page itself only needs
    # `user.invite`, not `user.view`, so it works for a role that lacks the list screen too.
    response = admin_client.get(reverse("web:admin_users_invite_sent") + "?email=new@example.org")
    assert response.status_code == 200
    assert b"new@example.org" in response.content


@pytest.mark.django_db
def test_inviting_existing_email_shows_friendly_message_not_500(admin_client, volunteer_user):
    response = admin_client.post(
        reverse("web:admin_users_invite"),
        {"email": volunteer_user.email, "first_name": "Someone", "last_name": ""},
    )
    assert response.status_code == 200
    assert b"already has a HAM account" in response.content


@pytest.mark.django_db
def test_resend_and_cancel_invitation(admin_client, make_user):
    invited = make_user("new-invite@example.org")
    RoleAssignment.objects.create(user=invited, role="VOLUNTEER", granted_at=now())

    resend = admin_client.post(reverse("web:admin_user_invitation_resend", args=[invited.id]))
    assert resend.status_code == 302
    invited.refresh_from_db()
    assert invited.invitation_resent_at is not None

    cancel = admin_client.post(
        reverse("web:admin_user_invitation_cancel", args=[invited.id]),
        {"reason": "wrong address"},
    )
    assert cancel.status_code == 302
    invited.refresh_from_db()
    assert invited.is_disabled is True


# ---------------------------------------------------------------------------------------
# Item 5: church time zone validation on the settings form
# ---------------------------------------------------------------------------------------
@pytest.mark.django_db
def test_church_settings_rejects_unknown_time_zone(admin_client):
    response = admin_client.post(
        reverse("web:admin_church_settings"),
        {
            "ham_phone": "305-555-0100",
            "ham_email": "ham@example.org",
            "time_zone": "Not/AZone",
            "website_url": "https://example.org",
        },
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------------------
# Item 7: Administrator Home summary; Assistant Director invite card
# ---------------------------------------------------------------------------------------
@pytest.mark.django_db
def test_administrator_home_shows_integration_summary(admin_client):
    response = admin_client.get(reverse("web:home"))
    assert response.status_code == 200
    assert b"Integrations" in response.content
    assert b"Recent sign-in failures" in response.content


@pytest.mark.django_db
def test_assistant_director_home_has_invite_card(client, make_user):
    andre = make_user("andre@example.org")
    SharedIdentityProfile.objects.create(user=andre, full_name="Andre Watson")
    RoleAssignment.objects.create(user=andre, role="ASSISTANT_DIRECTOR", granted_at=now())
    _mfa_login(client, andre)  # ASSISTANT_DIRECTOR is an MFA-required role (Q-045)
    response = client.get(reverse("web:home"))
    assert response.status_code == 200
    assert b"Invite someone" in response.content
