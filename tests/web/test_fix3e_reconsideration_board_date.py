"""Fix 3E item 3 / UX M7, PRD re-check small items: A9's Board-date future check is inline
(church-local date) and preserves the typed reason on refusal, instead of bouncing to the
generic "someone decided first" redirect and losing what was typed.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse

from ham.authz.context import RequesterContext
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now
from ham.requests.services_decisions import reject_request, request_reconsideration
from ham.requests.states import RequestStatus
from tests.web.test_s36_leadership_screens import _ctx_for, _login, _make_request

pytestmark = pytest.mark.django_db


def _board_reconsideration(client, make_user):
    req = _make_request()
    board_rep = _login(
        client,
        make_user,
        email="board-a9@example.org",
        full_name="Board Nine",
        role="BOARD_REPRESENTATIVE",
    )
    approval = reject_request(
        _ctx_for(board_rep, "BOARD_REPRESENTATIVE"),
        request_id=req.id,
        route="board",
        reason_code="couldnt_confirm",
        message="We couldn't confirm the details.",
    )
    set_clock(FixedClock(approval.effective_at))
    request_reconsideration(RequesterContext(request_id=req.id), note="Please look again.")
    req.refresh_from_db()
    assert req.status == RequestStatus.RECONSIDERATION_PENDING.value
    return req


class TestFutureBoardDateOnReconsiderationSheet:
    def test_future_board_date_is_refused_inline_with_typed_reason_preserved(
        self, client, make_user
    ):
        req = _board_reconsideration(client, make_user)
        future = (clock_now() + timedelta(days=3)).date().isoformat()
        response = client.post(
            reverse("web:request_reconsideration_decide", args=[req.id]),
            {
                "outcome": "approve",
                "reason": "MY-DISTINCTIVE-TYPED-REASON",
                "board_decided_on": future,
            },
        )
        # Refused INLINE (same 200 re-render, never a redirect to the generic
        # "someone decided first" page that would lose the typed text).
        assert response.status_code == 200
        body = response.content.decode()
        assert "can't be in the future" in body
        assert "MY-DISTINCTIVE-TYPED-REASON" in body
        req.refresh_from_db()
        assert req.status == RequestStatus.RECONSIDERATION_PENDING.value
        set_clock(None)

    def test_todays_board_date_is_accepted(self, client, make_user):
        req = _board_reconsideration(client, make_user)
        today = clock_now().date().isoformat()
        response = client.post(
            reverse("web:request_reconsideration_decide", args=[req.id]),
            {
                "outcome": "approve",
                "reason": "A fine reason.",
                "board_decided_on": today,
            },
        )
        assert response.status_code == 302
        set_clock(None)
