"""FIX-3B M3: Rejected is a neutral chip with `circle-x` (never red/danger), Approved is
info + `badge-check`, Reconsideration pending is attention + `rotate-ccw`, and the requester-
facing "Not approved"/"Taking another look" wording chip must not leak onto staff rows
(step3-ui-visual-qa.md M3).
"""

from __future__ import annotations

import uuid

import pytest
from django.test import Client

from ham.authz import roles
from ham.authz.context import ActorContext, RequesterContext, SystemContext
from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
from ham.platform.clock import now as clock_now
from ham.requests.presentation import STATUS_ICONS, STATUS_TONES
from ham.requests.services import complete_intake_checks, submit_request
from ham.requests.services_decisions import reject_request
from ham.requests.states import RequestStatus
from tests.requests.conftest import make_payload

pytestmark = pytest.mark.django_db


def _login(django_user):
    client = Client()
    client.force_login(django_user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return client


def test_rejected_status_tone_is_neutral_never_danger():
    assert STATUS_TONES[RequestStatus.REJECTED.value] == "neutral"
    assert STATUS_ICONS[RequestStatus.REJECTED.value] == "circle-x"


def test_approved_status_tone_and_icon():
    assert STATUS_TONES[RequestStatus.APPROVED.value] == "info"
    assert STATUS_ICONS[RequestStatus.APPROVED.value] == "badge-check"


def test_reconsideration_pending_status_tone_and_icon():
    assert STATUS_TONES[RequestStatus.RECONSIDERATION_PENDING.value] == "attention"
    assert STATUS_ICONS[RequestStatus.RECONSIDERATION_PENDING.value] == "rotate-ccw"


def test_rejected_row_never_renders_danger_chip_or_requester_wording():
    pastor = User.objects.create_user(email=f"pastor-{uuid.uuid4().hex[:6]}@example.org")
    SharedIdentityProfile.objects.create(user=pastor, full_name="Ruth Alvarez")
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

    ctx = ActorContext(
        user_id=pastor.id,
        real_user_id=None,
        roles=frozenset({roles.PASTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    reject_request(
        ctx,
        request_id=req.id,
        route="pastoral",
        reason_code="family_or_others_can_help",
        message="We're sorry, we can't help with this one.",
    )

    client = _login(pastor)
    resp = client.get("/requests?tab=decided")
    body = resp.content.decode()
    assert "chip--danger" not in body
    # Scoped to the request-rows list (not the detail page's separate History timeline, which
    # has its own distinct per-entry label and isn't part of M3's row-chip fix).
    rows_start = body.index('class="request-rows"')
    rows_end = body.index("</ul>", rows_start)
    rows_html = body[rows_start:rows_end]
    assert "Not approved" not in rows_html
    assert "chip--tag" not in rows_html
