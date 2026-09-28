"""Fix round FIX-B: media security findings (security review H4/M2/M3/M4/L1/L3; PRD
guardian M3/M7/N6/N9/N10/N11). New file (test-engineer owns the pre-existing test files in
this same package) -- see `docs/handoff/wave-brief.md`.
"""

from __future__ import annotations

import uuid

import pytest

from ham.audit.models import AuditEvent
from ham.authz import roles
from ham.authz.context import ActorContext, RequesterContext
from ham.media import services
from ham.media.models import (
    FAILURE_PROCESSING_TIMED_OUT,
    FAILURE_PROCESSING_UNAVAILABLE,
    FAILURE_UPLOAD_EXPIRED,
    STATUS_PROCESSING,
    STATUS_RESERVED,
    STATUS_UPLOADED,
    RequestMedia,
    RequestMediaBatch,
)
from ham.media.services import UploadIntent, UploadsClosed
from ham.platform.clock import FixedClock, SystemClock, set_clock
from ham.platform.clock import now as clock_now
from ham.platform.storage import get_object_store
from ham.requests.models import Requester
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


def _admin_and_director_ctx():
    return ActorContext(
        user_id=uuid.UUID("00000000-0000-7000-8000-000000000003"),
        real_user_id=None,
        roles=frozenset({roles.ADMINISTRATOR, roles.HAM_DIRECTOR}),
        is_active=True,
        mfa_satisfied=True,
    )


def _give_email(request):
    Requester.objects.create(request=request, full_name="", email="on-file@example.org")


# --- L3 / M7: only ever auto-create batch #1 --------------------------------------------
def test_reserve_uploads_refuses_once_every_batch_is_closed(open_request):
    """Security review L3 / PRD guardian M7: once a leader has closed every batch (e.g. after
    a staff-opened reopened batch is later closed), a requester's own upload attempt must
    refuse -- never silently auto-open batch #2 on its own."""
    _give_email(open_request)
    ctx = _requester_ctx(open_request.id)
    services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])
    services.close_open_batches(open_request.id, reason_code="test")

    with pytest.raises(UploadsClosed, match="uploads are closed"):
        services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])

    assert RequestMediaBatch.objects.filter(request=open_request).count() == 1


def test_reopen_batch_still_allows_uploads_after_l3_refusal(open_request):
    """A leader's `reopen_batch` (not the requester's own auto-open) is still how batch #2+
    gets opened once #1 is closed."""
    _give_email(open_request)
    ctx = _requester_ctx(open_request.id)
    services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])
    services.close_open_batches(open_request.id, reason_code="test")

    batch = services.reopen_batch(_director_ctx(), request_id=open_request.id, reason="one more")
    assert batch.number == 2
    services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])  # no raise


# --- N10: reopen_batch refuses closed/cancelled and no-email requests -------------------
def test_reopen_batch_refuses_a_cancelled_request(make_request):
    cancelled = make_request(status=RequestStatus.CANCELLED.value, closed_at=clock_now())
    _give_email(cancelled)
    with pytest.raises(ValueError, match="closed"):
        services.reopen_batch(_director_ctx(), request_id=cancelled.id, reason="need more")


def test_reopen_batch_refuses_a_request_with_no_email_on_file(open_request):
    """No `Requester` row at all, same as a request that hasn't been given contact info --
    and the same as a `NEEDS_PHONE_CHECK` (Q-025) request, which never has an email."""
    with pytest.raises(ValueError, match="no email"):
        services.reopen_batch(_director_ctx(), request_id=open_request.id, reason="need more")


# --- N9: masking uses is_masked_view, not "holds the Administrator role" ----------------
def test_administrator_who_also_holds_a_leadership_role_sees_the_full_gallery(open_request):
    _give_email(open_request)
    ctx = _requester_ctx(open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    store = get_object_store()
    store.put_object(item.quarantine_key, b"x" * 100, content_type="image/jpeg")
    services.complete_upload(ctx, item_id=item.id)

    view = services.media_gallery_for(_admin_and_director_ctx(), open_request.id)
    assert view.items is not None
    assert len(view.items) == 1


# --- M4: spam purge deletes storage objects first ---------------------------------------
def test_purge_all_for_request_deletes_storage_and_audits(
    open_request, django_capture_on_commit_callbacks
):
    _give_email(open_request)
    ctx = _requester_ctx(open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    store = get_object_store()
    store.put_object(item.quarantine_key, b"x" * 100, content_type="image/jpeg")
    assert store.head(item.quarantine_key) is not None

    # N6: the actual `store.delete()` call only runs once the surrounding transaction commits
    # (`transaction.on_commit`) -- `django_capture_on_commit_callbacks(execute=True)` runs any
    # callbacks registered inside the `with` block once it exits, same as a real commit would.
    with django_capture_on_commit_callbacks(execute=True):
        purged = services.purge_all_for_request(open_request.id)

    assert purged == 1
    assert store.head(item.quarantine_key) is None
    event = AuditEvent.objects.get(action="request_media.purged", target_id=str(item.id))
    assert event.project_id == open_request.id


def test_spam_purge_calls_the_media_hook_before_deleting_the_request(
    open_request, django_capture_on_commit_callbacks
):
    """End-to-end through `ham.requests.services.purge_expired_request`'s registered hook
    (`ham.media.apps.MediaConfig.ready()`), not the media function directly."""
    from ham.requests.models import AssistanceRequest
    from ham.requests.services import purge_expired_request
    from ham.requests.states import CancelReason

    _give_email(open_request)
    ctx = _requester_ctx(open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    store = get_object_store()
    store.put_object(item.quarantine_key, b"x" * 100, content_type="image/jpeg")

    open_request.cancel_reason_code = CancelReason.SPAM.value
    open_request.save(update_fields=["cancel_reason_code"])

    from ham.authz.context import SystemContext

    with django_capture_on_commit_callbacks(execute=True):
        purge_expired_request(SystemContext(), request_id=open_request.id)

    assert store.head(item.quarantine_key) is None
    assert not AssistanceRequest.objects.filter(id=open_request.id).exists()
    assert AuditEvent.objects.filter(
        action="request_media.purged", context__request_id=str(open_request.id)
    ).exists()


def test_purge_expired_request_raises_if_media_purge_hook_not_registered(open_request, monkeypatch):
    """N6: an unregistered hook is a startup wiring bug, not something to silently skip --
    skipping would mean the spam purge quietly never deletes storage objects."""
    from ham.requests import services as requests_services
    from ham.requests.services import purge_expired_request
    from ham.requests.states import CancelReason

    open_request.cancel_reason_code = CancelReason.SPAM.value
    open_request.save(update_fields=["cancel_reason_code"])

    monkeypatch.setattr(requests_services, "_media_purge_hook", None)

    from ham.authz.context import SystemContext

    with pytest.raises(RuntimeError, match="no media purge hook registered"):
        purge_expired_request(SystemContext(), request_id=open_request.id)


# --- N6: media audit events carry project_id = request id -------------------------------
def test_complete_upload_rejection_audit_carries_project_id(open_request):
    ctx = _requester_ctx(open_request.id)
    reserved = services.reserve_uploads(
        ctx, intents=[UploadIntent("photo", "image/jpeg", RULES.media.REQUESTER_PHOTO_MAX_BYTES)]
    )[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    store = get_object_store()
    store.put_object(
        item.quarantine_key,
        b"x" * (RULES.media.REQUESTER_PHOTO_MAX_BYTES + 1),
        content_type="image/jpeg",
    )
    services.complete_upload(ctx, item_id=item.id)
    event = AuditEvent.objects.get(action="request_media.rejected", target_id=str(item.id))
    assert event.project_id == open_request.id


def test_reopen_batch_audit_carries_project_id(open_request):
    _give_email(open_request)
    batch = services.reopen_batch(_director_ctx(), request_id=open_request.id, reason="more")
    event = AuditEvent.objects.get(action="request_media.batch_opened", target_id=str(batch.id))
    assert event.project_id == open_request.id


# --- M2: process_item re-checks size via head() before get_object -----------------------
def test_process_item_rejects_an_oversized_object_found_at_processing_time(open_request):
    """Simulates the object at the quarantine key being larger than the declared/validated
    size by the time the worker runs (M2's "process_item heads + re-checks size before
    get_object") -- writes straight to storage, bypassing `complete_upload`'s own check."""
    from ham.media import jobs as media_jobs

    ctx = _requester_ctx(open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    store = get_object_store()
    store.put_object(item.quarantine_key, b"x" * 100, content_type="image/jpeg")
    services.complete_upload(ctx, item_id=item.id)

    # Swap in an oversized object after completion (TOCTOU simulation).
    too_big = RULES.media.REQUESTER_PHOTO_MAX_BYTES + 1
    store.put_object(item.quarantine_key, b"x" * too_big, content_type="image/jpeg")

    media_jobs.process_item(str(item.id))

    item.refresh_from_db()
    assert item.status == "rejected"
    assert item.failure_code == "too_large"
    assert store.head(item.quarantine_key) is None


# --- M3: periodic sweeper for stale reserved/uploaded/processing items ------------------
def test_sweep_releases_a_stale_reservation_past_its_lifetime(open_request):
    from ham.media import jobs as media_jobs

    ctx = _requester_ctx(open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    assert item.status == STATUS_RESERVED

    later = (
        clock_now()
        + RULES.media.MEDIA_UPLOAD_INTENT_LIFETIME
        + RULES.media.MEDIA_UPLOAD_INTENT_LIFETIME
    )
    set_clock(FixedClock(later))
    try:
        released = media_jobs.sweep_stale_uploads(0)
    finally:
        set_clock(SystemClock())

    assert released == 1
    item.refresh_from_db()
    assert item.status == "rejected"
    assert item.failure_code == FAILURE_UPLOAD_EXPIRED


def test_sweep_frees_the_slot_so_a_new_upload_can_be_reserved(open_request):
    from ham.media import jobs as media_jobs
    from ham.rules import RULES as R

    ctx = _requester_ctx(open_request.id)
    intents = [UploadIntent("photo", "image/jpeg", 1000)] * R.media.REQUESTER_MEDIA_BATCH_MAX_PHOTOS
    services.reserve_uploads(ctx, intents=intents)
    with pytest.raises(ValueError, match="not enough free photo slots"):
        services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])

    later = (
        clock_now() + R.media.MEDIA_UPLOAD_INTENT_LIFETIME + R.media.MEDIA_UPLOAD_INTENT_LIFETIME
    )
    set_clock(FixedClock(later))
    try:
        media_jobs.sweep_stale_uploads(0)
    finally:
        set_clock(SystemClock())

    services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])  # no raise


def test_sweep_releases_an_item_stuck_in_processing(open_request):
    from ham.media import jobs as media_jobs

    ctx = _requester_ctx(open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    store = get_object_store()
    store.put_object(item.quarantine_key, b"x" * 100, content_type="image/jpeg")
    services.complete_upload(ctx, item_id=item.id)
    item.refresh_from_db()
    assert item.status == STATUS_UPLOADED
    item.status = STATUS_PROCESSING
    item.save(update_fields=["status"])

    later = (
        clock_now() + RULES.media.MEDIA_PROCESSING_TIMEOUT + RULES.media.MEDIA_PROCESSING_TIMEOUT
    )
    set_clock(FixedClock(later))
    try:
        released = media_jobs.sweep_stale_uploads(0)
    finally:
        set_clock(SystemClock())

    assert released == 1
    item.refresh_from_db()
    assert item.status == "rejected"
    assert item.failure_code == FAILURE_PROCESSING_TIMED_OUT


def test_sweep_leaves_fresh_items_alone(open_request):
    from ham.media import jobs as media_jobs

    ctx = _requester_ctx(open_request.id)
    services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])
    assert media_jobs.sweep_stale_uploads(0) == 0


# --- gallery: processing_unavailable is shown distinctly, not silently hidden -----------
def test_gallery_surfaces_a_processing_unavailable_item(open_request):
    _give_email(open_request)
    ctx = _requester_ctx(open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("video", "video/mp4", 1000)])[0]
    item = RequestMedia.objects.get(id=reserved.item_id)
    item.status = "rejected"
    item.failure_code = FAILURE_PROCESSING_UNAVAILABLE
    item.save(update_fields=["status", "failure_code"])

    view = services.media_gallery_for(_director_ctx(), open_request.id)
    assert view.items is not None
    assert len(view.items) == 1
    assert view.items[0].failure_code == FAILURE_PROCESSING_UNAVAILABLE
    # not counted as usable media
    assert view.counts.videos == 0
