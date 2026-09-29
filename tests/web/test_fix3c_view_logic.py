"""Fix 3C: view-level regressions (items 1, 5, 9, and 12's list-row markers)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.platform.clock import FixedClock, set_clock
from ham.requests.services_decisions import (
    decide_reconsideration,
    record_reconsideration_by_phone,
    reject_request,
)
from ham.rules import RULES
from tests.requests.conftest import no_email_payload
from tests.web.test_s36_leadership_screens import (
    _ctx_for,
    _login,
    _make_request,
    _requester_ctx,
    _system_ctx,
)

pytestmark = pytest.mark.django_db


def _make_no_email_request():
    import uuid

    from ham.authz.context import ActorContext
    from ham.requests.services import complete_intake_checks, submit_request

    req = submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=None,
        payload=no_email_payload(),
    )
    from ham.requests.services import verify_by_phone

    verify_by_phone(
        ActorContext(
            user_id=uuid.uuid4(),
            real_user_id=None,
            roles=frozenset({"HAM_DIRECTOR"}),
            is_active=True,
            mfa_satisfied=True,
        ),
        request_id=req.id,
    )
    complete_intake_checks(_system_ctx(), request_id=req.id)
    return req


# ---------------------------------------------------------------------------------------
# Item 1 / security N1: the "Tell by phone" view.
# ---------------------------------------------------------------------------------------
class TestPhonedSheetUsesLatestDecision:
    def test_shows_the_reconsideration_outcome_not_the_initial_decline(self, client, make_user):
        req = _make_no_email_request()
        pastor = _login(client, make_user, email="p1@example.org", full_name="P One", role="PASTOR")
        pastor_ctx = _ctx_for(pastor, "PASTOR")
        first = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="SORRY-INITIAL-DECLINE-TEXT",
        )
        set_clock(FixedClock(first.effective_at + RULES.approvals.DECISION_UNDO_WINDOW))
        director = _login(
            client, make_user, email="d1@example.org", full_name="D One", role="HAM_DIRECTOR"
        )
        record_reconsideration_by_phone(
            _ctx_for(director, "HAM_DIRECTOR"), request_id=req.id, note=""
        )
        second = decide_reconsideration(pastor_ctx, request_id=req.id, approve=True, reason="ok")
        set_clock(FixedClock(second.effective_at + RULES.approvals.DECISION_UNDO_WINDOW))

        response = client.get(reverse("web:request_decision_phoned", args=[req.id]))
        assert response.status_code == 200
        body = response.content.decode()
        assert "SORRY-INITIAL-DECLINE-TEXT" not in body
        assert "has been approved" in body

    def test_404s_while_the_decision_is_still_undoable(self, client, make_user):
        req = _make_no_email_request()
        pastor = _login(client, make_user, email="p2@example.org", full_name="P Two", role="PASTOR")
        reject_request(
            _ctx_for(pastor, "PASTOR"),
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="X-DECLINE",
        )
        _login(client, make_user, email="d2@example.org", full_name="D Two", role="HAM_DIRECTOR")
        response = client.get(reverse("web:request_decision_phoned", args=[req.id]))
        assert response.status_code == 404
        assert "X-DECLINE" not in response.content.decode()

    def test_final_decline_shows_no_reconsider_offer_or_deadline(self, client, make_user):
        req = _make_no_email_request()
        pastor = _login(
            client, make_user, email="p3@example.org", full_name="P Three", role="PASTOR"
        )
        pastor_ctx = _ctx_for(pastor, "PASTOR")
        first = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="FIRST-DECLINE",
        )
        set_clock(FixedClock(first.effective_at + RULES.approvals.DECISION_UNDO_WINDOW))
        director = _login(
            client, make_user, email="d3@example.org", full_name="D Three", role="HAM_DIRECTOR"
        )
        record_reconsideration_by_phone(
            _ctx_for(director, "HAM_DIRECTOR"), request_id=req.id, note=""
        )
        second = decide_reconsideration(
            pastor_ctx,
            request_id=req.id,
            approve=False,
            reason="FINAL-DECLINE",
            reason_code="another_reason",
        )
        set_clock(FixedClock(second.effective_at + RULES.approvals.DECISION_UNDO_WINDOW))

        response = client.get(reverse("web:request_decision_phoned", args=[req.id]))
        assert response.status_code == 200
        body = response.content.decode()
        assert "reconsider" not in body.lower()


# ---------------------------------------------------------------------------------------
# Item 5 / PRD N2: the take-over tick always starts unchecked.
# ---------------------------------------------------------------------------------------
class TestTakeOverTickStartsUnchecked:
    def test_take_over_query_param_does_not_pre_check(self, client, make_user):
        from ham.authz.context import RequesterContext
        from ham.requests.services_decisions import request_reconsideration

        req = _make_request()
        original = _login(
            client, make_user, email="orig@example.org", full_name="Orig Pastor", role="PASTOR"
        )
        first = reject_request(
            _ctx_for(original, "PASTOR"),
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="sorry",
        )
        set_clock(FixedClock(first.effective_at + RULES.approvals.DECISION_UNDO_WINDOW))
        request_reconsideration(RequesterContext(request_id=req.id))

        _login(
            client, make_user, email="other@example.org", full_name="Other Pastor", role="PASTOR"
        )
        response = client.get(
            reverse("web:request_reconsideration_decide", args=[req.id]) + "?take_over=1"
        )
        assert response.status_code == 200
        body = response.content.decode()
        # The checkbox itself must render without a `checked` attribute.
        idx = body.index('name="take_over"')
        snippet = body[max(0, idx - 60) : idx + 60]
        assert "checked" not in snippet


# ---------------------------------------------------------------------------------------
# Item 8 / UX N1: "Show contact details" must never wipe the typed question.
# ---------------------------------------------------------------------------------------
class TestAskSheetShowContactEchoesTypedQuestion:
    def test_show_contact_post_echoes_the_typed_question_back(self, client, make_user):
        req = _make_no_email_request()
        _login(
            client, make_user, email="ask-dir@example.org", full_name="Ask Dir", role="HAM_DIRECTOR"
        )
        response = client.post(
            reverse("web:request_question_ask", args=[req.id]),
            {"question": "DISTINCTIVE TYPED QUESTION", "show_contact": "1"},
        )
        assert response.status_code == 200
        body = response.content.decode()
        assert "DISTINCTIVE TYPED QUESTION" in body
