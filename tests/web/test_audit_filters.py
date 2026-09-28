"""The H1 audit filter bar (usability M5/M6/M7): plain-language action labels, no raw internal
codes required to filter, date-range presets, and church-local times.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from ham.audit.models import AuditEvent
from ham.authz.roles import ROLE_LABELS
from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.platform.clock import now
from ham.rules import RULES_VERSION


@pytest.fixture
def admin_client(client, make_user):
    user = make_user("nadia@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Nadia Pierre")
    RoleAssignment.objects.create(user=user, role="ADMINISTRATOR", granted_at=now())
    client.force_login(user)
    # ADMINISTRATOR is an MFA-required role (§60.1); its permissions only activate once this
    # session's `ham_mfa_satisfied` is set (Q-045).
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return user, client


@pytest.fixture
def an_event(admin_client, make_user):
    user, _client = admin_client
    kevin = make_user("kevin@example.org")
    SharedIdentityProfile.objects.create(user=kevin, full_name="Kevin Thompson")
    return AuditEvent.objects.create(
        occurred_at=now(),
        actor_type="user",
        actor_user_id=user.id,
        action="role.granted",
        target_type="user",
        target_id=str(kevin.id),
        rules_version=RULES_VERSION,
    )


@pytest.mark.django_db
def test_action_select_shows_plain_language_labels_not_raw_codes(admin_client, an_event):
    _user, client = admin_client
    response = client.get(reverse("web:audit_log"))
    content = response.content.decode()
    assert "Role added" in content
    # The raw code should only appear as an <option value=...>, never as visible list text.
    assert ">role.granted<" not in content


@pytest.mark.django_db
def test_subject_shows_a_persons_name_not_a_raw_uuid(admin_client, an_event):
    _user, client = admin_client
    response = client.get(reverse("web:audit_log"))
    content = response.content.decode()
    # The audit log's own display-name convention is the short "Kevin T." form (used
    # everywhere in the viewer, per `display_names_for`'s docstring) — the point of this test
    # is that a *name* shows at all, not the raw UUID.
    assert "Kevin T." in content
    assert str(an_event.target_id) not in content


@pytest.mark.django_db
def test_role_filter_is_a_labelled_select_of_role_names(admin_client, an_event):
    _user, client = admin_client
    response = client.get(reverse("web:audit_log"))
    content = response.content.decode()
    for label in ROLE_LABELS.values():
        assert label in content


@pytest.mark.django_db
def test_date_range_preset_filters_events(admin_client, make_user):
    user, client = admin_client
    old_event = AuditEvent.objects.create(
        occurred_at=now() - dt.timedelta(days=60),
        actor_type="user",
        actor_user_id=user.id,
        action="auth.sign_in.succeeded",
        target_type="user",
        target_id=str(user.id),
        rules_version=RULES_VERSION,
    )
    recent_event = AuditEvent.objects.create(
        occurred_at=now(),
        actor_type="user",
        actor_user_id=user.id,
        action="auth.sign_in.succeeded",
        target_type="user",
        target_id=str(user.id),
        rules_version=RULES_VERSION,
    )
    response = client.get(reverse("web:audit_log"), {"range": "7"})
    content = response.content.decode()
    assert str(recent_event.id) in content
    assert str(old_event.id) not in content


@pytest.mark.django_db
def test_export_button_disabled_with_zero_events(admin_client):
    _user, client = admin_client
    response = client.get(reverse("web:audit_log"), {"range": "today", "action": "user.created"})
    content = response.content.decode()
    assert "0 event" in content
    assert "disabled" in content
