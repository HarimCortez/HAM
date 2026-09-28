"""S2.4b `ham.media.jobs` (Q-120 processing job; §47/Q-128 retention sweep)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest

from ham.audit.models import AuditEvent
from ham.media import jobs as media_jobs
from ham.media import processing, services
from ham.media.models import (
    FAILURE_PROCESSING_UNAVAILABLE,
    STATUS_READY,
    STATUS_UPLOADED,
    RequestMedia,
)
from ham.media.services import UploadIntent
from ham.platform.clock import FixedClock, set_clock
from ham.platform.storage import get_object_store
from ham.requests.states import RequestStatus
from ham.rules import RULES

pytestmark = pytest.mark.django_db


def _uploaded_photo_item(open_request):
    from ham.authz.context import RequesterContext

    ctx = RequesterContext(request_id=open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    store = get_object_store()

    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (200, 100), color="red").save(buf, format="JPEG")
    quarantine_key = RequestMedia.objects.get(id=reserved.item_id).quarantine_key
    store.put_object(quarantine_key, buf.getvalue(), content_type="image/jpeg")
    item = services.complete_upload(ctx, item_id=reserved.item_id)
    assert item.status == STATUS_UPLOADED
    return item


def test_process_item_photo_produces_ready_derivative(open_request):
    item = _uploaded_photo_item(open_request)
    store = get_object_store()

    media_jobs.process_item(str(item.id))

    item.refresh_from_db()
    assert item.status == STATUS_READY
    assert item.storage_key and item.thumb_key
    assert item.width and item.height
    assert store.head(item.storage_key) is not None
    assert store.head(item.thumb_key) is not None
    # original deleted (Q-120)
    assert store.head(item.quarantine_key) is None


def test_process_item_video_degrades_when_ffmpeg_unavailable(open_request):
    from ham.authz.context import RequesterContext

    ctx = RequesterContext(request_id=open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("video", "video/mp4", 1000)])[0]
    store = get_object_store()
    item = RequestMedia.objects.get(id=reserved.item_id)
    store.put_object(item.quarantine_key, b"fake video bytes", content_type="video/mp4")
    item = services.complete_upload(ctx, item_id=reserved.item_id)

    with patch.object(processing, "ffmpeg_available", return_value=False):
        media_jobs.process_item(str(item.id))

    item.refresh_from_db()
    assert item.status == "rejected"
    assert item.failure_code == FAILURE_PROCESSING_UNAVAILABLE
    assert store.head(item.quarantine_key) is None  # original never kept/served
    assert AuditEvent.objects.filter(
        action="request_media.rejected", target_id=str(item.id)
    ).exists()


def test_process_item_skips_if_not_uploaded(open_request):
    item = _uploaded_photo_item(open_request)
    item.status = STATUS_READY
    item.save(update_fields=["status"])
    # calling again should be a safe no-op (already processed / raced)
    media_jobs.process_item(str(item.id))
    item.refresh_from_db()
    assert item.status == STATUS_READY


def test_retention_sweep_purges_media_past_the_clock_from_cancellation(open_request):
    item = _uploaded_photo_item(open_request)
    media_jobs.process_item(str(item.id))
    item.refresh_from_db()
    assert item.status == STATUS_READY

    open_request.status = RequestStatus.CANCELLED.value
    open_request.closed_at = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    open_request.save(update_fields=["status", "closed_at"])

    storage_key, thumb_key = item.storage_key, item.thumb_key
    period = RULES.media.PHOTO_RETENTION_AFTER_CLOSE
    set_clock(FixedClock(open_request.closed_at + period + dt.timedelta(seconds=1)))
    purged = media_jobs.retention_sweep(0)

    item.refresh_from_db()
    assert purged == 1
    assert item.status == "purged"
    store = get_object_store()
    assert store.head(storage_key) is None
    assert store.head(thumb_key) is None
    assert AuditEvent.objects.filter(action="request_media.purged", target_id=str(item.id)).exists()


def test_retention_sweep_does_not_purge_before_the_clock(open_request):
    item = _uploaded_photo_item(open_request)
    media_jobs.process_item(str(item.id))
    item.refresh_from_db()

    open_request.status = RequestStatus.CANCELLED.value
    open_request.closed_at = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    open_request.save(update_fields=["status", "closed_at"])

    set_clock(FixedClock(open_request.closed_at + dt.timedelta(days=1)))
    purged = media_jobs.retention_sweep(0)

    item.refresh_from_db()
    assert purged == 0
    assert item.status == STATUS_READY


def test_retention_sweep_leaves_open_requests_alone(open_request):
    item = _uploaded_photo_item(open_request)
    media_jobs.process_item(str(item.id))
    set_clock(FixedClock(dt.datetime(2030, 1, 1, tzinfo=dt.UTC)))
    purged = media_jobs.retention_sweep(0)
    item.refresh_from_db()
    assert purged == 0
    assert item.status == STATUS_READY
