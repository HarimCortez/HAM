from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from ham.authz import roles
from ham.identity.models import RoleAssignment, User

pytestmark = pytest.mark.django_db


def test_seed_dev_creates_personas():
    call_command("seed_dev")
    assert User.objects.filter(email="nadia@example.org").exists()
    kevin = User.objects.get(email="kevin@example.org")
    assert RoleAssignment.objects.filter(
        user=kevin, role=roles.VOLUNTEER, revoked_at__isnull=True
    ).exists()
    marcus = User.objects.get(email="marcus@example.org")
    marcus_roles = set(
        RoleAssignment.objects.filter(user=marcus, revoked_at__isnull=True).values_list(
            "role", flat=True
        )
    )
    assert marcus_roles == {roles.HAM_DIRECTOR, roles.VOLUNTEER}


def test_seed_dev_is_idempotent():
    call_command("seed_dev")
    call_command("seed_dev")
    assert User.objects.filter(email="nadia@example.org").count() == 1
    assert (
        RoleAssignment.objects.filter(
            user__email="nadia@example.org", revoked_at__isnull=True
        ).count()
        == 1
    )


@override_settings(HAM_ENV="production")
def test_seed_dev_refuses_in_production():
    with pytest.raises(CommandError):
        call_command("seed_dev")
