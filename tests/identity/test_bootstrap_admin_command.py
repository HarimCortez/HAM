from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from ham.authz import roles
from ham.identity.models import RoleAssignment, User

pytestmark = pytest.mark.django_db


def test_bootstrap_admin_creates_administrator():
    call_command("bootstrap_admin", "--email", "owner@example.org")
    user = User.objects.get(email="owner@example.org")
    assert RoleAssignment.objects.filter(
        user=user, role=roles.ADMINISTRATOR, revoked_at__isnull=True
    ).exists()


def test_bootstrap_admin_rejects_bad_email():
    with pytest.raises(CommandError):
        call_command("bootstrap_admin", "--email", "not-an-email")
