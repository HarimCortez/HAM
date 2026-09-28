from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

from ham.authz import roles
from ham.identity.models import RoleAssignment
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db


def _grant(user, role, **kwargs):
    return RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now(), **kwargs)


class TestUser:
    def test_email_is_case_insensitive_unique(self, make_user):
        make_user("kevin@example.org")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_user("Kevin@Example.org")

    def test_no_usable_password(self, make_user):
        user = make_user("kevin@example.org")
        assert user.has_usable_password() is False

    def test_invited_until_first_sign_in(self, make_user):
        user = make_user("kevin@example.org")
        assert user.is_invited is True
        user.first_sign_in_at = clock_now()
        user.save()
        assert user.is_invited is False

    def test_disabled_state(self, make_user):
        user = make_user("kevin@example.org")
        assert user.is_disabled is False
        user.disabled_at = clock_now()
        user.save()
        assert user.is_disabled is True


class TestSharedIdentityProfileDisplayName:
    def test_derives_first_name_last_initial(self, make_user):
        user = make_user("kevin@example.org")
        profile = user.profile if hasattr(user, "profile") else None
        from ham.identity.models import SharedIdentityProfile

        profile = SharedIdentityProfile.objects.create(user=user, full_name="Kevin Thompson")
        assert profile.display_name == "Kevin T."

    def test_single_name_shown_whole(self, make_user):
        from ham.identity.models import SharedIdentityProfile

        user = make_user("bayside@example.org")
        profile = SharedIdentityProfile.objects.create(user=user, full_name="Bayside")
        assert profile.display_name == "Bayside"


class TestRoleAssignmentInvariants:
    def test_global_role_requires_null_scope(self, make_user):
        user = make_user("kevin@example.org")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _grant(
                    user,
                    roles.VOLUNTEER,
                    scope_type=roles.SCOPE_TYPE_PROJECT,
                    scope_id=uuid.uuid4(),
                )

    def test_project_leader_requires_project_scope(self, make_user):
        user = make_user("luis@example.org")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _grant(user, roles.PROJECT_LEADER)  # no scope_type/scope_id

    def test_project_leader_with_task_scope_type_rejected(self, make_user):
        user = make_user("luis@example.org")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _grant(
                    user,
                    roles.PROJECT_LEADER,
                    scope_type=roles.SCOPE_TYPE_TASK,
                    scope_id=uuid.uuid4(),
                )

    def test_project_leader_valid_row(self, make_user):
        user = make_user("luis@example.org")
        assignment = _grant(
            user, roles.PROJECT_LEADER, scope_type=roles.SCOPE_TYPE_PROJECT, scope_id=uuid.uuid4()
        )
        assert assignment.is_active is True

    def test_one_active_global_role_per_user(self, make_user):
        user = make_user("kevin@example.org")
        _grant(user, roles.VOLUNTEER)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _grant(user, roles.VOLUNTEER)

    def test_re_grant_after_revoke_is_allowed(self, make_user):
        user = make_user("kevin@example.org")
        first = _grant(user, roles.VOLUNTEER)
        first.revoked_at = clock_now()
        first.save()
        second = _grant(user, roles.VOLUNTEER)
        assert second.pk != first.pk
        assert (
            RoleAssignment.objects.filter(
                user=user, role=roles.VOLUNTEER, revoked_at__isnull=True
            ).count()
            == 1
        )

    def test_one_active_leader_per_project(self, make_user):
        luis = make_user("luis@example.org")
        tom = make_user("tom@example.org")
        project_id = uuid.uuid4()
        _grant(luis, roles.PROJECT_LEADER, scope_type=roles.SCOPE_TYPE_PROJECT, scope_id=project_id)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _grant(
                    tom,
                    roles.PROJECT_LEADER,
                    scope_type=roles.SCOPE_TYPE_PROJECT,
                    scope_id=project_id,
                )

    def test_reassigning_after_revoke_is_allowed(self, make_user):
        luis = make_user("luis@example.org")
        tom = make_user("tom@example.org")
        project_id = uuid.uuid4()
        first = _grant(
            luis, roles.PROJECT_LEADER, scope_type=roles.SCOPE_TYPE_PROJECT, scope_id=project_id
        )
        first.revoked_at = clock_now()
        first.save()
        second = _grant(
            tom, roles.PROJECT_LEADER, scope_type=roles.SCOPE_TYPE_PROJECT, scope_id=project_id
        )
        assert second.is_active is True

    def test_rows_are_never_deleted_by_services(self, make_user):
        # Documentation-as-test: identity.services never calls .delete() on RoleAssignment.
        import inspect

        from ham.identity import services

        source = inspect.getsource(services)
        assert ".delete()" not in source
