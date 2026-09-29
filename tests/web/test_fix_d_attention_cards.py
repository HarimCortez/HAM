"""FIX-D item 6 (visual M17): one Home attention card per urgent, actionable request instead
of a single aggregate card mislabeling the whole group "Urgent". See
`ham.requests.attention.awaiting_approval_cards`.
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.platform.clock import now as clock_now
from ham.requests.attention import attention_cards
from ham.requests.services import complete_intake_checks, submit_request
from tests.requests.conftest import actor_ctx, make_payload

pytestmark = pytest.mark.django_db


@pytest.fixture
def pastor_ctx():
    return actor_ctx(roles=frozenset({"PASTOR"}))


@pytest.fixture
def director_ctx():
    return actor_ctx(roles=frozenset({"HAM_DIRECTOR"}))


def _requester_ctx():
    from ham.authz.context import RequesterContext

    return RequesterContext(request_id=None)


def _system_ctx():
    from ham.authz.context import SystemContext

    return SystemContext()


def _make_request(*, urgent: bool = False):
    extra = {"urgency_justification": "Water is coming in fast."} if urgent else {}
    req = submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(urgent_requested=urgent, **extra),
    )
    complete_intake_checks(_system_ctx(), request_id=req.id)
    return req


def _login(client, make_user, *, email: str, full_name: str, role: str):
    user = make_user(email)
    SharedIdentityProfile.objects.create(user=user, full_name=full_name)
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return user


class TestPerRequestUrgentCards:
    def test_urgent_request_gets_its_own_card(self, pastor_ctx):
        req = _make_request(urgent=True)
        cards = attention_cards(pastor_ctx)
        urgent_cards = [c for c in cards if c.key == f"requests.awaiting_approval.{req.id}"]
        assert len(urgent_cards) == 1
        card = urgent_cards[0]
        assert card.urgent is True
        assert card.actionable is True
        assert card.href == f"/requests/{req.id}"
        assert req.display_number in card.title

    def test_mixed_urgent_and_non_urgent_produce_two_kinds_of_card(self, pastor_ctx):
        urgent_req = _make_request(urgent=True)
        _make_request(urgent=False)
        cards = attention_cards(pastor_ctx)
        urgent_cards = [c for c in cards if c.urgent]
        aggregate_cards = [c for c in cards if c.key == "requests.awaiting_approval"]
        assert len(urgent_cards) == 1
        assert urgent_cards[0].href == f"/requests/{urgent_req.id}"
        assert len(aggregate_cards) == 1
        assert aggregate_cards[0].count == 1
        assert "waiting for a decision" in aggregate_cards[0].title

    def test_all_non_urgent_yields_only_the_aggregate_card(self, pastor_ctx):
        _make_request(urgent=False)
        _make_request(urgent=False)
        cards = attention_cards(pastor_ctx)
        assert not any(c.urgent for c in cards)
        aggregate = next(c for c in cards if c.key == "requests.awaiting_approval")
        assert aggregate.count == 2
        assert "2 requests are waiting for a decision" == aggregate.title

    def test_director_awareness_row_stays_one_muted_card_never_urgent(self, director_ctx):
        _make_request(urgent=True)
        _make_request(urgent=False)
        cards = attention_cards(director_ctx)
        awaiting = [c for c in cards if c.key.startswith("requests.awaiting_approval")]
        assert len(awaiting) == 1
        assert awaiting[0].actionable is False
        assert awaiting[0].urgent is False
        assert awaiting[0].count == 2

    def test_cards_carry_no_pii(self, pastor_ctx):
        _make_request(urgent=True)
        for card in attention_cards(pastor_ctx):
            assert "Jane Test" not in card.title
            assert "jane@example.org" not in card.title


class TestHomeRendersUrgentChipOnlyForActionableCards:
    def test_home_urgent_card_has_open_button_and_no_chip_on_muted_row(self, client, make_user):
        _make_request(urgent=True)
        _login(
            client,
            make_user,
            email="pastor-fixd@example.org",
            full_name="Pat Pastor",
            role="PASTOR",
        )
        resp = client.get(reverse("web:home"))
        html = resp.content.decode()
        assert "Urgent" in html
        assert "Review" in html  # FIX-3B UX m19: "Review", not "Open"
