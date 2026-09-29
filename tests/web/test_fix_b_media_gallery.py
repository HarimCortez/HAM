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
def _real_portal_lookups(real_portal_lookups):
    """Order-dependence fix (test-engineer pass, step 3): this module used to register its
    *own* copy of the real lookups and reset the globals to `None` on teardown rather than
    restoring them -- exactly the pre-shared-fixture pattern `tests/conftest.py::
    real_portal_lookups`'s own docstring describes and was written to replace (a `None`
    teardown is only safe if this happens to be the *last* portal-touching test to run in the
    process; running the suite in reverse file order confirmed it is not: this file sits
    early in `tests/web/`'s reverse order and its `None` teardown poisoned every later file
    that assumed the app-startup registration, or an earlier file's own restore, was still
    intact -- `tests/e2e/test_step3_requester_screens.py` and `tests/e2e/test_fix_f1_
    upload.py` both failed with `RuntimeError: ham.requester_portal.services used before
    ham.requests registered its request-facts lookup` as a direct result). This module calls
    `ham.requester_portal.services.issue_link` directly (N11's secure-page tests), so it still
    can't rely on `RequesterPortalConfig.ready()`'s startup registration alone -- depending on
    the shared fixture keeps that guarantee while also restoring the real callables on
    teardown instead of `None`."""


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


def test_gallery_viewer_opens_in_same_tab(client, make_user):
    """FIX-F1 Gallery: `target="_blank"` used to strand a leader in a new tab with no "Back"
    on a phone."""
    req, _item = _make_request_with_a_ready_photo()
    _login(client, make_user, email="director3@example.org", full_name="Dir3", role="HAM_DIRECTOR")
    resp = client.get(reverse("web:request_detail", args=[req.id]))
    assert resp.status_code == 200
    assert b'target="_blank"' not in resp.content


def test_gallery_has_one_role_status_region():
    """FIX-F1 Gallery: one shared `role="status"` region for the whole gallery, not one per
    processing chip (each was separately announced on load, and every chip re-announcing on
    load was the actual bug -- a single request with 2+ processing items reproduces it)."""
    from dataclasses import dataclass

    from django.template.loader import render_to_string

    @dataclass
    class FakeItem:
        id: str
        media_kind: str
        status: str
        index: int
        failure_code: str = ""

    @dataclass
    class FakeCounts:
        photos: int
        videos: int

    @dataclass
    class FakeGallery:
        counts: FakeCounts
        items: tuple

    gallery = FakeGallery(
        counts=FakeCounts(photos=2, videos=0),
        items=(
            FakeItem(id="a", media_kind="photo", status="processing", index=1),
            FakeItem(id="b", media_kind="photo", status="processing", index=2),
        ),
    )
    html = render_to_string(
        "web/_request_media_gallery.html",
        {"detail": {"id": "req-1", "display_number": "HAM #001"}, "gallery": gallery},
    )
    assert html.count('role="status"') == 1


def test_gallery_fallback_chip_shows_a_label_not_the_raw_status():
    """FIX-F1 Gallery: the fallback chip's status code used to render verbatim
    (`{{ item.status }}`) instead of through a label map. `media_gallery_for` doesn't
    currently surface a status that hits this branch (only ready/processing/uploaded/
    rejected+processing_unavailable reach the template) -- render the partial directly with a
    synthetic item, as a defensive-code guarantee for any future status."""
    from dataclasses import dataclass

    from django.template.loader import render_to_string

    @dataclass
    class FakeItem:
        id: str
        media_kind: str
        status: str
        index: int
        failure_code: str = ""

    @dataclass
    class FakeCounts:
        photos: int
        videos: int

    @dataclass
    class FakeGallery:
        counts: FakeCounts
        items: tuple

    gallery = FakeGallery(
        counts=FakeCounts(photos=1, videos=0),
        items=(FakeItem(id="x", media_kind="photo", status="purged", index=1),),
    )
    html = render_to_string(
        "web/_request_media_gallery.html",
        {"detail": {"id": "req-1", "display_number": "HAM #001"}, "gallery": gallery},
    )
    assert "Purged" in html
    assert "&middot; purged<" not in html


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
