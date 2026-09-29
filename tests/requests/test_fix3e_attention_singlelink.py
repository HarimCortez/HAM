"""Fix 3E / UX M1: a Home card whose count has settled to exactly one deep-links straight to
that request, instead of the whole tab.
"""

from __future__ import annotations

import uuid

import pytest

from ham.platform.clock import FixedClock, set_clock
from ham.requests.attention import (
    awaiting_approval_cards,
    decision_phone_card,
    pastor_certify_card,
    reconsideration_cards,
)
from ham.requests.services import complete_intake_checks, submit_request
from ham.requests.services_decisions import approve_request, reject_request

from .conftest import make_payload, no_email_payload
from .test_s32_decisions import _urgent_awaiting

pytestmark = pytest.mark.django_db


class TestAwaitingApprovalAggregateSingleLink:
    def test_one_non_urgent_request_links_straight_to_it(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=req.id)
        cards = awaiting_approval_cards(pastor_ctx)
        aggregate = next(c for c in cards if c.key == "requests.awaiting_approval")
        assert aggregate.href == f"/requests/{req.id}"

    def test_two_non_urgent_requests_link_to_the_tab(self, requester_ctx, system_ctx, pastor_ctx):
        for _ in range(2):
            req = submit_request(
                requester_ctx,
                draft_id=uuid.uuid4(),
                verification_id=uuid.uuid4(),
                payload=make_payload(),
            )
            complete_intake_checks(system_ctx, request_id=req.id)
        cards = awaiting_approval_cards(pastor_ctx)
        aggregate = next(c for c in cards if c.key == "requests.awaiting_approval")
        assert aggregate.href == "/requests?tab=awaiting"


class TestReconsiderationCardSingleLink:
    def test_one_reconsideration_links_straight_to_it(self, requester_ctx, system_ctx, pastor_ctx):
        from ham.authz.context import RequesterContext

        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=req.id)
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )
        set_clock(FixedClock(approval.effective_at))
        from ham.requests.services_decisions import request_reconsideration

        request_reconsideration(RequesterContext(request_id=req.id), note="Please look again")
        cards = reconsideration_cards(pastor_ctx)
        card = next(c for c in cards if c.key == "requests.reconsideration")
        assert card.href == f"/requests/{req.id}"
        set_clock(None)


class TestDecisionPhoneCardSingleLink:
    def test_one_no_email_settled_decision_links_straight_to_it(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        from ham.requests.services import verify_by_phone

        verify_by_phone(director_ctx, request_id=req.id)
        complete_intake_checks(system_ctx, request_id=req.id)
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )
        set_clock(FixedClock(approval.effective_at))
        card = decision_phone_card(director_ctx)
        assert card is not None
        assert card.href == f"/requests/{req.id}"
        set_clock(None)


class TestPastorCertifyCardSingleLink:
    def test_one_board_approved_urgent_awaiting_certification_links_straight_to_it(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        from ham.authz import roles

        from .conftest import actor_ctx

        board_ctx = actor_ctx(roles=frozenset({roles.BOARD_REPRESENTATIVE}))
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(board_ctx, request_id=req.id, route="board")
        set_clock(FixedClock(approval.effective_at))
        card = pastor_certify_card(pastor_ctx)
        assert card is not None
        assert card.href == f"/requests/{req.id}"
        set_clock(None)
