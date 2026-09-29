"""S3.6: leadership approval/decision screens (docs/ux/approvals.md A1-A13; design-system/
screens/approvals.md §§1-4). View-level tests: every sheet's happy path, Administrator masking
(no decision buttons, no answer/note text), impersonation blocks, and a concurrent decision.
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from ham.authz.context import ActorContext
from ham.identity.models import ImpersonationSession, RoleAssignment, SharedIdentityProfile
from ham.platform.clock import FixedClock, set_clock
from ham.platform.clock import now as clock_now
from ham.requests.models import Approval, RequestQuestion
from ham.requests.services import complete_intake_checks, submit_request
from ham.requests.services_decisions import approve_request, reject_request
from ham.requests.states import RequestStatus
from ham.rules import RULES
from tests.requests.conftest import make_payload, no_email_payload

pytestmark = pytest.mark.django_db


def _requester_ctx():
    from ham.authz.context import RequesterContext

    return RequesterContext(request_id=None)


def _system_ctx():
    from ham.authz.context import SystemContext

    return SystemContext()


def _make_request(*, status: RequestStatus = RequestStatus.AWAITING_APPROVAL, **payload_kwargs):
    req = submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(**payload_kwargs),
    )
    if status == RequestStatus.AWAITING_APPROVAL:
        complete_intake_checks(_system_ctx(), request_id=req.id)
    return req


def _make_no_email_request():
    req = submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=None,
        payload=no_email_payload(full_name="Ruth Hall", phone="+13055550177"),
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


def _login(client, make_user, *, email: str, full_name: str, role: str):
    user = make_user(email)
    SharedIdentityProfile.objects.create(user=user, full_name=full_name)
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return user


def _ctx_for(user, role: str) -> ActorContext:
    return ActorContext(
        user_id=user.id,
        real_user_id=None,
        roles=frozenset({role}),
        is_active=True,
        mfa_satisfied=True,
    )


# --------------------------------------------------------------------------------------
# A2: approve
# --------------------------------------------------------------------------------------
def test_pastor_approves_a_request(client, make_user):
    req = _make_request()
    user = _login(
        client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )

    response = client.get(reverse("web:request_approve", args=[req.id]))
    assert response.status_code == 200
    assert "Approve" in response.content.decode()

    response = client.post(
        reverse("web:request_approve", args=[req.id]),
        {"route": "pastoral", "approval_note": "Roof leak confirmed"},
    )
    assert response.status_code == 302
    req.refresh_from_db()
    assert req.status == RequestStatus.APPROVED.value
    approval = Approval.objects.get(request_id=req.id)
    assert approval.decided_by_user_id == user.id
    assert approval.approval_note == "Roof leak confirmed"


def test_board_rep_records_board_approval(client, make_user):
    req = _make_request()
    _login(
        client,
        make_user,
        email="samuel@example.org",
        full_name="Samuel Okafor",
        role="BOARD_REPRESENTATIVE",
    )
    response = client.post(reverse("web:request_approve", args=[req.id]), {"route": "board"})
    assert response.status_code == 302
    approval = Approval.objects.get(request_id=req.id)
    assert approval.route == "board"
    assert approval.board_decided_on is not None


# --------------------------------------------------------------------------------------
# A3: decline, with the "What the requester will read" preview
# --------------------------------------------------------------------------------------
def test_pastor_declines_with_reason_and_preview(client, make_user):
    req = _make_request()
    _login(client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR")

    response = client.get(reverse("web:request_reject", args=[req.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "What the requester will read" in content
    assert "Family or others may be able to help" in content

    response = client.post(
        reverse("web:request_reject", args=[req.id]),
        {
            "route": "pastoral",
            "reason_code": "family_or_others_can_help",
            "message": "From what you've shared, family may be able to help.",
        },
    )
    assert response.status_code == 302
    req.refresh_from_db()
    assert req.status == RequestStatus.REJECTED.value
    approval = Approval.objects.get(request_id=req.id)
    assert approval.reason_code == "family_or_others_can_help"
    assert approval.reason == "From what you've shared, family may be able to help."


def test_decline_requires_reason_and_message(client, make_user):
    req = _make_request()
    _login(client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR")
    response = client.post(
        reverse("web:request_reject", args=[req.id]),
        {"route": "pastoral", "reason_code": "", "message": ""},
    )
    assert response.status_code == 422
    assert not Approval.objects.filter(request_id=req.id).exists()


# --------------------------------------------------------------------------------------
# U1: undo
# --------------------------------------------------------------------------------------
def test_decider_can_undo_within_the_window(client, make_user):
    req = _make_request()
    user = _login(
        client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    approve_request(_ctx_for(user, "PASTOR"), request_id=req.id, route="pastoral")
    approval = Approval.objects.get(request_id=req.id)

    response = client.get(
        reverse("web:request_decision_undo", args=[req.id]) + f"?approval_id={approval.id}"
    )
    assert response.status_code == 200
    assert "Can be undone until" not in response.content.decode()  # that's the card, not the sheet
    assert "Undo" in response.content.decode()

    response = client.post(
        reverse("web:request_decision_undo", args=[req.id]), {"approval_id": str(approval.id)}
    )
    assert response.status_code == 302
    req.refresh_from_db()
    assert req.status == RequestStatus.AWAITING_APPROVAL.value
    approval.refresh_from_db()
    assert approval.undone_at is not None


def test_undo_refused_after_the_window(client, make_user):
    req = _make_request()
    user = _login(
        client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    approve_request(_ctx_for(user, "PASTOR"), request_id=req.id, route="pastoral")
    approval = Approval.objects.get(request_id=req.id)

    later = (
        clock_now() + RULES.approvals.DECISION_UNDO_WINDOW + RULES.approvals.DECISION_UNDO_WINDOW
    )
    set_clock(FixedClock(later))
    try:
        response = client.post(
            reverse("web:request_decision_undo", args=[req.id]), {"approval_id": str(approval.id)}
        )
    finally:
        set_clock(None)
    assert response.status_code == 302
    req.refresh_from_db()
    assert req.status == RequestStatus.APPROVED.value


def test_other_approver_cannot_undo_someone_elses_decision(client, make_user):
    req = _make_request()
    decider = make_user("ruth-decider@example.org")
    SharedIdentityProfile.objects.create(user=decider, full_name="Ruth Alvarez")
    RoleAssignment.objects.create(user=decider, role="PASTOR", granted_at=clock_now())
    approve_request(_ctx_for(decider, "PASTOR"), request_id=req.id, route="pastoral")
    approval = Approval.objects.get(request_id=req.id)

    _login(client, make_user, email="ken@example.org", full_name="Ken Pastor", role="PASTOR")
    response = client.post(
        reverse("web:request_decision_undo", args=[req.id]), {"approval_id": str(approval.id)}
    )
    # Fix 3E / security L-d: the undo sheet (GET and POST alike) is decider-only -- a
    # different Pastor gets the same neutral 404 as any other out-of-scope id, not a distinct
    # "someone decided first" flash that would confirm the id resolved to something real.
    assert response.status_code == 404
    approval.refresh_from_db()
    assert approval.undone_at is None


# --------------------------------------------------------------------------------------
# A4: ask a question
# --------------------------------------------------------------------------------------
def test_ask_a_question(client, make_user):
    req = _make_request()
    _login(
        client,
        make_user,
        email="andre@example.org",
        full_name="Andre Whitfield",
        role="ASSISTANT_DIRECTOR",
    )
    response = client.post(
        reverse("web:request_question_ask", args=[req.id]),
        {"question": "Does the water come in only when it rains?"},
    )
    assert response.status_code == 302
    question = RequestQuestion.objects.get(request_id=req.id)
    assert question.question == "Does the water come in only when it rains?"
    assert question.answered_at is None


def test_ask_a_question_requires_text(client, make_user):
    req = _make_request()
    _login(
        client,
        make_user,
        email="andre@example.org",
        full_name="Andre Whitfield",
        role="ASSISTANT_DIRECTOR",
    )
    response = client.post(reverse("web:request_question_ask", args=[req.id]), {"question": ""})
    assert response.status_code == 200
    assert not RequestQuestion.objects.filter(request_id=req.id).exists()


# --------------------------------------------------------------------------------------
# Administrator: masked view, no decision buttons, no answer text
# --------------------------------------------------------------------------------------
def test_administrator_sees_no_decision_buttons(client, make_user):
    req = _make_request()
    _login(
        client, make_user, email="nadia@example.org", full_name="Nadia Pierre", role="ADMINISTRATOR"
    )
    response = client.get(reverse("web:request_detail", args=[req.id]))
    content = response.content.decode()
    assert "Approve" not in content
    assert "Decline" not in content


def test_administrator_denied_approve_route(client, make_user):
    req = _make_request()
    _login(
        client, make_user, email="nadia@example.org", full_name="Nadia Pierre", role="ADMINISTRATOR"
    )
    response = client.get(reverse("web:request_approve", args=[req.id]))
    assert response.status_code == 404
    response = client.post(reverse("web:request_approve", args=[req.id]), {"route": "pastoral"})
    assert response.status_code == 404


def test_administrator_does_not_see_approval_note_or_decline_message(client, make_user):
    """A1 spec (docs/ux/approvals.md §5, G3-19) + Q-124/Q-151: the Administrator's masked
    view hides the decider's own words -- the optional "Why approved (leaders only)" note
    (Q-169) and the rejection's "what we'll tell Doris" message -- even though it does show
    who decided, the route and the outcome chip (that much is operational status, not the
    decider's own free text)."""
    approved_req = _make_request()
    pastor = _login(
        client, make_user, email="ruth-a1@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    distinctive_note = "Distinctive leaders-only note about the widow next door."
    approve_request(
        _ctx_for(pastor, "PASTOR"),
        request_id=approved_req.id,
        route="pastoral",
        approval_note=distinctive_note,
    )

    declined_req = _make_request()
    distinctive_message = "Distinctive kind decline sentence nobody else should read."
    reject_request(
        _ctx_for(pastor, "PASTOR"),
        request_id=declined_req.id,
        route="pastoral",
        reason_code="couldnt_confirm",
        message=distinctive_message,
    )

    _login(
        client,
        make_user,
        email="nadia-a1@example.org",
        full_name="Nadia Pierre",
        role="ADMINISTRATOR",
    )

    resp = client.get(reverse("web:request_detail", args=[approved_req.id]))
    content = resp.content.decode()
    assert distinctive_note not in content
    assert "Approved" in content  # the outcome itself still shows
    assert "Ruth A." in content  # who decided still shows, as a display name (§5)

    resp = client.get(reverse("web:request_detail", args=[declined_req.id]))
    content = resp.content.decode()
    assert distinctive_message not in content
    assert "Not approved" in content or "Rejected" in content


def test_administrator_does_not_see_answer_text(client, make_user):
    req = _make_request()
    asker = make_user("andre-asker@example.org")
    SharedIdentityProfile.objects.create(user=asker, full_name="Andre Whitfield")
    RoleAssignment.objects.create(user=asker, role="ASSISTANT_DIRECTOR", granted_at=clock_now())
    from ham.requests.services_questions import ask_question, record_phone_answer

    q = ask_question(
        _ctx_for(asker, "ASSISTANT_DIRECTOR"), request_id=req.id, question="Only when it rains?"
    )
    record_phone_answer(
        _ctx_for(asker, "ASSISTANT_DIRECTOR"), question_id=q.id, answer="Only after storms, badly."
    )

    _login(
        client, make_user, email="nadia@example.org", full_name="Nadia Pierre", role="ADMINISTRATOR"
    )
    response = client.get(reverse("web:request_detail", args=[req.id]))
    content = response.content.decode()
    assert "Only after storms, badly." not in content
    assert "Answered on" in content or "message-circle" in content


# --------------------------------------------------------------------------------------
# Impersonation: decision actions blocked; category change allowed (Q-172)
# --------------------------------------------------------------------------------------
def _start_impersonation(client, admin, target):
    imp = ImpersonationSession.objects.create(
        admin_user_id=admin.id,
        target_user_id=target.id,
        reason="support",
        started_at=clock_now(),
        last_activity_at=clock_now(),
    )
    session = client.session
    session["ham_impersonation_id"] = str(imp.id)
    session["ham_mfa_satisfied"] = True
    session.save()


def test_approve_route_blocked_while_impersonating(client, make_user):
    req = _make_request()
    admin = _login(
        client, make_user, email="nadia@example.org", full_name="Nadia Pierre", role="ADMINISTRATOR"
    )
    target = make_user("ruth-target@example.org")
    SharedIdentityProfile.objects.create(user=target, full_name="Ruth Alvarez")
    RoleAssignment.objects.create(user=target, role="PASTOR", granted_at=clock_now())
    _start_impersonation(client, admin, target)
    response = client.get(reverse("web:request_approve", args=[req.id]))
    assert response.status_code == 404


def test_category_change_allowed_while_impersonating(client, make_user):
    req = _make_request()
    admin = _login(
        client,
        make_user,
        email="nadia2@example.org",
        full_name="Nadia Pierre",
        role="ADMINISTRATOR",
    )
    target = make_user("marcus-target@example.org")
    SharedIdentityProfile.objects.create(user=target, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=target, role="HAM_DIRECTOR", granted_at=clock_now())
    _start_impersonation(client, admin, target)
    response = client.get(reverse("web:request_category_change", args=[req.id]))
    assert response.status_code == 200


# --------------------------------------------------------------------------------------
# A6: change category (Director/AD only)
# --------------------------------------------------------------------------------------
def test_director_changes_category(client, make_user):
    req = _make_request()
    _login(
        client, make_user, email="marcus@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    response = client.post(
        reverse("web:request_category_change", args=[req.id]), {"need_category": "electrical"}
    )
    assert response.status_code == 302
    req.refresh_from_db()
    assert req.need_category == "electrical"


def test_pastor_cannot_change_category(client, make_user):
    """Owner box (Q-109): Director/AD only, unlike the UX body's wider draft."""
    req = _make_request()
    _login(client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR")
    response = client.get(reverse("web:request_category_change", args=[req.id]))
    assert response.status_code == 404


# --------------------------------------------------------------------------------------
# A13: someone decided first (concurrency)
# --------------------------------------------------------------------------------------
def test_concurrent_decision_shows_clean_alert(client, make_user):
    req = _make_request()
    user = _login(
        client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )

    # Another approver (e.g. the Board rep) records the decision first, in between this
    # browser's GET and its POST.
    other = make_user("samuel@example.org")
    SharedIdentityProfile.objects.create(user=other, full_name="Samuel Okafor")
    RoleAssignment.objects.create(user=other, role="BOARD_REPRESENTATIVE", granted_at=clock_now())
    approve_request(_ctx_for(other, "BOARD_REPRESENTATIVE"), request_id=req.id, route="board")

    response = client.post(
        reverse("web:request_approve", args=[req.id]), {"route": "pastoral"}, follow=True
    )
    assert response.status_code == 200
    assert "already decided" in response.content.decode().lower()
    assert Approval.objects.filter(request_id=req.id).count() == 1
    approval = Approval.objects.get(request_id=req.id)
    assert approval.decided_by_user_id == other.id
    assert approval.decided_by_user_id != user.id


# --------------------------------------------------------------------------------------
# A7: list tabs
# --------------------------------------------------------------------------------------
def test_list_tabs_include_waiting_reconsideration_decided(client, make_user):
    _make_request()
    _login(client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR")
    response = client.get(reverse("web:requests"))
    content = response.content.decode()
    assert "Waiting on requester" in content
    assert "Reconsideration" in content
    assert "Decided" in content


def test_decided_tab_shows_a_decided_request(client, make_user):
    req = _make_request()
    user = _login(
        client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    approve_request(_ctx_for(user, "PASTOR"), request_id=req.id, route="pastoral")
    response = client.get(reverse("web:requests") + "?tab=decided")
    content = response.content.decode()
    assert req.display_number in content


def test_reject_reconsideration_and_decide_flow(client, make_user):
    req = _make_request()
    user = _login(
        client, make_user, email="ruth@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    approval = reject_request(
        _ctx_for(user, "PASTOR"),
        request_id=req.id,
        route="pastoral",
        reason_code="couldnt_confirm",
        message="We couldn't confirm the details.",
    )
    from ham.authz.context import RequesterContext
    from ham.requests.services_decisions import request_reconsideration

    req.refresh_from_db()
    # Security M1/Q-181: refused while the decline can still be undone.
    set_clock(FixedClock(approval.effective_at))
    request_reconsideration(RequesterContext(request_id=req.id), note="Please look again.")
    req.refresh_from_db()
    assert req.status == RequestStatus.RECONSIDERATION_PENDING.value

    response = client.get(reverse("web:request_reconsideration_decide", args=[req.id]))
    assert response.status_code == 200
    assert "Please look again." in response.content.decode()

    response = client.post(
        reverse("web:request_reconsideration_decide", args=[req.id]),
        {"outcome": "approve", "reason": "No family nearby after all."},
    )
    assert response.status_code == 302
    req.refresh_from_db()
    assert req.status == RequestStatus.APPROVED.value
