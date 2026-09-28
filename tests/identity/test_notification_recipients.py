"""ham.identity.services.notification_recipients (S2.5, intake-contracts.md §7): resolves a
role set to active users' (user_id, email, notify_email), for ham.notifications/ham.requests
builders that must not read User/RoleAssignment themselves."""

from __future__ import annotations

import pytest

from ham.authz import roles
from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.identity.services import notification_recipients
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db


def _grant(user, role):
    return RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


class TestNotificationRecipients:
    def test_resolves_every_role_in_the_set(self, make_user):
        pastor = make_user("ruth@example.org")
        board = make_user("marcus@example.org")
        volunteer = make_user("kevin@example.org")
        _grant(pastor, roles.PASTOR)
        _grant(board, roles.BOARD_REPRESENTATIVE)
        _grant(volunteer, roles.VOLUNTEER)

        recipients = notification_recipients({roles.PASTOR, roles.BOARD_REPRESENTATIVE})
        assert {r[0] for r in recipients} == {pastor.id, board.id}

    def test_a_role_the_church_has_no_one_in_returns_nothing(self, make_user):
        director = make_user("nadia@example.org")
        _grant(director, roles.HAM_DIRECTOR)
        assert notification_recipients({roles.PASTOR}) == []

    def test_returns_email_and_notify_email_preference(self, make_user):
        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)
        SharedIdentityProfile.objects.create(user=pastor, notify_email=False)

        (user_id, email, notify_email) = notification_recipients({roles.PASTOR})[0]
        assert user_id == pastor.id
        assert email == "ruth@example.org"
        assert notify_email is False

    def test_defaults_notify_email_true_with_no_profile_row(self, make_user):
        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)
        assert SharedIdentityProfile.objects.filter(user=pastor).exists() is False

        (_, _, notify_email) = notification_recipients({roles.PASTOR})[0]
        assert notify_email is True

    def test_a_disabled_account_is_excluded(self, make_user):
        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)
        pastor.is_active = False
        pastor.save(update_fields=["is_active"])
        assert notification_recipients({roles.PASTOR}) == []

    def test_a_disabled_at_account_is_excluded(self, make_user):
        pastor = make_user("ruth@example.org")
        _grant(pastor, roles.PASTOR)
        pastor.disabled_at = clock_now()
        pastor.save(update_fields=["disabled_at"])
        assert notification_recipients({roles.PASTOR}) == []

    def test_a_revoked_role_is_excluded(self, make_user):
        pastor = make_user("ruth@example.org")
        grant = _grant(pastor, roles.PASTOR)
        grant.revoked_at = clock_now()
        grant.save(update_fields=["revoked_at"])
        assert notification_recipients({roles.PASTOR}) == []

    def test_a_user_holding_two_matching_roles_appears_once(self, make_user):
        leader = make_user("nadia@example.org")
        _grant(leader, roles.HAM_DIRECTOR)
        _grant(leader, roles.ASSISTANT_DIRECTOR)
        recipients = notification_recipients({roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR})
        assert len(recipients) == 1
        assert recipients[0][0] == leader.id
