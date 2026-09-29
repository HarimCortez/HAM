"""FIX-3D: B2 residue (a short sheet's `<form>` must wrap the whole sheet body so it can pin
the bar at large text, not just the bar itself), and M9 copy fixes (no hard-coded "Elder", no
"Ruth A.." double period) in `_decision_card.html`."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def _session_cookie(live_server, django_user):
    from django.conf import settings
    from django.test import Client

    client = Client()
    client.force_login(django_user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return {
        "name": settings.SESSION_COOKIE_NAME,
        "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
        "url": live_server.url,
    }


def _make_awaiting_request_and_pastor(full_name="Ruth Alvarez"):
    from ham.authz import roles
    from ham.authz.context import RequesterContext, SystemContext
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now
    from ham.requests.services import complete_intake_checks, submit_request
    from tests.requests.conftest import make_payload

    pastor = User.objects.create_user(email=f"pastor-{uuid.uuid4().hex[:6]}@example.org")
    SharedIdentityProfile.objects.create(user=pastor, full_name=full_name)
    RoleAssignment.objects.create(user=pastor, role=roles.PASTOR, granted_at=clock_now())

    req = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(
            full_name="Fictional Requester",
            description="Water comes through the bedroom ceiling when it rains "
            "(fictional test data).",
        ),
    )
    complete_intake_checks(SystemContext(), request_id=req.id)
    return pastor, req


def test_u1_form_wraps_the_whole_sheet_body():
    """B2 residue: `.sheet--fullscreen > form {flex: 1; display: flex; flex-direction:
    column}` plus `.action-bar {margin-top: auto}` only has room to pin the bar to the
    bottom of the *form's own* box -- if the consequence list and "you can undo until" line
    sit outside the `<form>`, that box is small and the trick has much less to work with.
    Checked structurally (the intro content must be inside the `<form>`, in DOM order before
    `.action-bar`), the same mechanism B2's fix for A2/A3 already relies on."""
    from ham.authz import roles
    from ham.authz.context import ActorContext
    from ham.requests.services_decisions import approve_request

    pastor, req = _make_awaiting_request_and_pastor()
    ctx = ActorContext(
        user_id=pastor.id,
        real_user_id=None,
        roles=frozenset({roles.PASTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    approval = approve_request(ctx, request_id=req.id, route="pastoral")

    from django.test import Client

    client = Client()
    client.force_login(pastor)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    response = client.get(
        f"/requests/{req.id}/decision/undo", {"approval_id": str(approval.id)}
    )
    content = response.content.decode()

    form_start = content.index("<form")
    list_pos = content.index("Nothing has been sent to the requester")
    bar_pos = content.index('class="action-bar"')
    assert form_start < list_pos < bar_pos, (
        "the consequence list must be inside <form>, before .action-bar, so the sheet's "
        "flex/sticky pinning trick has the whole body to work with"
    )


def test_decision_card_has_no_hardcoded_elder_title():
    """M9: the Board-route reconsideration line must not hard-code "Elder" before the
    decider's name -- a real church might not use that title at all. Rendered directly (not
    through the full view/state machine, which is a parallel slice's file) with the exact
    `decision.is_board_route` shape `_decision_card.html` expects."""
    import uuid as _uuid
    from types import SimpleNamespace

    from django.template.loader import render_to_string

    decision = SimpleNamespace(
        accent="reconsideration",
        state="reconsideration",
        impersonating=False,
        masked=False,
        can_decide=False,
        needs_take_over=False,
        can_take_over=False,
        is_board_route=True,
        original_decider_name="Pat Nguyen",
        recon=None,
        question_marker=None,
        urgent_awaiting_cert=False,
        board_cant_certify_note=False,
        is_dir_ad_awareness=False,
        can_certify_and_approve=False,
        can_approve=False,
        can_reject=False,
        can_ask_question=False,
        can_decline_urgency_link=False,
        can_change_category=False,
        is_board_only=False,
        waiting_since=None,
    )
    html = render_to_string(
        "web/_decision_card.html",
        {"decision": decision, "detail": SimpleNamespace(id=_uuid.uuid4()), "heading_tag": "h2"},
    )
    assert "Elder" not in html, html
    assert "Pat Nguyen" in html


def test_decision_card_take_over_line_has_no_double_period():
    """M9: `original_decider_name` can itself end in a period ("Ruth A.", the short
    display-name form), so the take-over line used to read "Goes to Ruth A.. If..." -- a
    literal double period. Rendered directly (not through the full view/state machine, which
    is a parallel slice's file) with the exact `decision.can_take_over` shape
    `_decision_card.html` expects."""
    import uuid as _uuid
    from types import SimpleNamespace

    from django.template.loader import render_to_string

    decision = SimpleNamespace(
        accent="reconsideration",
        state="reconsideration",
        impersonating=False,
        masked=False,
        can_decide=False,
        needs_take_over=False,
        can_take_over=True,
        is_board_route=False,
        original_decider_name="Ruth A.",
        recon=None,
        question_marker=None,
        urgent_awaiting_cert=False,
        board_cant_certify_note=False,
        is_dir_ad_awareness=False,
        can_certify_and_approve=False,
        can_approve=False,
        can_reject=False,
        can_ask_question=False,
        can_decline_urgency_link=False,
        can_change_category=False,
        is_board_only=False,
        waiting_since=None,
    )
    html = render_to_string(
        "web/_decision_card.html",
        {"decision": decision, "detail": SimpleNamespace(id=_uuid.uuid4()), "heading_tag": "h2"},
    )
    assert "Ruth A.." not in html, html
    assert "Goes to Ruth A." in html
