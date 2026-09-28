from __future__ import annotations

import uuid

import pytest

from ham.audit.queries import AuditFilter, list_events
from ham.audit.services import record

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = dict(
        ctx=None, actor_type="system", action="user.created", target_type="user", target_id="u1"
    )
    defaults.update(kw)
    return record(**defaults)


class TestFilters:
    def test_filters_by_action(self):
        _event(action="user.created")
        _event(action="user.disabled")
        results = list_events(AuditFilter(action="user.disabled"))
        assert {e.action for e in results} == {"user.disabled"}

    def test_filters_by_project(self):
        project_id = uuid.uuid4()
        _event(project_id=project_id)
        _event(project_id=uuid.uuid4())
        results = list_events(AuditFilter(project_id=project_id))
        assert len(results) == 1
        assert results[0].project_id == project_id

    def test_filters_by_role(self):
        from ham.authz.context import ActorContext

        director_ctx = ActorContext(
            user_id=uuid.uuid4(),
            real_user_id=None,
            roles=frozenset({"HAM_DIRECTOR"}),
            is_active=True,
            mfa_satisfied=True,
        )
        volunteer_ctx = ActorContext(
            user_id=uuid.uuid4(),
            real_user_id=None,
            roles=frozenset({"VOLUNTEER"}),
            is_active=True,
            mfa_satisfied=True,
        )
        record(ctx=director_ctx, action="role.granted", target_type="user", target_id="u1")
        record(ctx=volunteer_ctx, action="profile.updated", target_type="user", target_id="u2")
        results = list_events(AuditFilter(role="HAM_DIRECTOR"))
        assert {e.action for e in results} == {"role.granted"}

    def test_user_filter_matches_actor_or_acting_as(self):
        user_id = uuid.uuid4()
        record(
            ctx=None,
            actor_type="user",
            actor_user_id=user_id,
            action="a",
            target_type="t",
            target_id="1",
        )
        record(
            ctx=None,
            actor_type="user",
            actor_user_id=uuid.uuid4(),
            acting_as_user_id=user_id,
            action="b",
            target_type="t",
            target_id="2",
        )
        results = list_events(AuditFilter(user_id=user_id))
        assert {e.action for e in results} == {"a", "b"}

    def test_pagination_by_seq(self):
        for i in range(5):
            _event(target_id=str(i))
        page1 = list_events(limit=2)
        assert len(page1) == 2
        page2 = list_events(before_seq=page1[-1].seq, limit=2)
        assert page2[0].seq < page1[-1].seq
