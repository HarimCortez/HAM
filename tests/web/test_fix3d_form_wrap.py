"""FIX-3D B2: the `<form>` wraps the whole sheet body (not just the trailing action bar) on
A2c, A2u (request_approve.html's urgent branch), A2n, A4, A5 and A11 -- checked structurally
(single `<form>`, with the intro content appearing before `.action-bar`, inside it), the same
mechanism already proven for U1 in `tests/e2e/test_fix3d_bar_pinning_and_copy.py`.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.django_db


def _make_awaiting_request_and_pastor(full_name="Ruth Alvarez", *, urgent=False, no_email=False):
    from ham.authz import roles
    from ham.authz.context import RequesterContext, SystemContext
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now
    from ham.requests.services import complete_intake_checks, submit_request
    from tests.requests.conftest import make_payload, no_email_payload

    pastor = User.objects.create_user(email=f"pastor-{uuid.uuid4().hex[:6]}@example.org")
    SharedIdentityProfile.objects.create(user=pastor, full_name=full_name)
    RoleAssignment.objects.create(user=pastor, role=roles.PASTOR, granted_at=clock_now())

    kwargs = dict(
        full_name="Fictional Requester",
        description="Water comes through the bedroom ceiling when it rains (fictional test data).",
    )
    if urgent:
        kwargs["urgent_requested"] = True
        kwargs["urgency_justification"] = "Water is actively flooding the kitchen."
    payload = no_email_payload(**kwargs) if no_email else make_payload(**kwargs)
    req = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=payload,
    )
    complete_intake_checks(SystemContext(), request_id=req.id)
    return pastor, req


def _make_director(full_name="Marcus Bell"):
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now

    director = User.objects.create_user(email=f"director-{uuid.uuid4().hex[:6]}@example.org")
    SharedIdentityProfile.objects.create(user=director, full_name=full_name)
    RoleAssignment.objects.create(user=director, role=roles.HAM_DIRECTOR, granted_at=clock_now())
    return director


def _login(client, user):
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()


def _assert_form_wraps_body(content, *, intro_marker, bar_marker='class="action-bar"'):
    form_start = content.index("<form")
    intro_pos = content.index(intro_marker)
    bar_pos = content.index(bar_marker)
    assert form_start < intro_pos < bar_pos, (
        f"expected <form> ({form_start}) < intro ({intro_pos}) < action-bar ({bar_pos})"
    )


def test_a2u_urgent_approve_form_wraps_urgency_block():
    from django.test import Client

    pastor, req = _make_awaiting_request_and_pastor(urgent=True)

    client = Client()
    _login(client, pastor)
    response = client.get(f"/requests/{req.id}/approve", {"mode": "urgent"})
    content = response.content.decode()
    _assert_form_wraps_body(content, intro_marker="Why it's urgent")


def test_a2n_not_urgent_form_wraps_intro_paragraph():
    from django.test import Client

    pastor, req = _make_awaiting_request_and_pastor(urgent=True)

    client = Client()
    _login(client, pastor)
    response = client.get(f"/requests/{req.id}/urgency/decline")
    content = response.content.decode()
    _assert_form_wraps_body(
        content, intro_marker="will stay with the pastors and Board as a normal request"
    )


def test_a2c_certify_form_wraps_urgency_quote():
    from django.test import Client

    from ham.authz import roles
    from ham.authz.context import ActorContext
    from ham.requests.services_decisions import approve_request

    board_rep, req = _make_awaiting_request_and_pastor(full_name="Andre Whitfield", urgent=True)
    from ham.identity.models import RoleAssignment
    from ham.platform.clock import now as clock_now

    RoleAssignment.objects.filter(user=board_rep).delete()
    RoleAssignment.objects.create(
        user=board_rep, role=roles.BOARD_REPRESENTATIVE, granted_at=clock_now()
    )
    ctx = ActorContext(
        user_id=board_rep.id,
        real_user_id=None,
        roles=frozenset({roles.BOARD_REPRESENTATIVE}),
        is_active=True,
        mfa_satisfied=True,
    )
    approve_request(ctx, request_id=req.id, route="board")

    pastor, _ = _make_awaiting_request_and_pastor()
    client = Client()
    _login(client, pastor)
    response = client.get(f"/requests/{req.id}/urgency/certify")
    content = response.content.decode()
    _assert_form_wraps_body(content, intro_marker="Why it's urgent")


def test_a5_record_answer_has_one_form_and_wraps_the_quote():
    """B2: the "Show contact details" button used to be its own separate `<form>` (a direct
    sibling), so only the small trailing form got `.sheet--fullscreen > form`'s flex-grow --
    now there is exactly one `<form>`, and it wraps the question quote too."""
    from django.test import Client

    from ham.authz import roles
    from ham.authz.context import ActorContext
    from ham.requests.services_questions import ask_question

    pastor, req = _make_awaiting_request_and_pastor()
    ctx = ActorContext(
        user_id=pastor.id,
        real_user_id=None,
        roles=frozenset({roles.PASTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    question = ask_question(ctx, request_id=req.id, question="What is the roof material?")

    client = Client()
    _login(client, pastor)
    response = client.get(f"/requests/{req.id}/questions/{question.id}/answer")
    content = response.content.decode()
    assert content.count("<form") == 1, "expected exactly one <form> on A5"
    _assert_form_wraps_body(content, intro_marker="asked", bar_marker="Save answer")


def test_a11_tell_by_phone_has_one_form_and_wraps_the_script():
    """B2: same single-form merge as A5, for the "what to say" script quote."""
    from django.test import Client

    from ham.authz import roles
    from ham.authz.context import ActorContext
    from ham.requests.services_decisions import approve_request

    pastor, req = _make_awaiting_request_and_pastor()
    from ham.requests.models import Requester

    Requester.objects.filter(request_id=req.id).update(email=None)

    ctx = ActorContext(
        user_id=pastor.id,
        real_user_id=None,
        roles=frozenset({roles.PASTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    approve_request(ctx, request_id=req.id, route="pastoral")

    director = _make_director()
    client = Client()
    _login(client, director)
    response = client.get(f"/requests/{req.id}/decision/phoned")
    content = response.content.decode()
    assert content.count("<form") == 1, "expected exactly one <form> on A11"
    _assert_form_wraps_body(content, intro_marker="What to say", bar_marker="Mark as told")
