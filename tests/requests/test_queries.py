"""S2.2: list/detail queries, the Administrator's masked projection, the Needs-phone-check
list, `scope_queryset`, and `outcome_summary`.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from ham.authz.scopes import scope_queryset
from ham.requests.models import AssistanceRequest
from ham.requests.queries import (
    get_request_detail,
    list_requests,
    needs_phone_check_list,
    outcome_summary,
)
from ham.requests.services import complete_intake_checks, submit_request

from .conftest import make_payload, no_email_payload

pytestmark = pytest.mark.django_db


def _submitted(requester_ctx, **overrides):
    return submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**overrides),
    )


class TestListRequests:
    def test_needs_phone_check_hidden_from_pastor_and_board_and_admin(
        self, requester_ctx, pastor_ctx, board_rep_ctx, administrator_ctx, director_ctx
    ):
        submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        for ctx in (pastor_ctx, board_rep_ctx, administrator_ctx):
            rows = list_requests(ctx)
            assert all(r.status != "NEEDS_PHONE_CHECK" for r in rows)
        rows = list_requests(director_ctx)
        assert any(r.status == "NEEDS_PHONE_CHECK" for r in rows)

    def test_list_rows_carry_no_pii(self, requester_ctx, director_ctx):
        _submitted(requester_ctx)
        rows = list_requests(director_ctx)
        for row in rows:
            text = str(dataclasses.asdict(row))
            assert "jane@example.org" not in text
            assert "Jane Test" not in text

    def test_urgent_first_ordering(self, requester_ctx, director_ctx):
        submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(full_name="Calm Person", email="calm@example.org"),
        )
        submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(
                full_name="Urgent Person",
                email="urgent@example.org",
                urgent_requested=True,
                urgency_justification="Water everywhere.",
            ),
        )
        rows = list_requests(director_ctx)
        assert rows[0].urgent_requested is True

    def test_scope_queryset_registered_for_request_list(self, requester_ctx, pastor_ctx):
        submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        filtered = scope_queryset(pastor_ctx, "request.list", AssistanceRequest.objects.all())
        assert not filtered.filter(status="NEEDS_PHONE_CHECK").exists()


class TestNeedsPhoneCheckList:
    def test_only_director_and_ad_see_it(
        self, requester_ctx, director_ctx, assistant_director_ctx, pastor_ctx, administrator_ctx
    ):
        submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=no_email_payload(),
        )
        assert len(needs_phone_check_list(director_ctx)) == 1
        assert len(needs_phone_check_list(assistant_director_ctx)) == 1
        assert needs_phone_check_list(pastor_ctx) == []
        assert needs_phone_check_list(administrator_ctx) == []


class TestRequestDetail:
    def test_administrator_gets_masked_photo_count_only_view(
        self, requester_ctx, administrator_ctx
    ):
        req = _submitted(requester_ctx)
        detail = get_request_detail(administrator_ctx, req.id)
        assert detail is not None
        assert detail.is_masked_view is True
        assert detail.can_reveal_contact is False
        assert detail.photo_count_only is True
        assert "Jane" not in str(dataclasses.asdict(detail))

    def test_director_gets_reveal_capability_not_masked(self, requester_ctx, director_ctx):
        req = _submitted(requester_ctx)
        detail = get_request_detail(director_ctx, req.id)
        assert detail is not None
        assert detail.is_masked_view is False
        assert detail.can_reveal_contact is True

    def test_unknown_request_returns_none(self, director_ctx):
        assert get_request_detail(director_ctx, uuid.uuid4()) is None


class TestOutcomeSummary:
    def test_lists_prior_matches_newest_first(self, requester_ctx, system_ctx):
        first = _submitted(requester_ctx)
        complete_intake_checks(system_ctx, request_id=first.id)
        second = submit_request(
            requester_ctx,
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(
                full_name="Someone Else", email="someone@example.org", phone="+13055559999"
            ),
        )
        complete_intake_checks(system_ctx, request_id=second.id)
        second.refresh_from_db()
        summary = outcome_summary(second)
        assert len(summary) == 1
        assert summary[0].request_id == first.id
        assert summary[0].reasons == ("address",)

    def test_no_matches_is_empty(self, requester_ctx):
        req = _submitted(requester_ctx)
        assert outcome_summary(req) == []
