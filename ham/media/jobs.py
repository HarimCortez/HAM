"""S2.4b background jobs (`ham.jobs`, PRD §78): media processing and the retention sweep.

`media.process_item` is deferred by `ham.media.services.complete_upload` right after an
upload is confirmed. `media.retention_sweep` is a `periodic_job` (§47, Q-128) that purges
photos/videos past their retention clock on a closed/cancelled request.
"""

from __future__ import annotations

import logging

from ham import jobs
from ham.audit.services import record as audit_record
from ham.authz.context import SystemContext
from ham.platform.clock import now as clock_now
from ham.platform.ids import uuid7
from ham.platform.storage import get_object_store
from ham.rules import RULES, media_retention_period

from . import processing
from .models import (
    FAILURE_PROCESSING_UNAVAILABLE,
    MEDIA_KIND_PHOTO,
    STATUS_PROCESSING,
    STATUS_PURGED,
    STATUS_READY,
    STATUS_UPLOADED,
    RequestMedia,
)

logger = logging.getLogger(__name__)

_SYSTEM = SystemContext()


def _mark_rejected(item: RequestMedia, *, failure_code: str) -> None:
    item.status = "rejected"
    item.failure_code = failure_code
    item.save(update_fields=["status", "failure_code"])
    store = get_object_store()
    if item.quarantine_key:
        store.delete(item.quarantine_key)  # Q-120: never keep/serve the original
    audit_record(
        ctx=_SYSTEM,
        action="request_media.rejected",
        target_type="request_media",
        target_id=str(item.id),
        reason=failure_code,
        context={"request_id": str(item.request_id)},
    )


@jobs.job(name="media.process_item")
def process_item(item_id: str) -> None:
    """Re-encodes one uploaded item (Q-120), then deletes the original either way."""
    try:
        item = RequestMedia.objects.select_related("batch").get(id=item_id)
    except RequestMedia.DoesNotExist:  # pragma: no cover - defensive, removed mid-flight
        return
    if item.status != STATUS_UPLOADED:
        return  # already processed, removed, or reprocessed by a retried job

    item.status = STATUS_PROCESSING
    item.save(update_fields=["status"])

    store = get_object_store()
    try:
        original = store.get_object(item.quarantine_key)
    except FileNotFoundError:
        _mark_rejected(item, failure_code="corrupt")
        return

    try:
        if item.media_kind == MEDIA_KIND_PHOTO:
            photo = processing.process_photo(original)
            storage_key, thumb_key = f"media/{uuid7()}", f"thumb/{uuid7()}"
            store.put_object(storage_key, photo.data, content_type=photo.content_type)
            store.put_object(thumb_key, photo.thumbnail, content_type="image/jpeg")
            width, height, duration_ms = photo.width, photo.height, None
        else:
            max_ms = int(RULES.media.REQUESTER_MEDIA_MAX_VIDEO_DURATION.total_seconds() * 1000)
            video = processing.process_video(original, max_duration_ms=max_ms)
            storage_key, thumb_key = f"media/{uuid7()}", ""
            store.put_object(storage_key, video.data, content_type=video.content_type)
            width, height, duration_ms = video.width, video.height, video.duration_ms
    except processing.ProcessingUnavailable:
        _mark_rejected(item, failure_code=FAILURE_PROCESSING_UNAVAILABLE)
        return
    except processing.ProcessingError as exc:
        _mark_rejected(item, failure_code=exc.code)
        return

    store.delete(item.quarantine_key)  # originals are never kept once a derivative exists

    item.status = STATUS_READY
    item.storage_key = storage_key
    item.thumb_key = thumb_key
    item.width = width
    item.height = height
    item.duration_ms = duration_ms
    item.processed_at = clock_now()
    item.save(
        update_fields=[
            "status",
            "storage_key",
            "thumb_key",
            "width",
            "height",
            "duration_ms",
            "processed_at",
        ]
    )


def _purge_item(item: RequestMedia, *, closing_status: str) -> None:
    store = get_object_store()
    for key in (item.storage_key, item.thumb_key, item.quarantine_key):
        if key:
            store.delete(key)
    item.status = STATUS_PURGED
    item.storage_key = ""
    item.thumb_key = ""
    item.purged_at = clock_now()
    item.save(update_fields=["status", "storage_key", "thumb_key", "purged_at"])
    audit_record(
        ctx=_SYSTEM,
        action="request_media.purged",
        target_type="request_media",
        target_id=str(item.id),
        reason=closing_status,
        context={"request_id": str(item.request_id)},
    )


@jobs.periodic_job(name="media.retention_sweep", cron="0 3 * * *")
def retention_sweep(timestamp: int) -> int:
    """Daily (03:00 UTC): purge every `ready`/`rejected` item whose request has been
    closed/cancelled long enough (§47, Q-128). Returns the count purged, for tests/logs."""
    from ham.requests.models import AssistanceRequest
    from ham.requests.states import RequestStatus

    now = clock_now()
    purged = 0
    closing_statuses = (
        RequestStatus.CANCELLED.value,
        RequestStatus.REJECTED.value,
        # Step 2 has no COMPLETED status yet (it lands with later steps); the retention
        # sweep is written generically against `ham.rules.media_retention_period`'s full set
        # so it needs no change when COMPLETED becomes reachable.
    )
    requests = AssistanceRequest.objects.filter(
        status__in=closing_statuses, closed_at__isnull=False
    ).only("id", "status", "closed_at")
    for request in requests:
        closed_at = request.closed_at
        if closed_at is None:  # pragma: no cover - excluded by closed_at__isnull=False above
            continue
        items = RequestMedia.objects.filter(
            request_id=request.id, status__in=(STATUS_READY, "rejected")
        )
        for item in items:
            try:
                period = media_retention_period(item.media_kind, request.status)
            except ValueError:
                continue  # no rule for this status (defensive; closing_statuses is filtered)
            if period is None:
                continue
            if now >= closed_at + period:
                _purge_item(item, closing_status=request.status)
                purged += 1
    return purged
