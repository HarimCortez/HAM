from __future__ import annotations

import pytest

from ham.audit.models import AuditEvent
from ham.audit.queries import AuditFilter
from ham.authz import roles
from ham.authz.audit_access import export_csv, list_events
from ham.authz.commands import PermissionDenied, StepUpRequired
from ham.authz.context import ActorContext
from ham.identity.models import RoleAssignment
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db


def _grant(user, role):
    return RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


def _ctx(user, roles_, **overrides):
    defaults = dict(
        user_id=user.id,
        real_user_id=None,
        roles=frozenset(roles_),
        is_active=True,
        mfa_satisfied=True,
    )
    defaults.update(overrides)
    return ActorContext(**defaults)


class TestListEvents:
    def test_director_can_view(self, make_user):
        marcus = make_user("marcus@example.org")
        _grant(marcus, roles.HAM_DIRECTOR)
        assert list_events(_ctx(marcus, {roles.HAM_DIRECTOR})) == []

    def test_volunteer_cannot_view(self, make_user):
        kevin = make_user("kevin@example.org")
        _grant(kevin, roles.VOLUNTEER)
        with pytest.raises(PermissionDenied):
            list_events(_ctx(kevin, {roles.VOLUNTEER}))


class TestExportCsv:
    def test_export_requires_step_up(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        ctx = _ctx(admin, {roles.ADMINISTRATOR}, step_up_at={})
        with pytest.raises(StepUpRequired):
            export_csv(ctx)

    def test_export_writes_audit_exported_event(self, make_user):
        admin = make_user("nadia@example.org")
        _grant(admin, roles.ADMINISTRATOR)
        ctx = _ctx(admin, {roles.ADMINISTRATOR}, step_up_at={"audit_export": clock_now()})
        data = export_csv(ctx, AuditFilter())
        assert data.startswith(b"\xef\xbb\xbf")
        assert AuditEvent.objects.filter(action="audit.exported").exists()

    def test_export_denied_for_non_privileged_role(self, make_user):
        kevin = make_user("kevin@example.org")
        _grant(kevin, roles.VOLUNTEER)
        with pytest.raises(PermissionDenied):
            export_csv(_ctx(kevin, {roles.VOLUNTEER}))
