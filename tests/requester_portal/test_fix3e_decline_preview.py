"""Fix 3E item 2 (UX M6, PRD guardian minor 1): one shared builder for the decline preview
(`ham.requests.presentation.decline_outcome_text`/`render_decline_outcome_text`) and the E10/
E13 email -- both the leadership A3 preview and the requester email render the same three
parts, and the "Here's why: ...." double-punctuation is gone.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.authz.context import RequesterContext
from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal.notifications import _build_rejected_email
from ham.requests.presentation import decline_outcome_text, render_decline_outcome_text
from ham.requests.services_decisions import (
    decide_reconsideration,
    reject_request,
    request_reconsideration,
)
from tests.requester_portal.test_s35_notifications import _awaiting, _event
from tests.web.test_s36_leadership_screens import _ctx_for, _login

pytestmark = pytest.mark.django_db


@pytest.fixture
def requester_ctx():
    return RequesterContext(request_id=None)


@pytest.fixture
def system_ctx():
    from ham.authz.context import SystemContext

    return SystemContext()


@pytest.fixture
def pastor_ctx():
    from tests.requests.conftest import actor_ctx

    return actor_ctx(roles=frozenset({"PASTOR"}))


@pytest.fixture(autouse=True)
def _real_portal_lookups(real_portal_lookups):
    """See `tests/requester_portal/test_notifications.py`'s identical fixture."""


class TestDeclineOutcomeTextParts:
    def test_no_double_punctuation_when_message_already_ends_in_a_period(self):
        parts = decline_outcome_text("We could not confirm what was needed.", final=False)
        rendered = render_decline_outcome_text(parts)
        assert ".." not in rendered
        assert '".' not in rendered.replace('."', "", 1)
        assert 'Here\'s why: "We could not confirm what was needed."' in rendered

    def test_no_double_punctuation_message_without_trailing_period(self):
        parts = decline_outcome_text("Owner is responsible", final=False)
        rendered = render_decline_outcome_text(parts)
        assert 'Here\'s why: "Owner is responsible."' in rendered

    def test_closing_carries_the_sympathy_line_non_final(self):
        parts = decline_outcome_text("A reason", final=False, deadline_text="Tue, Oct 20")
        assert "We know this isn't the answer you hoped for." in parts.closing
        assert "once, until Tue, Oct 20" in parts.closing

    def test_final_closing_has_no_sympathy_line_but_invites_a_new_request(self):
        parts = decline_outcome_text("A reason", final=True)
        assert "welcome to send a new request" in parts.closing
        assert "We know this isn't the answer" not in parts.closing


class TestPreviewMatchesEmailInitialStage:
    def test_preview_equals_email_for_every_reason_initial_stage(
        self, requester_ctx, system_ctx, pastor_ctx, client, make_user
    ):
        reasons = [
            ("family_or_others_can_help", "Family or others can help with this."),
            ("owner_or_landlord_responsible", "The owner or landlord is responsible."),
            ("not_help_ham_offers", "Not the kind of work HAM does."),
            ("couldnt_confirm", "We could not confirm what was needed."),
            ("another_reason", "A different reason entirely."),
        ]
        for reason_code, message in reasons:
            req = _awaiting(requester_ctx, system_ctx)
            pastor = _login(
                client,
                make_user,
                email=f"pastor-{reason_code}@example.org",
                full_name="P One",
                role="PASTOR",
            )
            # A POST missing `route` is refused inline (422 re-render) WITHOUT recording any
            # decision -- this is the one way to see the A3 preview for an exact reason +
            # message combo without also committing the decision, so the request is still
            # available afterward for `_build_rejected_email`'s own real decision.
            response = client.post(
                reverse("web:request_reject", args=[req.id]),
                data={"reason_code": reason_code, "message": message},
            )
            assert response.status_code == 422
            body = response.content.decode()
            preview_opening = decline_outcome_text(message, final=False).opening
            expected = (preview_opening[0].upper() + preview_opening[1:]).replace("'", "&#x27;")
            assert expected in body
            assert message in body

            pastor_ctx_here = _ctx_for(pastor, "PASTOR")
            reject_request(
                pastor_ctx_here,
                request_id=req.id,
                route="pastoral",
                reason_code=reason_code,
                message=message,
            )
            req.refresh_from_db()
            event = _event(
                "RequestRejected",
                aggregate_id=req.id,
                payload={
                    "request_id": str(req.id),
                    "stage": "initial",
                    "route": "pastoral",
                    "reason_code": reason_code,
                    "final": False,
                },
            )
            email = _build_rejected_email(event)
            assert email is not None
            assert message in email.text_body


class TestPreviewMatchesEmailFinalStage:
    def test_preview_parts_match_email_final_stage(self, requester_ctx, system_ctx, pastor_ctx):
        req = _awaiting(requester_ctx, system_ctx)
        approval = reject_request(
            pastor_ctx,
            request_id=req.id,
            route="pastoral",
            reason_code="couldnt_confirm",
            message="We could not confirm what was needed.",
        )
        req.refresh_from_db()
        set_clock(FixedClock(approval.effective_at))
        request_reconsideration(RequesterContext(request_id=req.id), note="Please look again")
        decide_reconsideration(
            pastor_ctx,
            request_id=req.id,
            approve=False,
            reason="Still can't help with this one.",
            reason_code="couldnt_confirm",
        )
        event = _event(
            "RequestRejected",
            aggregate_id=req.id,
            payload={
                "request_id": str(req.id),
                "stage": "reconsideration",
                "route": "pastoral",
                "reason_code": "couldnt_confirm",
                "final": True,
            },
        )
        email = _build_rejected_email(event)
        assert email is not None
        parts = decline_outcome_text("Still can't help with this one.", final=True)
        rendered = render_decline_outcome_text(parts)
        assert rendered in email.text_body
