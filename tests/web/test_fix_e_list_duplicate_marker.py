"""FIX-E M2 regression: the list row's "possible earlier request" marker
(`has_possible_duplicate`) is only ever computed for a viewer who holds
`request.history.view` -- never the Administrator, even while impersonating a role that would
otherwise qualify (N5/Q-151). New file per wave brief.
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from ham.authz import roles as ham_roles
from ham.authz.context import RequesterContext, SystemContext
from ham.platform.clock import now as clock_now
from ham.requests.models import RequestMatch
from ham.requests.queries import list_requests
from ham.requests.services import complete_intake_checks, submit_request
from tests.requests.conftest import actor_ctx, make_payload
from tests.web.test_fix_c_leadership_screens import _login
from tests.web.test_fix_e_notification_open import _impersonation_session

pytestmark = pytest.mark.django_db


def _requester_ctx():
    return RequesterContext(request_id=None)


def _make_two_matching_requests():
    first = submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(phone="+13055550199"),
    )
    second = submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(phone="+13055550199"),
    )
    RequestMatch.objects.create(
        request=second, prior_request=first, reasons=["phone"], detected_at=clock_now()
    )
    complete_intake_checks(SystemContext(), request_id=first.id)
    complete_intake_checks(SystemContext(), request_id=second.id)
    return first, second


def test_director_sees_the_marker(client, make_user):
    _first, second = _make_two_matching_requests()
    _login(
        client, make_user, email="director-dup@example.org", full_name="D Dup", role="HAM_DIRECTOR"
    )
    resp = client.get(reverse("web:requests"), {"tab": "awaiting"})
    assert resp.status_code == 200
    assert b"Earlier request" in resp.content


def test_administrator_never_sees_the_marker(client, make_user):
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile

    _first, second = _make_two_matching_requests()
    admin = make_user("admin-dup@example.org")
    SharedIdentityProfile.objects.create(user=admin, full_name="Admin Dup")
    RoleAssignment.objects.create(user=admin, role=roles.ADMINISTRATOR, granted_at=clock_now())
    client.force_login(admin)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()

    resp = client.get(reverse("web:requests"), {"tab": "awaiting"})
    assert resp.status_code == 200
    assert b"Earlier request" not in resp.content


def test_administrator_impersonating_a_director_still_never_sees_the_marker(client, make_user):
    """N5/Q-151: `ctx.effective_roles` reflects the impersonation target's role (Director,
    which alone *would* qualify) -- the real actor being an Administrator must still win."""
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile

    _first, second = _make_two_matching_requests()

    target = make_user("director-target-dup@example.org")
    SharedIdentityProfile.objects.create(user=target, full_name="Target Director")
    RoleAssignment.objects.create(user=target, role=roles.HAM_DIRECTOR, granted_at=clock_now())

    admin = make_user("admin-impersonator-dup@example.org")
    SharedIdentityProfile.objects.create(user=admin, full_name="Admin Impersonator")
    RoleAssignment.objects.create(user=admin, role=roles.ADMINISTRATOR, granted_at=clock_now())

    client.force_login(admin)
    _impersonation_session(client, admin, target)

    resp = client.get(reverse("web:requests"), {"tab": "awaiting"})
    assert resp.status_code == 200
    assert b"Earlier request" not in resp.content


def test_list_requests_query_itself_omits_the_marker_for_administrator():
    _first, second = _make_two_matching_requests()
    director_ctx = actor_ctx(roles=frozenset({ham_roles.HAM_DIRECTOR}))
    admin_ctx = actor_ctx(roles=frozenset({ham_roles.ADMINISTRATOR}))
    director_rows = {r.id: r for r in list_requests(director_ctx)}
    admin_rows = {r.id: r for r in list_requests(admin_ctx)}
    assert director_rows[second.id].has_possible_duplicate is True
    assert admin_rows[second.id].has_possible_duplicate is False
