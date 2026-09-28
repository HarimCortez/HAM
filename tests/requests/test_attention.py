from __future__ import annotations

import uuid

import pytest

from ham.notifications.attention import attention_items_for
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

    def test_urgent_card_title_includes_waiting_context(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        """FIX-F1 M17 remainder: each per-request urgent card gets a "waiting N h" line, not
        just the aggregate needs-phone-check card."""
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(urgent_requested=True, urgency_justification="Water everywhere"),
        )
        complete_intake_checks(system_ctx, request_id=req.id)
        cards = attention_cards(pastor_ctx)
        urgent_card = next(c for c in cards if c.key == f"requests.awaiting_approval.{req.id}")
        assert "waiting" in urgent_card.title

    def test_urgent_cards_capped_with_a_more_urgent_card(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        """FIX-F1 minor 1: more than `MAX_URGENT_CARDS` urgent+actionable requests fold into
        one "N more urgent" card instead of one primary-button card per request."""
        from ham.requests.attention import MAX_URGENT_CARDS

        for _ in range(MAX_URGENT_CARDS + 2):
            req = submit_request(
                requester_ctx,
                draft_id=uuid.uuid4(),
                verification_id=uuid.uuid4(),
                payload=make_payload(
                    urgent_requested=True, urgency_justification="Water everywhere"
                ),
            )
            complete_intake_checks(system_ctx, request_id=req.id)

        cards = attention_cards(pastor_ctx)
        per_request_cards = [c for c in cards if c.key.startswith("requests.awaiting_approval.")]
        assert len(per_request_cards) == MAX_URGENT_CARDS + 1  # +1 for the "N more urgent" card
        more_card = next(c for c in per_request_cards if c.key.endswith("more_urgent"))
        assert more_card.title == "2 more urgent"
        assert more_card.urgent is True

    def test_registered_with_the_real_notifications_registry(
        self, requester_ctx, system_ctx, pastor_ctx
    ):
        """`RequestsConfig.ready()` actually registered `provide_attention_items` with
        `ham.notifications.attention` (intake-contracts.md §8.3) -- not just a same-module
        function the app forgot to wire up."""
        req = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(),
        )
        complete_intake_checks(system_ctx, request_id=req.id)
        items = attention_items_for(pastor_ctx)
        assert any(item.kind == "requests.awaiting_approval" for item in items)
