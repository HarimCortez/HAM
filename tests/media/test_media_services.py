"""S2.4b `ham.media.services` (intake.md §3, §4, §7; Q-114/Q-118, Q-119, Q-138)."""

from __future__ import annotations

import threading
import uuid

import pytest

from ham.authz import roles
from ham.authz.commands import PermissionDenied
from ham.authz.context import ActorContext, RequesterContext
from ham.media import services
from ham.media.models import (
    STATUS_READY,
    STATUS_REMOVED,
    STATUS_RESERVED,
    STATUS_UPLOADED,
    RequestMedia,
    RequestMediaBatch,
)
from ham.media.services import MediaValidationError, UploadIntent
from ham.platform.clock import now as clock_now
from ham.platform.storage import get_object_store
from ham.requests.states import RequestStatus
from ham.rules import RULES

pytestmark = pytest.mark.django_db


def _requester_ctx(request_id):
    return RequesterContext(request_id=request_id)


def _director_ctx():
    return ActorContext(
        user_id=uuid.UUID("00000000-0000-7000-8000-000000000001"),
        real_user_id=None,
        roles=frozenset({roles.HAM_DIRECTOR}),
        is_active=True,
        mfa_satisfied=True,
    )


def _admin_ctx():
    return ActorContext(
        user_id=uuid.UUID("00000000-0000-7000-8000-000000000002"),
        real_user_id=None,
        roles=frozenset({roles.ADMINISTRATOR}),
        is_active=True,
        mfa_satisfied=True,
    )


# --- reserve_uploads --------------------------------------------------------------------
def test_reserve_uploads_returns_presigned_urls(open_request):
    ctx = _requester_ctx(open_request.id)
    intents = [UploadIntent("photo", "image/jpeg", 1000)]
    reserved = services.reserve_uploads(ctx, intents=intents)
    assert len(reserved) == 1
    item = RequestMedia.objects.get(id=reserved[0].item_id)
    assert item.status == STATUS_RESERVED
    assert item.request_id == open_request.id
    assert reserved[0].upload.url


def test_reserve_uploads_rejects_unsupported_type(open_request):
    ctx = _requester_ctx(open_request.id)
    with pytest.raises(MediaValidationError):
        services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/gif", 1000)])


def test_reserve_uploads_rejects_oversize_declared_bytes(open_request):
    ctx = _requester_ctx(open_request.id)
    too_big = RULES.media.REQUESTER_PHOTO_MAX_BYTES + 1
    with pytest.raises(MediaValidationError):
        services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", too_big)])


def test_reserve_uploads_refuses_without_a_request(open_request):
    ctx = RequesterContext(request_id=None)
    with pytest.raises(PermissionDenied):
        services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])


def test_reserve_uploads_refuses_on_closed_request(make_request):
    closed = make_request(status=RequestStatus.CANCELLED.value, closed_at=clock_now())
    ctx = _requester_ctx(closed.id)
    with pytest.raises(ValueError):
        services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])


def test_reserve_uploads_enforces_batch_photo_limit(open_request):
    ctx = _requester_ctx(open_request.id)
    max_photos = RULES.media.REQUESTER_MEDIA_BATCH_MAX_PHOTOS
    intents = [UploadIntent("photo", "image/jpeg", 1000) for _ in range(max_photos)]
    services.reserve_uploads(ctx, intents=intents)
    with pytest.raises(ValueError):
        services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])


def test_reserve_uploads_enforces_batch_video_limit(open_request):
    ctx = _requester_ctx(open_request.id)
    max_videos = RULES.media.REQUESTER_MEDIA_BATCH_MAX_VIDEOS
    intents = [UploadIntent("video", "video/mp4", 1000) for _ in range(max_videos)]
    services.reserve_uploads(ctx, intents=intents)
    with pytest.raises(ValueError):
        services.reserve_uploads(ctx, intents=[UploadIntent("video", "video/mp4", 1000)])


@pytest.mark.django_db(transaction=True)
def test_reserve_uploads_enforces_batch_limit_under_concurrency(local_storage):
    from .factories import create_request

    request = create_request()
    max_photos = RULES.media.REQUESTER_MEDIA_BATCH_MAX_PHOTOS
    attempts = max_photos + 5
    errors: list[Exception] = []
    successes: list[object] = []
    lock = threading.Lock()

    def worker() -> None:
        from django.db import connections

        try:
            ctx = _requester_ctx(request.id)
            result = services.reserve_uploads(
                ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)]
            )
            with lock:
                successes.append(result)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == max_photos
    assert len(errors) == attempts - max_photos
    held = RequestMedia.objects.filter(
        request_id=request.id, status__in=("reserved", "uploaded", "processing", "ready")
    ).count()
    assert held == max_photos


# --- complete_upload ---------------------------------------------------------------------
def _reserve_one(open_request, *, media_kind="photo", content_type="image/jpeg", size=1000):
    ctx = _requester_ctx(open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent(media_kind, content_type, size)])
    return ctx, reserved[0]


def test_complete_upload_success(open_request):
    ctx, reserved = _reserve_one(open_request)
    store = get_object_store()
    store.put_object(
        RequestMedia.objects.get(id=reserved.item_id).quarantine_key,
        b"x" * 1000,
        content_type="image/jpeg",
    )
    item = services.complete_upload(ctx, item_id=reserved.item_id)
    assert item.status == STATUS_UPLOADED
    assert item.bytes == 1000


def test_complete_upload_rejects_if_actual_size_too_large(open_request):
    ctx, reserved = _reserve_one(open_request)
    store = get_object_store()
    too_big = RULES.media.REQUESTER_PHOTO_MAX_BYTES + 10
    store.put_object(
        RequestMedia.objects.get(id=reserved.item_id).quarantine_key,
        b"x" * too_big,
        content_type="image/jpeg",
    )
    item = services.complete_upload(ctx, item_id=reserved.item_id)
    assert item.status == "rejected"
    assert item.failure_code == "too_large"
    assert store.head(item.quarantine_key) is None  # original deleted


def test_complete_upload_missing_object_raises(open_request):
    ctx, reserved = _reserve_one(open_request)
    with pytest.raises(ValueError):
        services.complete_upload(ctx, item_id=reserved.item_id)


def test_requester_cannot_complete_another_requests_item(open_request, make_request):
    other = make_request()
    ctx, reserved = _reserve_one(open_request)
    other_ctx = _requester_ctx(other.id)
    with pytest.raises(PermissionDenied):
        services.complete_upload(other_ctx, item_id=reserved.item_id)


def test_requester_cannot_remove_another_requests_item(open_request, make_request):
    other = make_request()
    ctx, reserved = _reserve_one(open_request)
    store = get_object_store()
    item = RequestMedia.objects.get(id=reserved.item_id)
    store.put_object(item.quarantine_key, b"x" * 100, content_type="image/jpeg")
    services.complete_upload(ctx, item_id=reserved.item_id)
    item.refresh_from_db()
    item.status = STATUS_READY
    item.save(update_fields=["status"])

    other_ctx = _requester_ctx(other.id)
    with pytest.raises(PermissionDenied):
        services.remove_item(other_ctx, item_id=reserved.item_id)


# --- remove_item ---------------------------------------------------------------------------
def test_remove_item_frees_the_slot_and_deletes_storage(open_request):
    ctx, reserved = _reserve_one(open_request)
    store = get_object_store()
    item = RequestMedia.objects.get(id=reserved.item_id)
    store.put_object(item.quarantine_key, b"x" * 100, content_type="image/jpeg")
    services.complete_upload(ctx, item_id=reserved.item_id)
    item.refresh_from_db()
    item.status = STATUS_READY
    item.storage_key = "media/fake"
    item.thumb_key = "thumb/fake"
    store.put_object(item.storage_key, b"y", content_type="image/jpeg")
    store.put_object(item.thumb_key, b"z", content_type="image/jpeg")
    item.save(update_fields=["status", "storage_key", "thumb_key"])

    removed = services.remove_item(ctx, item_id=reserved.item_id)
    assert removed.status == STATUS_REMOVED
    assert store.head("media/fake") is None
    assert store.head("thumb/fake") is None

    # slot is free again
    max_photos = RULES.media.REQUESTER_MEDIA_BATCH_MAX_PHOTOS
    services.reserve_uploads(
        ctx, intents=[UploadIntent("photo", "image/jpeg", 1000) for _ in range(max_photos)]
    )


def test_remove_item_refuses_if_not_ready(open_request):
    ctx, reserved = _reserve_one(open_request)
    with pytest.raises(ValueError):
        services.remove_item(ctx, item_id=reserved.item_id)


def test_remove_item_refuses_once_batch_is_closed(open_request):
    ctx, reserved = _reserve_one(open_request)
    item = RequestMedia.objects.get(id=reserved.item_id)
    item.status = STATUS_READY
    item.save(update_fields=["status"])
    services.close_open_batches(open_request.id, reason_code="test")
    with pytest.raises(ValueError):
        services.remove_item(ctx, item_id=reserved.item_id)


# --- reopen_batch ----------------------------------------------------------------------
def test_reopen_batch_requires_a_reason(open_request):
    ctx = _director_ctx()
    with pytest.raises(ValueError):
        services.reopen_batch(ctx, request_id=open_request.id, reason="")


def test_reopen_batch_closes_the_previous_one_and_opens_a_new_one(open_request):
    ctx = _requester_ctx(open_request.id)
    services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])
    first_batch = RequestMediaBatch.objects.get(request=open_request, number=1)
    assert first_batch.is_open

    leader_ctx = _director_ctx()
    new_batch = services.reopen_batch(
        leader_ctx, request_id=open_request.id, reason="need a photo of the roof"
    )
    first_batch.refresh_from_db()
    assert not first_batch.is_open
    assert new_batch.number == 2
    assert new_batch.kind == "reopened"
    assert new_batch.reason == "need a photo of the roof"


# --- close_open_batches ------------------------------------------------------------------
def test_close_open_batches_is_idempotent(open_request):
    ctx = _requester_ctx(open_request.id)
    services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])
    services.close_open_batches(open_request.id, reason_code="x")
    services.close_open_batches(open_request.id, reason_code="x")
    batch = RequestMediaBatch.objects.get(request=open_request, number=1)
    assert not batch.is_open


# --- media_gallery_for (Q-124, Q-138) ------------------------------------------------------
def test_administrator_sees_counts_only(open_request):
    ctx = _requester_ctx(open_request.id)
    store = get_object_store()
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    store.put_object(item.quarantine_key, b"x" * 100, content_type="image/jpeg")
    services.complete_upload(ctx, item_id=item.id)
    item.refresh_from_db()
    item.status = STATUS_READY
    item.save(update_fields=["status"])

    admin_view = services.media_gallery_for(_admin_ctx(), open_request.id)
    assert admin_view.counts.photos == 1
    assert admin_view.items is None

    director_view = services.media_gallery_for(_director_ctx(), open_request.id)
    assert director_view.counts.photos == 1
    assert director_view.items is not None
    assert len(director_view.items) == 1
