"""FIX-3D hand-back item 2: the "Urgent request needs a pastor" wording is pastor-only --
Director/AD/Board rep get a factually-accurate update instead of a title that addresses a
role they don't hold.
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.identity.models import RoleAssignment
from ham.outbox.models import OutboxEvent
from ham.platform.clock import now as clock_now
from ham.requests.notifications import _build_awaiting_approval_notices
from ham.requests.services import submit_request

from .conftest import make_payload

pytestmark = pytest.mark.django_db


def _grant(user, role):
    return RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())


def _event(event_type: str, *, aggregate_id, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type, aggregate_type="request", aggregate_id=aggregate_id, payload=payload
    )


class TestDirectorGetsAFactualTitleNotThePastorWording:
    def test_urgent_case(self, requester_ctx, make_user):
        pastor = make_user("ruth-pastor@example.org")
        _grant(pastor, roles.PASTOR)
        director = make_user("nadia-director@example.org")
        _grant(director, roles.HAM_DIRECTOR)

        request = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(urgent_requested=True, urgency_justification="x"),
        )
        event = _event("RequestAwaitingApproval", aggregate_id=request.id, payload={"urgent": True})
        notices = _build_awaiting_approval_notices(event)
        assert notices is not None

        pastor_notice = next(n for n in notices if n.recipient_user_id == pastor.id)
        director_notice = next(n for n in notices if n.recipient_user_id == director.id)

        assert pastor_notice.title.startswith("Urgent request needs a pastor")
        assert not director_notice.title.startswith("Urgent request needs a pastor")
        assert "needs a pastor" not in director_notice.title
        assert request.display_number in director_notice.title
