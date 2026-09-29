"""FIX-3D hand-back item 1 (UX/visual M12): `reconsideration_cards`, `pastor_certify_card` and
`decision_phone_card` return one card per request (HAM # + category, straight to it), capped
at `MAX_URGENT_CARDS` like the step-2 urgent cards.
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.platform.clock import FixedClock, set_clock
from ham.requests.attention import (
    MAX_URGENT_CARDS,
    decision_phone_card,
    pastor_certify_card,
    reconsideration_cards,
)
from ham.requests.services import complete_intake_checks, submit_request, verify_by_phone
from ham.requests.services_decisions import approve_request, reject_request

from .conftest import actor_ctx, make_payload, no_email_payload
from .test_s32_decisions import _urgent_awaiting

pytestmark = pytest.mark.django_db


def _settled_reject(requester_ctx, system_ctx, ctx, **payload_overrides):
    req = submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**payload_overrides),
    )
    complete_intake_checks(system_ctx, request_id=req.id)
    approval = reject_request(
        ctx,
        request_id=req.id,
        route="pastoral",
        reason_code="another_reason",
        message="Sorry.",
    )
    set_clock(FixedClock(approval.effective_at))
    return req


class TestDecisionPhoneCardPerRequest:
    def test_one_card_per_no_email_request_with_ham_number_and_category(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
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
        cards = decision_phone_card(director_ctx)
        assert len(cards) == 1
        card = cards[0]
        assert req.display_number in card.title
        assert card.href == f"/requests/{req.id}"
        assert card.count == 1
        set_clock(None)

    def test_capped_at_three_then_a_more_card(
        self, requester_ctx, system_ctx, pastor_ctx, director_ctx
    ):
        reqs = []
        for i in range(MAX_URGENT_CARDS + 2):
            req = submit_request(
                requester_ctx,
                draft_id=uuid.uuid4(),
                verification_id=uuid.uuid4(),
                payload=no_email_payload(phone=f"+1305555{1000 + i}"),
            )
            verify_by_phone(director_ctx, request_id=req.id)
            complete_intake_checks(system_ctx, request_id=req.id)
            approval = reject_request(
                pastor_ctx,
                request_id=req.id,
                route="pastoral",
                reason_code="another_reason",
                message="Sorry.",
            )
            reqs.append((req, approval))
        # Settle every decision at once (same instant is fine -- each has its own effective_at).
        latest_effective = max(a.effective_at for _, a in reqs)
        set_clock(FixedClock(latest_effective))
        cards = decision_phone_card(director_ctx)
        assert len(cards) == MAX_URGENT_CARDS + 1  # 3 individual + 1 "more"
        individual = [c for c in cards if c.count == 1]
        more = [c for c in cards if c.count != 1]
        assert len(individual) == MAX_URGENT_CARDS
        assert len(more) == 1
        assert more[0].count == 2
        assert "more" in more[0].title
        set_clock(None)

    def test_never_shown_to_a_pastor(self, requester_ctx, system_ctx, pastor_ctx, director_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
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
        assert decision_phone_card(pastor_ctx) == []
        set_clock(None)


class TestPastorCertifyCardPerRequest:
    def test_one_card_per_request_with_ham_number_and_category(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        board_ctx = actor_ctx(roles=frozenset({roles.BOARD_REPRESENTATIVE}))
        req = _urgent_awaiting(requester_ctx, system_ctx)
        approval = approve_request(board_ctx, request_id=req.id, route="board")
        set_clock(FixedClock(approval.effective_at))
        cards = pastor_certify_card(pastor_ctx)
        assert len(cards) == 1
        assert req.display_number in cards[0].title
        assert cards[0].urgent is True
        set_clock(None)


class TestReconsiderationCardsPerRequest:
    def test_one_card_per_reconsideration_assigned_to_her(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        from ham.authz.context import RequesterContext
        from ham.requests.services_decisions import request_reconsideration

        req = _settled_reject(requester_ctx, system_ctx, pastor_ctx)
        request_reconsideration(RequesterContext(request_id=req.id), note="Please look again")
        cards = reconsideration_cards(pastor_ctx)
        assert len(cards) == 1
        assert req.display_number in cards[0].title
        assert cards[0].href == f"/requests/{req.id}"
        set_clock(None)
