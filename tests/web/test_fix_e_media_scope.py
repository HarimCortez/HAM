"""FIX-E N1 regression: a Pastor must not be able to fetch media bytes for a request that is
still `NEEDS_PHONE_CHECK` (Q-025: Director/Assistant Director only), even by guessing the
request/media ids directly -- `_serve_media` must scope through
`ham.requests.queries.get_request_by_id(ctx, request_id)` first, the same scoping every other
leadership screen already applies. Turned from the security re-check PoC
(``test_poc_media_scope.py``) into a real regression test. New file per wave brief.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.authz import roles
from ham.requests.models import AssistanceRequest
from tests.web.test_fix_b_media_gallery import _login, _make_request_with_a_ready_photo

pytestmark = pytest.mark.django_db


def test_pastor_cannot_fetch_needs_phone_check_media(client, make_user):
    req, item = _make_request_with_a_ready_photo()
    AssistanceRequest.objects.filter(pk=req.id).update(status="NEEDS_PHONE_CHECK")
    _login(client, make_user, email="p@example.org", full_name="Pastor P", role=roles.PASTOR)

    detail = client.get(reverse("web:request_detail", kwargs={"request_id": req.id}))
    assert detail.status_code == 404

    thumb = client.get(
        reverse("web:request_media_thumb", kwargs={"request_id": req.id, "media_id": item.id})
    )
    assert thumb.status_code == 404

    view = client.get(
        reverse("web:request_media_view", kwargs={"request_id": req.id, "media_id": item.id})
    )
    assert view.status_code == 404


def test_director_can_still_fetch_needs_phone_check_media(client, make_user):
    """Sanity check: the fix is a scoping fix, not a blanket denial -- Director/AD (who do see
    NEEDS_PHONE_CHECK requests, Q-025) still get the bytes."""
    req, item = _make_request_with_a_ready_photo()
    AssistanceRequest.objects.filter(pk=req.id).update(status="NEEDS_PHONE_CHECK")
    _login(
        client, make_user, email="d@example.org", full_name="Director D", role=roles.HAM_DIRECTOR
    )

    thumb = client.get(
        reverse("web:request_media_thumb", kwargs={"request_id": req.id, "media_id": item.id})
    )
    assert thumb.status_code == 200
    assert thumb["Cache-Control"] == "no-store"
