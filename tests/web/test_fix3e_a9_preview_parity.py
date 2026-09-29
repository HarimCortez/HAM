"""Fix 3E: FIX-3D's A9 decline preview (final=True, "the requester's FINAL message") now
renders from the SAME `ham.requests.presentation.decline_outcome_text` parts as the E13 email
and the A3 preview, instead of an independently hand-written "We looked at your request
again..." copy that could drift from what actually sends (per the brief's "if A9's decline
preview exists on your base, have it use the same parts").
"""

from __future__ import annotations

from django.urls import reverse

from ham.authz.context import RequesterContext
from ham.platform.clock import FixedClock, set_clock
from ham.requests.presentation import decline_outcome_text
from ham.requests.services_decisions import reject_request, request_reconsideration
from tests.web.test_s36_leadership_screens import _ctx_for, _login, _make_request


def test_a9_decline_preview_opening_and_closing_match_the_final_parts(client, make_user):
    req = _make_request()
    pastor = _login(
        client, make_user, email="a9preview@example.org", full_name="A9 Preview", role="PASTOR"
    )
    ctx = _ctx_for(pastor, "PASTOR")
    approval = reject_request(
        ctx,
        request_id=req.id,
        route="pastoral",
        reason_code="couldnt_confirm",
        message="We could not confirm what was needed.",
    )
    set_clock(FixedClock(approval.effective_at))
    request_reconsideration(RequesterContext(request_id=req.id), note="Please look again")

    response = client.get(
        reverse("web:request_reconsideration_decide", args=[req.id]) + "?outcome=decline"
    )
    assert response.status_code == 200
    body = response.content.decode()

    expected = decline_outcome_text("", final=True)
    expected_opening = expected.opening[0].upper() + expected.opening[1:]
    assert expected_opening.replace("'", "&#x27;") in body
    assert expected.closing.replace("'", "&#x27;") in body
    # Regression guard: the OLD hand-written copy is gone, not just coincidentally present
    # alongside the shared parts.
    assert "We looked at your request again, and we're sorry" not in body
    set_clock(None)
