"""FIX-G UX minor: the installed PWA has no browser chrome, so opening a gallery thumbnail's
raw `/view` route stranded a leader with no way back. A minimal leadership viewer page
(`/requests/<id>/media/<mid>/`) wraps it with "<- Back to HAM #NNN"; gallery thumbnails now
link to that page, not the raw file. The raw `/view` route is unchanged (still what the
viewer page's own `<img>`/`<video>` embeds, same scope/masking/`no-store`).
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


def test_gallery_thumbnail_links_to_the_viewer_page_not_the_raw_file(client, make_user):
    req, item = _make_request_with_a_ready_photo()
    _login(client, make_user, email="director1@example.org", full_name="Dir", role="HAM_DIRECTOR")

    resp = client.get(reverse("web:request_detail", args=[req.id]))
    assert resp.status_code == 200
    html = resp.content.decode()
    viewer_path = reverse("web:request_media_viewer", args=[req.id, item.id])
    raw_view_path = reverse("web:request_media_view", args=[req.id, item.id])
    assert f'href="{viewer_path}"' in html
    assert f'href="{raw_view_path}"' not in html


def test_viewer_page_shows_image_and_a_back_link(client, make_user):
    req, item = _make_request_with_a_ready_photo()
    _login(client, make_user, email="director2@example.org", full_name="Dir", role="HAM_DIRECTOR")

    resp = client.get(reverse("web:request_media_viewer", args=[req.id, item.id]))
    assert resp.status_code == 200
    assert resp["Cache-Control"] == "no-store"
    html = resp.content.decode()
    assert f"Back to {req.display_number}" in html
    raw_view_path = reverse("web:request_media_view", args=[req.id, item.id])
    assert f'src="{raw_view_path}"' in html


def test_administrator_cannot_reach_the_viewer_page(client, make_user):
    req, item = _make_request_with_a_ready_photo()
    _login(client, make_user, email="admin2@example.org", full_name="Admin", role="ADMINISTRATOR")

    resp = client.get(reverse("web:request_media_viewer", args=[req.id, item.id]))
    assert resp.status_code == 403


def test_viewer_page_for_a_different_request_is_not_found(client, make_user):
    req1, item1 = _make_request_with_a_ready_photo()
    req2, _item2 = _make_request_with_a_ready_photo()
    _login(client, make_user, email="director3@example.org", full_name="Dir", role="HAM_DIRECTOR")

    resp = client.get(reverse("web:request_media_viewer", args=[req2.id, item1.id]))
    assert resp.status_code == 404
