"""FIX-3D hand-back item 3 (visual M3): `RequestListRow.is_final` was declared in the
template but never set by `list_requests`, so the "· Final" marker never rendered for a
closed rejection.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.authz.context import RequesterContext
from ham.platform.clock import FixedClock, set_clock
from ham.requests.services_decisions import (
    decide_reconsideration,
    reject_request,
    request_reconsideration,
)
from ham.rules import RULES
from tests.web.test_s36_leadership_screens import _ctx_for, _login, _make_request

pytestmark = pytest.mark.django_db


def _row_chunk(body: str, display_number: str) -> str:
    """The `<li>...</li>` for this request's own list row -- excludes the auto-selected
    split-view detail pane (`requests_list.html`'s `elif rows: selected_detail = ...`),
    which renders a SEPARATE, already-correct "Final" chip from `_decision_card.html`."""
    marker = f'<span class="request-row__number">{display_number}</span>'
    idx = body.find(marker)
    assert idx != -1, f"{display_number!r} row not found"
    start = body.rfind("<li>", 0, idx)
    end = body.find("</li>", idx)
    return body[start:end]


def test_final_marker_renders_after_a_reconsideration_stage_decline(client, make_user):
    req = _make_request()
    pastor = _login(
        client, make_user, email="final-p@example.org", full_name="Final P", role="PASTOR"
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
    request_reconsideration(RequesterContext(request_id=req.id), note="Please look again")
    second = decide_reconsideration(
        ctx,
        request_id=req.id,
        approve=False,
        reason="Still can't help.",
        reason_code="another_reason",
    )
    req.refresh_from_db()
    assert req.closed_at is not None
    # This second decision has its own fresh undo window -- advance past it too, or the row's
    # "Can still be undone" marker (correctly) takes over `line2_text` instead of "Final".
    set_clock(FixedClock(second.effective_at + RULES.approvals.DECISION_UNDO_WINDOW))

    response = client.get(reverse("web:requests") + "?tab=decided")
    assert response.status_code == 200
    body = response.content.decode()
    # Scope the assertion to THIS request's own `<li>` row (not the auto-selected split-view
    # detail pane, which renders its own, independently-correct "Final" chip in
    # `_decision_card.html` regardless of `RequestListRow.is_final`).
    row_chunk = _row_chunk(body, req.display_number)
    assert "&middot; Final" in row_chunk
    set_clock(None)


def test_no_final_marker_while_still_reconsiderable(client, make_user):
    req = _make_request()
    pastor = _login(
        client, make_user, email="notfinal-p@example.org", full_name="Not Final", role="PASTOR"
    )
    reject_request(
        _ctx_for(pastor, "PASTOR"),
        request_id=req.id,
        route="pastoral",
        reason_code="another_reason",
        message="Sorry.",
    )
    response = client.get(reverse("web:requests") + "?tab=decided")
    assert response.status_code == 200
    body = response.content.decode()
    row_chunk = _row_chunk(body, req.display_number)
    assert "&middot; Final" not in row_chunk
