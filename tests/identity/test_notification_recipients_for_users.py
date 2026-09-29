"""ham.identity.services.notification_recipients_for_users (S3.0, approvals-contracts.md §7):
resolves specific user ids (the original decider, a question asker, a batch reopener) to
active users' (user_id, email, notify_email), same shape/rules as `notification_recipients`
but addressed by id rather than by role set."""

from __future__ import annotations

import uuid

import pytest

from ham.identity.models import SharedIdentityProfile
from ham.identity.services import notification_recipients_for_users
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db


class TestNotificationRecipientsForUsers:
    def test_resolves_each_id(self, make_user):
        ruth = make_user("ruth@example.org")
        marcus = make_user("marcus@example.org")
        recipients = notification_recipients_for_users([ruth.id, marcus.id])
        assert {r[0] for r in recipients} == {ruth.id, marcus.id}

    def test_unknown_id_is_skipped(self, make_user):
        ruth = make_user("ruth@example.org")
        recipients = notification_recipients_for_users([ruth.id, uuid.uuid4()])
        assert {r[0] for r in recipients} == {ruth.id}

    def test_empty_input_returns_empty(self):
        assert notification_recipients_for_users([]) == []

    def test_returns_email_and_notify_email_preference(self, make_user):
        ruth = make_user("ruth@example.org")
        SharedIdentityProfile.objects.create(user=ruth, notify_email=False)
        (user_id, email, notify_email) = notification_recipients_for_users([ruth.id])[0]
        assert user_id == ruth.id
        assert email == "ruth@example.org"
        assert notify_email is False

    def test_defaults_notify_email_true_with_no_profile_row(self, make_user):
        ruth = make_user("ruth@example.org")
        (_, _, notify_email) = notification_recipients_for_users([ruth.id])[0]
        assert notify_email is True

    def test_a_disabled_account_is_excluded(self, make_user):
        ruth = make_user("ruth@example.org")
        ruth.is_active = False
        ruth.save(update_fields=["is_active"])
        assert notification_recipients_for_users([ruth.id]) == []

    def test_a_disabled_at_account_is_excluded(self, make_user):
        ruth = make_user("ruth@example.org")
        ruth.disabled_at = clock_now()
        ruth.save(update_fields=["disabled_at"])
        assert notification_recipients_for_users([ruth.id]) == []

    def test_duplicate_ids_appear_once(self, make_user):
        ruth = make_user("ruth@example.org")
        recipients = notification_recipients_for_users([ruth.id, ruth.id])
        assert len(recipients) == 1

    def test_preserves_input_order(self, make_user):
        ruth = make_user("ruth@example.org")
        marcus = make_user("marcus@example.org")
        recipients = notification_recipients_for_users([marcus.id, ruth.id])
        assert [r[0] for r in recipients] == [marcus.id, ruth.id]
