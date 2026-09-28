"""FIX-E NEW-1 regression: R5's "anything else about reaching you or visiting?" note
(`contact_note`) is blanked from the Administrator's masked detail view, both in the query
(`ham.requests.queries.get_request_detail`) and therefore never rendered by
`_request_detail.html`. New file per wave brief.
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from ham.authz.context import RequesterContext, SystemContext
from ham.requests.queries import get_request_detail
from ham.requests.services import complete_intake_checks, submit_request
from tests.requests.conftest import actor_ctx, make_payload
from tests.web.test_fix_c_leadership_screens import _login

pytestmark = pytest.mark.django_db


def _submit_with_note(note: str):
    req = submit_request(
        RequesterContext(request_id=None),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(contact_note=note),
    )
    complete_intake_checks(SystemContext(), request_id=req.id)
    return req


def test_query_blanks_contact_note_for_administrator():
    from ham.authz import roles

    req = _submit_with_note("Ring the back doorbell, dog is friendly.")
    director_detail = get_request_detail(actor_ctx(roles=frozenset({roles.HAM_DIRECTOR})), req.id)
    admin_detail = get_request_detail(actor_ctx(roles=frozenset({roles.ADMINISTRATOR})), req.id)

    assert director_detail.contact_note == "Ring the back doorbell, dog is friendly."
    assert admin_detail.contact_note == ""


def test_administrator_detail_page_never_renders_the_note(client, make_user):
    req = _submit_with_note("Use the side gate, ask for Maria.")
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile
    from ham.platform.clock import now as clock_now

    admin = make_user("admin-contactnote@example.org")
    SharedIdentityProfile.objects.create(user=admin, full_name="Admin Contact Note")
    RoleAssignment.objects.create(user=admin, role=roles.ADMINISTRATOR, granted_at=clock_now())
    client.force_login(admin)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()

    resp = client.get(reverse("web:request_detail", kwargs={"request_id": req.id}))
    assert resp.status_code == 200
    assert b"Use the side gate" not in resp.content


def test_director_detail_page_renders_the_note(client, make_user):
    req = _submit_with_note("Use the side gate, ask for Maria.")
    _login(
        client,
        make_user,
        email="director-contactnote@example.org",
        full_name="D Note",
        role="HAM_DIRECTOR",
    )
    resp = client.get(reverse("web:request_detail", kwargs={"request_id": req.id}))
    assert resp.status_code == 200
    assert b"Use the side gate" in resp.content
