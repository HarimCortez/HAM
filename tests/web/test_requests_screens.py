"""S2.8: leadership request screens L1-L11 (docs/ux/intake.md §6). View-level tests: per-role
permission (Administrator masked, Volunteer denied, impersonation blocked on phone verify),
PII absence on the list/Home/Inbox, and the core write flows (reveal, phone check, close, ask
for more photos).
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from ham.audit.models import AuditEvent
from ham.identity.models import ImpersonationSession, RoleAssignment, SharedIdentityProfile
from ham.platform.clock import now as clock_now
from ham.requests.services import complete_intake_checks, submit_request
from ham.requests.states import RequestStatus
from tests.requests.conftest import make_payload, no_email_payload

pytestmark = pytest.mark.django_db

_PII_STRINGS = (
    "Jane Test",
    "jane@example.org",
    "+13055550111",
    "123 Main St",
    "Ruth Hall",
    "+13055550177",
)


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
    return submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=None,
        payload=no_email_payload(full_name="Ruth Hall", phone="+13055550177"),
    )


def _login(client, make_user, *, email: str, full_name: str, role: str):
    user = make_user(email)
    SharedIdentityProfile.objects.create(user=user, full_name=full_name)
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return user


# --------------------------------------------------------------------------------------
# L1: permission per role
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "role",
    ["HAM_DIRECTOR", "ASSISTANT_DIRECTOR", "PASTOR", "BOARD_REPRESENTATIVE", "ADMINISTRATOR"],
)
def test_requests_list_allowed_for_leadership_roles(client, make_user, role):
    _make_request()
    _login(
        client, make_user, email=f"{role.lower()}@example.org", full_name="Leader Test", role=role
    )
    response = client.get(reverse("web:requests"))
    assert response.status_code == 200


def test_requests_list_denied_for_volunteer(client, make_user):
    _login(
        client, make_user, email="kevin@example.org", full_name="Kevin Thompson", role="VOLUNTEER"
    )
    response = client.get(reverse("web:requests"))
    assert response.status_code == 404


def test_requests_needs_phone_check_denied_for_pastor(client, make_user):
    """Q-025: no-email requests are Director/Assistant Director only."""
    _login(
        client, make_user, email="ruth-pastor@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    response = client.get(reverse("web:requests_needs_phone_check"))
    assert response.status_code == 404


def test_requests_list_never_shows_pii(client, make_user):
    _make_request()
    _make_no_email_request()
    _login(
        client, make_user, email="marcus@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    response = client.get(reverse("web:requests"))
    content = response.content.decode()
    for value in _PII_STRINGS:
        assert value not in content, f"{value!r} leaked onto the requests list"


# --------------------------------------------------------------------------------------
# L2: Administrator masked, no reveal
# --------------------------------------------------------------------------------------
def test_administrator_sees_masked_detail_with_no_reveal_button(client, make_user):
    req = _make_request()
    _login(
        client, make_user, email="nadia@example.org", full_name="Nadia Pierre", role="ADMINISTRATOR"
    )
    response = client.get(reverse("web:request_detail", args=[req.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Show contact details" not in content
    assert "Not shown to the Administrator role" in content
    for value in _PII_STRINGS:
        assert value not in content


def test_administrator_cannot_reveal_contact(client, make_user):
    req = _make_request()
    _login(
        client, make_user, email="nadia@example.org", full_name="Nadia Pierre", role="ADMINISTRATOR"
    )
    response = client.post(reverse("web:request_reveal_contact", args=[req.id]))
    assert response.status_code == 404


# --------------------------------------------------------------------------------------
# L2: reveal logging (Q-024)
# --------------------------------------------------------------------------------------
def test_director_reveal_is_not_audited(client, make_user):
    req = _make_request()
    _login(
        client, make_user, email="marcus@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    before = AuditEvent.objects.filter(action="requester_pii.revealed").count()
    response = client.post(reverse("web:request_reveal_contact", args=[req.id]))
    assert response.status_code == 200
    assert "Jane Test" in response.content.decode()
    after = AuditEvent.objects.filter(action="requester_pii.revealed").count()
    assert after == before


def test_assistant_director_reveal_is_audited(client, make_user):
    req = _make_request()
    _login(
        client,
        make_user,
        email="andre@example.org",
        full_name="Andre Whitfield",
        role="ASSISTANT_DIRECTOR",
    )
    before = AuditEvent.objects.filter(action="requester_pii.revealed").count()
    response = client.post(reverse("web:request_reveal_contact", args=[req.id]))
    assert response.status_code == 200
    assert "Jane Test" in response.content.decode()
    after = AuditEvent.objects.filter(action="requester_pii.revealed").count()
    assert after == before + 1


# --------------------------------------------------------------------------------------
# L9: phone check, incl. blocked while impersonating (Q-025, Q-048)
# --------------------------------------------------------------------------------------
def test_phone_check_verifies_and_moves_to_awaiting_approval(client, make_user):
    from ham.jobs import run_due_jobs_now

    req = _make_no_email_request()
    _login(
        client, make_user, email="marcus@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    response = client.post(
        reverse("web:request_phone_check", args=[req.id]), {"confirmed": "on"}, follow=True
    )
    assert response.status_code == 200
    req.refresh_from_db()
    # verify_by_phone moves NEEDS_PHONE_CHECK -> SUBMITTED synchronously and defers the
    # duplicate check job, which then moves SUBMITTED -> AWAITING_APPROVAL (states.py).
    assert req.status == RequestStatus.SUBMITTED.value
    run_due_jobs_now()
    req.refresh_from_db()
    assert req.status == RequestStatus.AWAITING_APPROVAL.value


def test_phone_check_blocked_while_impersonating(client, make_user):
    req = _make_no_email_request()
    admin = make_user("nadia2@example.org")
    SharedIdentityProfile.objects.create(user=admin, full_name="Nadia Pierre")
    RoleAssignment.objects.create(user=admin, role="ADMINISTRATOR", granted_at=clock_now())
    director = make_user("marcus2@example.org")
    SharedIdentityProfile.objects.create(user=director, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=director, role="HAM_DIRECTOR", granted_at=clock_now())

    client.force_login(admin)
    imp = ImpersonationSession.objects.create(
        admin_user_id=admin.id,
        target_user_id=director.id,
        reason="test",
        started_at=clock_now(),
        last_activity_at=clock_now(),
    )
    session = client.session
    session["ham_impersonation_id"] = str(imp.id)
    session["ham_mfa_satisfied"] = True
    session.save()

    # `request.contact_verify_phone` is `blocked_while_impersonating` at the matrix level
    # (docs/architecture/intake-contracts.md §2), so the route guard itself (not just the
    # command) refuses the whole sheet while impersonating -- the same neutral 404 as any
    # other denied route (navigation.md §6), not a partial page with a disabled button.
    response = client.get(reverse("web:request_phone_check", args=[req.id]))
    assert response.status_code == 404

    response = client.post(reverse("web:request_phone_check", args=[req.id]), {"confirmed": "on"})
    assert response.status_code == 404
    req.refresh_from_db()
    assert req.status == RequestStatus.NEEDS_PHONE_CHECK.value


# --------------------------------------------------------------------------------------
# L10: close (Director/AD only; pastor denied)
# --------------------------------------------------------------------------------------
def test_pastor_cannot_close_a_request(client, make_user):
    req = _make_request()
    _login(
        client, make_user, email="ruth-pastor2@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    response = client.get(reverse("web:request_close", args=[req.id]))
    assert response.status_code == 404


def test_director_can_close_as_duplicate(client, make_user):
    req = _make_request()
    _login(
        client, make_user, email="marcus3@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    response = client.post(
        reverse("web:request_close", args=[req.id]),
        {"reason_code": "duplicate_submission", "note": "Same as HAM #001"},
        follow=True,
    )
    assert response.status_code == 200
    req.refresh_from_db()
    assert req.status == RequestStatus.CANCELLED.value
    assert req.cancel_reason_code == "duplicate_submission"


# --------------------------------------------------------------------------------------
# L11: ask for more photos (Director, AD, pastor, Board rep)
# --------------------------------------------------------------------------------------
def test_pastor_can_ask_for_more_photos(client, make_user):
    req = _make_request()
    _login(
        client, make_user, email="ruth-pastor3@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    response = client.post(
        reverse("web:request_more_photos", args=[req.id]),
        {"reason": "A photo of the ceiling from the hallway."},
        follow=True,
    )
    assert response.status_code == 200


def test_ask_for_more_photos_disabled_reason_for_no_email_request(client, make_user):
    req = _make_no_email_request()
    _login(
        client, make_user, email="marcus4@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    response = client.get(reverse("web:request_more_photos", args=[req.id]))
    assert response.status_code == 200
    assert "We&#x27;ll take photos at the visit." in response.content.decode() or (
        "We'll take photos at the visit." in response.content.decode()
    )


# --------------------------------------------------------------------------------------
# Home / Inbox: attention cards, PII-free
# --------------------------------------------------------------------------------------
def test_home_attention_card_for_awaiting_approval_is_pii_free(client, make_user):
    _make_request()
    _login(
        client, make_user, email="ruth-pastor4@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    response = client.get(reverse("web:home"))
    assert response.status_code == 200
    content = response.content.decode()
    # FIX-D (visual M17): the non-urgent aggregate card reads "N request(s) is/are waiting
    # for a decision" -- see ham.requests.attention.awaiting_approval_cards.
    assert "waiting for a decision" in content
    for value in _PII_STRINGS:
        assert value not in content


def test_home_phone_check_attention_card_for_director(client, make_user):
    _make_no_email_request()
    _login(
        client, make_user, email="marcus5@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    response = client.get(reverse("web:home"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "phone check" in content.lower()
    for value in _PII_STRINGS:
        assert value not in content


def test_inbox_needs_response_is_pii_free(client, make_user):
    _make_request()
    _login(
        client, make_user, email="ruth-pastor5@example.org", full_name="Ruth Alvarez", role="PASTOR"
    )
    response = client.get(reverse("web:inbox"))
    assert response.status_code == 200
    content = response.content.decode()
    for value in _PII_STRINGS:
        assert value not in content


def test_requests_nav_item_is_built(client, make_user):
    _login(
        client, make_user, email="marcus6@example.org", full_name="Marcus Bell", role="HAM_DIRECTOR"
    )
    response = client.get(reverse("web:home"))
    assert response.status_code == 200
    assert reverse("web:requests") in response.content.decode()
