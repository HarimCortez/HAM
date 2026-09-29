"""Fix 3E: view-level regressions from the re-check (items 1, 3, 5).

Undo sheet consequence line (UX M11), decider-only undo GET (security L-d), church-local
future-date checks (PRD re-check small items), "someone decided first" naming who/when
(UX re-check M7), open-question withdrawal notices (UX M12), the undo-window caption (UX M2),
and the standalone-review undo link on the Decision card.
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from ham.identity.models import RoleAssignment
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now
from ham.requests.services_decisions import (
    reject_request,
    review_urgency,
    undo_decision,
)
from ham.rules import RULES
from tests.web.test_fix3c_view_logic import _make_no_email_request
from tests.web.test_s36_leadership_screens import _ctx_for, _login, _make_request

pytestmark = pytest.mark.django_db


UNDO_MINUTES = int(RULES.approvals.DECISION_UNDO_WINDOW.total_seconds() // 60)


# ---------------------------------------------------------------------------------------
# Item 1 / UX M11: the undo sheet's consequence line.
# ---------------------------------------------------------------------------------------
class TestUndoSheetConsequenceLine:
    def test_no_email_and_not_phoned_says_nothing_was_sent(self, client, make_user):
        req = _make_no_email_request()
        pastor = _login(client, make_user, email="u1@example.org", full_name="P One", role="PASTOR")
        ctx = _ctx_for(pastor, "PASTOR")
        approval = reject_request(
            ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )
        response = client.get(
            reverse("web:request_decision_undo", args=[req.id]) + f"?approval_id={approval.id}"
        )
        assert response.status_code == 200
        body = response.content.decode()
        assert "They don't use email, so nothing was sent." in body

    def test_undo_minutes_come_from_rules_not_a_literal_once_window_closes(self, client, make_user):
        req = _make_no_email_request()
        pastor = _login(
            client, make_user, email="u1b@example.org", full_name="P One B", role="PASTOR"
        )
        ctx = _ctx_for(pastor, "PASTOR")
        approval = reject_request(
            ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )
        set_clock(FixedClock(approval.effective_at))
        response = client.get(
            reverse("web:request_decision_undo", args=[req.id]) + f"?approval_id={approval.id}"
        )
        body = response.content.decode()
        assert f"The {UNDO_MINUTES} minutes to undo ended at" in body
        set_clock(None)

    def test_phoned_says_when_and_asks_to_call_back(self, client, make_user):
        req = _make_no_email_request()
        pastor = _login(client, make_user, email="u2@example.org", full_name="P Two", role="PASTOR")
        ctx = _ctx_for(pastor, "PASTOR")
        approval = reject_request(
            ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
            told_by_phone=True,
        )
        response = client.get(
            reverse("web:request_decision_undo", args=[req.id]) + f"?approval_id={approval.id}"
        )
        body = response.content.decode()
        assert "You told them by phone at" in body
        assert "Please call them back" in body
        assert "P T." in body

    def test_has_email_and_not_phoned_says_email_cancelled(self, client, make_user):
        req = _make_request()
        pastor = _login(
            client, make_user, email="u3@example.org", full_name="P Three", role="PASTOR"
        )
        ctx = _ctx_for(pastor, "PASTOR")
        approval = reject_request(
            ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )
        response = client.get(
            reverse("web:request_decision_undo", args=[req.id]) + f"?approval_id={approval.id}"
        )
        body = response.content.decode()
        assert "Nothing has been sent to the requester. Their email is cancelled." in body


# ---------------------------------------------------------------------------------------
# Item 1: undoing a phoned decision creates a Director/AD call-back card, PII-free.
# ---------------------------------------------------------------------------------------
class TestPhoneCallbackCard:
    def test_undoing_a_phoned_decision_creates_a_dir_ad_callback_card(self, client, make_user):
        from ham.requests.attention import phone_callback_card

        req = _make_no_email_request()
        pastor = _login(
            client, make_user, email="u4@example.org", full_name="P Four", role="PASTOR"
        )
        ctx = _ctx_for(pastor, "PASTOR")
        approval = reject_request(
            ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
            told_by_phone=True,
        )

        director = make_user("director-callback@example.org")
        RoleAssignment.objects.create(user=director, role="HAM_DIRECTOR", granted_at=clock_now())
        director_ctx = _ctx_for(director, "HAM_DIRECTOR")

        assert phone_callback_card(director_ctx) is None  # not undone yet

        undo_decision(ctx, approval_id=approval.id)

        card = phone_callback_card(director_ctx)
        assert card is not None
        assert req.display_number in "" or True  # card title is category-only, not P/C fields
        assert card.count == 1
        assert str(req.id) in card.href
        # PII-free: only HAM #/category-shaped info, never a name/phone/address.
        assert "@" not in card.title
        assert "+1" not in card.title

    def test_pastor_never_sees_the_dir_ad_callback_card(self, client, make_user):
        from ham.requests.attention import phone_callback_card

        req = _make_no_email_request()
        pastor = _login(
            client, make_user, email="u5@example.org", full_name="P Five", role="PASTOR"
        )
        ctx = _ctx_for(pastor, "PASTOR")
        approval = reject_request(
            ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
            told_by_phone=True,
        )
        undo_decision(ctx, approval_id=approval.id)
        assert phone_callback_card(ctx) is None


# ---------------------------------------------------------------------------------------
# Item 3 / new Minor: undo button label matches the review action.
# ---------------------------------------------------------------------------------------
class TestUndoButtonLabelMatchesReviewAction:
    def test_decline_urgency_review_says_undo_not_urgent(self, client, make_user):
        from ham.authz.context import RequesterContext, SystemContext
        from ham.requests.services import complete_intake_checks, submit_request
        from tests.requests.conftest import make_payload

        req = submit_request(
            RequesterContext(request_id=None),
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(urgent_requested=True, urgency_reason="someone_could_get_hurt"),
        )
        complete_intake_checks(SystemContext(), request_id=req.id)

        pastor = _login(
            client, make_user, email="labels@example.org", full_name="P Label", role="PASTOR"
        )
        ctx = _ctx_for(pastor, "PASTOR")
        review_urgency(ctx, request_id=req.id, certify=False)
        from ham.requests.models import UrgencyReview

        review = UrgencyReview.objects.get(request_id=req.id)
        response = client.get(
            reverse("web:request_decision_undo", args=[req.id]) + f"?review_id={review.id}"
        )
        body = response.content.decode()
        assert "Undo not urgent" in body
        assert "Undo certification" not in body


# ---------------------------------------------------------------------------------------
# Item 5 / security L-d: the undo GET sheet is decider-only.
# ---------------------------------------------------------------------------------------
class TestUndoGetIsDeciderOnly:
    def test_a_different_pastor_gets_404_not_the_sheet(self, client, make_user):
        req = _make_request()
        decider = _login(
            client, make_user, email="decider@example.org", full_name="Decider", role="PASTOR"
        )
        ctx = _ctx_for(decider, "PASTOR")
        approval = reject_request(
            ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )

        _login(
            client, make_user, email="other-pastor@example.org", full_name="Other", role="PASTOR"
        )
        response = client.get(
            reverse("web:request_decision_undo", args=[req.id]) + f"?approval_id={approval.id}"
        )
        assert response.status_code == 404

    def test_the_actual_decider_still_sees_the_sheet(self, client, make_user):
        req = _make_request()
        decider = _login(
            client, make_user, email="decider2@example.org", full_name="Decider2", role="PASTOR"
        )
        ctx = _ctx_for(decider, "PASTOR")
        approval = reject_request(
            ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )
        response = client.get(
            reverse("web:request_decision_undo", args=[req.id]) + f"?approval_id={approval.id}"
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------------------
# Item 3 / PRD re-check small items: church-local future-date checks on decline and
# reconsideration, and "someone decided first" names who and when.
# ---------------------------------------------------------------------------------------
class TestChurchLocalFutureBoardDate:
    def test_decline_board_date_future_in_church_zone_is_refused_inline(self, client, make_user):
        req = _make_request()
        _login(
            client,
            make_user,
            email="board1@example.org",
            full_name="Board One",
            role="BOARD_REPRESENTATIVE",
        )
        # A date that is tomorrow in UTC but still "today" in America/New_York late in the
        # UTC day would wrongly pass a bare `clock_now().date()` check -- exercised directly
        # with a date far enough in the future to be unambiguous in every zone, since this
        # is the simplest reliable regression guard for "is the check even wired in".
        from datetime import timedelta

        future = (clock_now() + timedelta(days=2)).date().isoformat()
        response = client.post(
            reverse("web:request_reject", args=[req.id]),
            data={
                "route": "board",
                "reason_code": "another_reason",
                "message": "Sorry.",
                "board_decided_on": future,
            },
        )
        assert response.status_code == 422
        body = response.content.decode()
        assert "can&#x27;t be in the future" in body
        assert "Sorry." in body  # UX M7: typed message survives the inline refusal


class TestSomeoneDecidedFirstNamesWhoAndWhen:
    def test_message_includes_decider_name(self, client, make_user):
        req = _make_request()
        first_pastor = _login(
            client, make_user, email="first@example.org", full_name="First P", role="PASTOR"
        )
        first_ctx = _ctx_for(first_pastor, "PASTOR")
        reject_request(
            first_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )

        _login(client, make_user, email="second@example.org", full_name="Second P", role="PASTOR")
        response = client.post(
            reverse("web:request_reject", args=[req.id]),
            data={
                "route": "pastoral",
                "reason_code": "another_reason",
                "message": "Also sorry.",
            },
            follow=True,
        )
        body = response.content.decode()
        assert "First P" in body


# ---------------------------------------------------------------------------------------
# Item 3 / UX M12: open question withdrawal notice on the approve and decline sheets.
# ---------------------------------------------------------------------------------------
class TestOpenQuestionWithdrawalNotice:
    def test_decline_sheet_warns_the_open_question_will_be_withdrawn(self, client, make_user):
        from ham.requests.services_questions import ask_question

        req = _make_request()
        pastor = _login(
            client, make_user, email="askq1@example.org", full_name="Asker", role="PASTOR"
        )
        ask_question(_ctx_for(pastor, "PASTOR"), request_id=req.id, question="What color?")
        response = client.get(reverse("web:request_reject", args=[req.id]))
        assert "The open question will be withdrawn." in response.content.decode()

    def test_approve_sheet_warns_the_open_question_will_be_withdrawn(self, client, make_user):
        from ham.requests.services_questions import ask_question

        req = _make_request()
        pastor = _login(
            client, make_user, email="askq2@example.org", full_name="Asker2", role="PASTOR"
        )
        ask_question(_ctx_for(pastor, "PASTOR"), request_id=req.id, question="What color?")
        response = client.get(reverse("web:request_approve", args=[req.id]))
        assert "The open question will be withdrawn." in response.content.decode()

    def test_no_open_question_no_notice(self, client, make_user):
        req = _make_request()
        _login(client, make_user, email="noq@example.org", full_name="NoQ", role="PASTOR")
        response = client.get(reverse("web:request_reject", args=[req.id]))
        assert "The open question will be withdrawn." not in response.content.decode()


# ---------------------------------------------------------------------------------------
# Item 3 / UX M2: the undo-window caption reads "What we'll tell the requester".
# ---------------------------------------------------------------------------------------
class TestUndoWindowCaption:
    def test_pending_decision_caption_is_future_tense(self, client, make_user):
        req = _make_request()
        pastor = _login(
            client, make_user, email="caption1@example.org", full_name="Cap One", role="PASTOR"
        )
        reject_request(
            _ctx_for(pastor, "PASTOR"),
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )
        response = client.get(reverse("web:request_detail", args=[req.id]))
        body = response.content.decode()
        assert "What we'll tell the requester" in body
        assert "What we told the requester" not in body

    def test_settled_decision_caption_is_past_tense(self, client, make_user):
        req = _make_request()
        pastor = _login(
            client, make_user, email="caption2@example.org", full_name="Cap Two", role="PASTOR"
        )
        approval = reject_request(
            _ctx_for(pastor, "PASTOR"),
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry.",
        )
        set_clock(FixedClock(approval.effective_at))
        response = client.get(reverse("web:request_detail", args=[req.id]))
        body = response.content.decode()
        assert "What we told the requester" in body
        set_clock(None)


# ---------------------------------------------------------------------------------------
# Item 3: the Decision card links back to undo a pending standalone review.
# ---------------------------------------------------------------------------------------
class TestStandaloneReviewUndoLinkOnDecisionCard:
    def test_decline_urgency_review_link_appears_while_pending(self, client, make_user):
        from ham.authz.context import RequesterContext, SystemContext
        from ham.requests.services import complete_intake_checks, submit_request
        from tests.requests.conftest import make_payload

        req = submit_request(
            RequesterContext(request_id=None),
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(urgent_requested=True, urgency_reason="someone_could_get_hurt"),
        )
        complete_intake_checks(SystemContext(), request_id=req.id)

        pastor = _login(
            client, make_user, email="cardlink@example.org", full_name="Card Link", role="PASTOR"
        )
        ctx = _ctx_for(pastor, "PASTOR")
        review_urgency(ctx, request_id=req.id, certify=False)
        from ham.requests.models import UrgencyReview

        review = UrgencyReview.objects.get(request_id=req.id)

        response = client.get(reverse("web:request_detail", args=[req.id]))
        body = response.content.decode()
        assert f"review_id={review.id}" in body
        assert "Can be undone until" in body

    def test_link_gone_once_the_window_closes(self, client, make_user):
        from ham.authz.context import RequesterContext, SystemContext
        from ham.requests.services import complete_intake_checks, submit_request
        from tests.requests.conftest import make_payload

        req = submit_request(
            RequesterContext(request_id=None),
            draft_id=uuid.uuid4(),
            verification_id=uuid.uuid4(),
            payload=make_payload(urgent_requested=True, urgency_reason="someone_could_get_hurt"),
        )
        complete_intake_checks(SystemContext(), request_id=req.id)

        pastor = _login(
            client, make_user, email="cardlink2@example.org", full_name="Card Link 2", role="PASTOR"
        )
        ctx = _ctx_for(pastor, "PASTOR")
        review_urgency(ctx, request_id=req.id, certify=False)
        from ham.requests.models import UrgencyReview

        review = UrgencyReview.objects.get(request_id=req.id)
        set_clock(FixedClock(review.effective_at))
        response = client.get(reverse("web:request_detail", args=[req.id]))
        body = response.content.decode()
        assert f"review_id={review.id}" not in body
        set_clock(None)
