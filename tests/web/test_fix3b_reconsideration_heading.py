"""FIX-3B M14: the reconsideration decision sheet's heading must be a whole, correctly
capitalized sentence -- never a lower-case verb spliced into a fixed phrase ("approve HAM
#009?") and never a capital letter mid-phrase ("Take over and Approve HAM #009")
(step3-ui-visual-qa.md M14).
"""

from __future__ import annotations

import uuid

import pytest
from django.test import Client

from ham.authz import roles
from ham.authz.context import ActorContext, RequesterContext, SystemContext
from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
from ham.platform.clock import now as clock_now
from ham.requests.services import complete_intake_checks, submit_request
from ham.requests.services_decisions import reject_request, request_reconsideration
from tests.requests.conftest import make_payload

pytestmark = pytest.mark.django_db


def _login(django_user):
    client = Client()
    client.force_login(django_user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return client


def _make_pending_reconsideration():
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
    request_reconsideration(RequesterContext(request_id=req.id), note="Please look again.")
    return pastor, req


def test_heading_is_capitalized_without_take_over():
    pastor, req = _make_pending_reconsideration()
    client = _login(pastor)
    resp = client.get(f"/requests/{req.id}/reconsideration/decide?outcome=approve")
    body = resp.content.decode()
    assert f"Approve {req.display_number} after reconsideration?" in body
    assert f"approve {req.display_number}" not in body
