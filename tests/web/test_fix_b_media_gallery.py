"""Fix round FIX-B: PRD guardian M3 / UX B1 (leadership thumb/view routes) and N11 (the
requester secure page shows batch state + the leader's reopen reason). New file -- see
`docs/handoff/wave-brief.md`.
"""

from __future__ import annotations

import io
import uuid

import pytest
from django.urls import reverse
from PIL import Image

from ham.authz.context import RequesterContext, SystemContext
from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.media import services as media_services
from ham.media.models import RequestMedia
from ham.platform.clock import now as clock_now
from ham.platform.storage import get_object_store
from ham.requests.services import complete_intake_checks, submit_request
from tests.requests.conftest import make_payload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _real_portal_lookups():
    """Some sibling test modules register fakes for `ham.requester_portal.services`'s
    cross-app lookups and reset the globals to `None` on teardown rather than restoring the
    real ones (see `tests/requester_portal/test_notifications.py`'s identical fixture) -- this
    module calls `ham.requester_portal.services.issue_link` directly (N11's secure-page
    tests), so it can't rely on `RequesterPortalConfig.ready()`'s startup registration still
    being in place when the full suite runs."""
    from ham.requester_portal import services as portal_services
    from ham.requests import queries as requests_queries

    def _facts_lookup(request_id):
        facts = requests_queries.request_facts_for_portal(request_id)
        return portal_services.RequestLinkFacts(status=facts.status, closed_at=facts.closed_at)

    portal_services.register_request_facts_lookup(_facts_lookup)
    portal_services.register_request_contact_lookup(requests_queries.request_contact_for_portal)
    portal_services.register_email_to_request_ids_lookup(
        requests_queries.request_ids_for_portal_email
    )
    yield
    portal_services._request_facts_lookup = None  # noqa: SLF001 - test isolation
    portal_services._request_contact_lookup = None  # noqa: SLF001
    portal_services._email_to_request_ids_lookup = None  # noqa: SLF001


def _requester_ctx():
    return RequesterContext(request_id=None)


def _make_request_with_a_ready_photo():
    req = submit_request(
        _requester_ctx(),
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(),
    )
    complete_intake_checks(SystemContext(), request_id=req.id)
    ctx = RequesterContext(request_id=req.id)
    reserved = media_services.reserve_uploads(
        ctx, intents=[media_services.UploadIntent("photo", "image/jpeg", 5000)]
    )[0]
    store = get_object_store()
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), color="blue").save(buf, format="JPEG")
    item = RequestMedia.objects.get(id=reserved.item_id)
    store.put_object(item.quarantine_key, buf.getvalue(), content_type="image/jpeg")
    media_services.complete_upload(ctx, item_id=item.id)
    from ham.media.jobs import process_item

    process_item(str(item.id))
    item.refresh_from_db()
    assert item.status == "ready"
    return req, item


def _login(client, make_user, *, email: str, full_name: str, role: str):
    user = make_user(email)
    SharedIdentityProfile.objects.create(user=user, full_name=full_name)
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return user


@pytest.mark.parametrize(
    "role", ["HAM_DIRECTOR", "ASSISTANT_DIRECTOR", "PASTOR", "BOARD_REPRESENTATIVE"]
)
def test_leadership_can_view_thumb_and_full(client, make_user, role):
    req, item = _make_request_with_a_ready_photo()
    _login(client, make_user, email=f"{role.lower()}@example.org", full_name="Leader", role=role)

    thumb = client.get(reverse("web:request_media_thumb", args=[req.id, item.id]))
    assert thumb.status_code == 200
    assert thumb["Cache-Control"] == "no-store"
    assert thumb["Content-Type"] == "image/jpeg"

    full = client.get(reverse("web:request_media_view", args=[req.id, item.id]))
    assert full.status_code == 200
    assert full["Cache-Control"] == "no-store"


def test_administrator_cannot_view_individual_media(client, make_user):
    """PRD guardian M3: the Administrator holds `request_media.view` (route guard passes,
    count only -- Q-138) but must never reach an individual item."""
    req, item = _make_request_with_a_ready_photo()
    _login(client, make_user, email="admin@example.org", full_name="Admin", role="ADMINISTRATOR")

    thumb = client.get(reverse("web:request_media_thumb", args=[req.id, item.id]))
    assert thumb.status_code == 403

    full = client.get(reverse("web:request_media_view", args=[req.id, item.id]))
    assert full.status_code == 403


def test_volunteer_cannot_view_media_at_all(client, make_user):
    req, item = _make_request_with_a_ready_photo()
    _login(client, make_user, email="volunteer@example.org", full_name="Vol", role="VOLUNTEER")

    resp = client.get(reverse("web:request_media_thumb", args=[req.id, item.id]))
    assert resp.status_code in (403, 404)


def test_unready_item_is_not_found(client, make_user):
    req, item = _make_request_with_a_ready_photo()
    item.status = "processing"
    item.save(update_fields=["status"])
    _login(client, make_user, email="director2@example.org", full_name="Dir", role="HAM_DIRECTOR")
    resp = client.get(reverse("web:request_media_thumb", args=[req.id, item.id]))
    assert resp.status_code == 404


def test_thumb_route_for_a_different_request_is_not_found(client, make_user):
    req1, item1 = _make_request_with_a_ready_photo()
    req2, _item2 = _make_request_with_a_ready_photo()
    _login(client, make_user, email="director3@example.org", full_name="Dir", role="HAM_DIRECTOR")
    resp = client.get(reverse("web:request_media_thumb", args=[req2.id, item1.id]))
    assert resp.status_code == 404


# --------------------------------------------------------------------------------------
# PRD guardian N11: the requester secure page shows batch state + the leader's reopen reason.
# The context contract below is what FIX-C's R9/R10 templates consume (`batch_open`,
# `batch_reopen_reason`) -- asserted on `response.context` (Django's test client records the
# render context via a signal) rather than on rendered HTML, since the template itself is
# FIX-C's to wire up.
# --------------------------------------------------------------------------------------
def test_secure_page_context_carries_batch_state_when_open(client):
    req, _item = _make_request_with_a_ready_photo()

    from ham.requester_portal import services as portal_services
    from ham.requester_portal.models import RequesterAccessLink

    issued = portal_services.issue_link(request_id=req.id, kind=RequesterAccessLink.KIND_INITIAL)

    resp = client.get(reverse("web:request_help_secure_page", kwargs={"token": issued.token}))
    assert resp.status_code == 200
    assert resp.context["batch_open"] is True
    assert resp.context["batch_reopen_reason"] == ""


def test_secure_page_context_carries_the_leaders_reopen_reason(client):
    req, _item = _make_request_with_a_ready_photo()
    from ham.authz import roles as ham_roles
    from ham.authz.context import ActorContext

    director_ctx = ActorContext(
        user_id=uuid.UUID("00000000-0000-7000-8000-000000000009"),
        real_user_id=None,
        roles=frozenset({ham_roles.HAM_DIRECTOR}),
        is_active=True,
        mfa_satisfied=True,
    )
    media_services.close_open_batches(req.id, reason_code="decision")
    media_services.reopen_batch(director_ctx, request_id=req.id, reason="need the ceiling too")

    from ham.requester_portal import services as portal_services
    from ham.requester_portal.models import RequesterAccessLink

    issued = portal_services.issue_link(request_id=req.id, kind=RequesterAccessLink.KIND_INITIAL)

    resp = client.get(reverse("web:request_help_secure_page", kwargs={"token": issued.token}))
    assert resp.status_code == 200
    assert resp.context["batch_open"] is True
    assert resp.context["batch_reopen_reason"] == "need the ceiling too"


def test_secure_page_context_shows_batch_closed_once_uploads_close(client):
    req, _item = _make_request_with_a_ready_photo()
    media_services.close_open_batches(req.id, reason_code="decision")

    from ham.requester_portal import services as portal_services
    from ham.requester_portal.models import RequesterAccessLink

    issued = portal_services.issue_link(request_id=req.id, kind=RequesterAccessLink.KIND_INITIAL)

    resp = client.get(reverse("web:request_help_secure_page", kwargs={"token": issued.token}))
    assert resp.status_code == 200
    assert resp.context["batch_open"] is False
