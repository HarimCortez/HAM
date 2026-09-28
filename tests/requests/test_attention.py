from __future__ import annotations

import uuid

import pytest

from ham.requests.attention import attention_cards
from ham.requests.services import complete_intake_checks, submit_request

from .conftest import make_payload, no_email_payload

pytestmark = pytest.mark.django_db


class TestAttentionCards:
    def test_pastor_sees_awaiting_approval_actionable(self, requester_ctx, system_ctx, pastor_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=req.id)
        cards = attention_cards(pastor_ctx)
        awaiting = next(c for c in cards if c.key == "requests.awaiting_approval")
        assert awaiting.actionable is True
        assert awaiting.count == 1

    def test_director_sees_awaiting_approval_as_muted_awareness(
        self, requester_ctx, system_ctx, director_ctx
    ):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=req.id)
        cards = attention_cards(director_ctx)
        awaiting = next(c for c in cards if c.key == "requests.awaiting_approval")
        assert awaiting.actionable is False

    def test_needs_phone_check_card_only_for_director_and_ad(
        self, requester_ctx, director_ctx, pastor_ctx
    ):
        submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        cards = attention_cards(director_ctx)
        assert any(c.key == "requests.needs_phone_check" for c in cards)
        assert not any(c.key == "requests.needs_phone_check" for c in attention_cards(pastor_ctx))

    def test_no_cards_when_nothing_pending(self, pastor_ctx):
        assert attention_cards(pastor_ctx) == []

    def test_cards_carry_no_pii(self, requester_ctx, system_ctx, pastor_ctx):
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=req.id)
        for card in attention_cards(pastor_ctx):
            assert "jane@example.org" not in card.title
            assert "Jane Test" not in card.title
