"""ham.identity.notifications: invitation, role-change (Q-055) and impersonation-ended (Q-049)
email builders, registered onto the shared `ham.integrations.email.notifications` subscriber.
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.identity.models import ImpersonationSession, SharedIdentityProfile
from ham.identity.notifications import (
    _build_impersonation_ended_email,
    _build_invitation_email,
    _build_role_change_email,
)
from ham.outbox.models import OutboxEvent
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db


def _event(event_type: str, aggregate_id, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type, aggregate_type="user", aggregate_id=aggregate_id, payload=payload
    )


class TestInvitationEmail:
    def test_no_inviter_means_no_email(self, make_user):
        user = make_user("dwayne@example.org")
        event = _event("UserCreated", user.id, {"roles": [roles.VOLUNTEER]})
        assert _build_invitation_email(event) is None

    def test_invitation_email_names_inviter_and_church(self, make_user):
        inviter = make_user("nadia@example.org")
        SharedIdentityProfile.objects.create(user=inviter, full_name="Nadia Ruiz")
        invitee = make_user("dwayne@example.org")
        event = _event(
            "UserCreated", invitee.id, {"roles": [roles.VOLUNTEER], "invited_by": str(inviter.id)}
        )
        emails = _build_invitation_email(event)
        assert emails is not None and len(emails) == 1
        email = emails[0]
        assert email.to == "dwayne@example.org"
        assert "Nadia" in email.subject
        assert "/sign-in" in email.text_body


class TestRoleChangeEmail:
    def test_notifies_every_active_administrator(self, make_user):
        admin1 = make_user("nadia@example.org")
        admin2 = make_user("other-admin@example.org")
        for admin in (admin1, admin2):
            from ham.identity.models import RoleAssignment

            RoleAssignment.objects.create(
                user=admin, role=roles.ADMINISTRATOR, granted_at=clock_now()
            )
        subject_user = make_user("kevin@example.org")
        event = _event(
            "RoleGranted",
            subject_user.id,
            {"role": roles.VOLUNTEER, "granted_by": str(admin1.id)},
        )
        emails = _build_role_change_email(event)
        assert emails is not None
        assert {e.to for e in emails} == {"nadia@example.org", "other-admin@example.org"}

    def test_no_administrators_means_no_email(self, make_user):
        subject_user = make_user("kevin@example.org")
        event = _event(
            "RoleGranted",
            subject_user.id,
            {"role": roles.VOLUNTEER, "granted_by": str(uuid.uuid4())},
        )
        assert _build_role_change_email(event) is None


class TestImpersonationEndedEmail:
    def test_notifies_the_impersonated_person(self, make_user):
        admin = make_user("nadia@example.org")
        SharedIdentityProfile.objects.create(user=admin, full_name="Nadia Ruiz")
        target = make_user("kevin@example.org")
        session = ImpersonationSession.objects.create(
            admin_user=admin,
            target_user=target,
            reason="troubleshooting a check-in issue",
            started_at=clock_now(),
            last_activity_at=clock_now(),
            ended_at=clock_now(),
            end_reason=ImpersonationSession.END_REASON_MANUAL,
        )
        event = _event(
            "ImpersonationEnded",
            target.id,
            {"session_id": str(session.id), "admin_user_id": str(admin.id)},
        )
        email = _build_impersonation_ended_email(event)
        assert email is not None
        assert email.to == "kevin@example.org"
        assert "Nadia" in email.text_body
        assert "troubleshooting a check-in issue" in email.text_body
