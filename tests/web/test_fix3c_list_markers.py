"""Fix 3C / UX N2: the requests-list template actually renders `RequestListRow.markers`/
`.line2_text` (they used to be un-populated attributes the template silently ignored)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.platform.clock import FixedClock, set_clock
from ham.requests.services_decisions import reject_request
from ham.rules import RULES
from tests.web.test_s36_leadership_screens import _ctx_for, _login, _make_request

pytestmark = pytest.mark.django_db


def test_undo_pending_marker_renders_on_the_list_row(client, make_user):
    req = _make_request()
    pastor = _login(client, make_user, email="marker-p@example.org", full_name="P", role="PASTOR")
    reject_request(
        _ctx_for(pastor, "PASTOR"),
        request_id=req.id,
        route="pastoral",
        reason_code="another_reason",
        message="sorry",
    )
    response = client.get(reverse("web:requests") + "?tab=decided")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Can still be undone" in body


def test_needs_phone_call_marker_renders_on_the_list_row(client, make_user):
    from tests.web.test_fix3c_view_logic import _make_no_email_request

    req = _make_no_email_request()
    pastor = _login(client, make_user, email="marker-p2@example.org", full_name="P2", role="PASTOR")
    appr = reject_request(
        _ctx_for(pastor, "PASTOR"),
        request_id=req.id,
        route="pastoral",
        reason_code="another_reason",
        message="sorry",
    )
    set_clock(FixedClock(appr.effective_at + RULES.approvals.DECISION_UNDO_WINDOW))
    _login(client, make_user, email="marker-d2@example.org", full_name="D2", role="HAM_DIRECTOR")
    response = client.get(reverse("web:requests") + "?tab=all")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Call to share a decision" in body
