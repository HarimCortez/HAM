"""`ham.media`'s write path (S2.4b; intake.md §3, §4, §7, §9; Q-118, Q-119, Q-120, Q-138).

Two different levels of "consequential" here, on purpose:

- **Reserving** upload slots (`reserve_uploads`) is a technical pre-step — it hands out
  presigned PUT URLs for slots that are released again after
  `RULES.media.MEDIA_UPLOAD_INTENT_LIFETIME` if nothing is ever uploaded. It runs under a row
  lock for correctness (two phones can't both grab the tenth photo, intake.md §3) but is not
  itself in intake.md §6's declared audit-action list, so it is not `@command`-wrapped;
  authorization is the calling view's `@requires_action("requester.media.upload")` route guard
  (foundation.md §7), same as `ham.identity.services.list_users`.
- **Completing** an upload, **removing** an item, and **reopening** a batch are all in that
  audit list (`request_media.uploaded`/`.rejected`/`.removed`/`.batch_opened`) and go through
  `@command` (foundation.md §1 "one write path": authorize, audit, emit, one transaction).

Storage keys never contain a request/requester id (§69) — see `_new_key`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from django.db import transaction

from ham.authz import roles
from ham.authz.commands import CommandResult, OutboxSpec, PermissionDenied, command
from ham.platform.clock import now as clock_now
from ham.platform.ids import uuid7
from ham.platform.storage import PresignedUpload, get_object_store
from ham.rules import RULES, RULES_VERSION

from .models import (
    BATCH_KIND_INITIAL,
    BATCH_KIND_REOPENED,
    FAILURE_TOO_LARGE,
    FAILURE_UNSUPPORTED,
    MEDIA_KIND_PHOTO,
    MEDIA_KIND_VIDEO,
    SLOT_HOLDING_STATUSES,
    STATUS_READY,
    STATUS_REMOVED,
    STATUS_RESERVED,
    STATUS_UPLOADED,
    UPLOADED_BY_REQUESTER,
    RequestMedia,
    RequestMediaBatch,
)

if TYPE_CHECKING:
    from ham.authz.context import ActorContext, RequesterContext

# intake.md §5, §6: leadership roles that see the full gallery through `request_media.view`.
# The Administrator (Q-124/Q-138) also holds `request_media.view` but is deliberately not in
# this set: `media_gallery_for` masks the item list down to counts for it alone.
_FULL_ACCESS_ROLES = frozenset(
    {roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR, roles.PASTOR, roles.BOARD_REPRESENTATIVE}
)


class MediaValidationError(ValueError):
    """A requested upload intent fails a fixed rule (type, size, count) — not a permission
    problem, so it is a 4xx-with-explanation at the view layer, not `PermissionDenied`."""


@dataclass(frozen=True, slots=True)
class UploadIntent:
    media_kind: Literal["photo", "video"]
    content_type: str
    declared_bytes: int


@dataclass(frozen=True, slots=True)
class ReservedUpload:
    item_id: uuid.UUID
    media_kind: str
    upload: PresignedUpload


def _new_key(prefix: str) -> str:
    """A random, non-guessable key with no request/requester id in it (§69)."""
    return f"{prefix}/{uuid7()}"


def _accepted_types(media_kind: str) -> tuple[str, ...]:
    m = RULES.media
    return m.REQUESTER_PHOTO_TYPES if media_kind == MEDIA_KIND_PHOTO else m.REQUESTER_VIDEO_TYPES


def _max_bytes(media_kind: str) -> int:
    m = RULES.media
    if media_kind == MEDIA_KIND_PHOTO:
        return m.REQUESTER_PHOTO_MAX_BYTES
    return m.REQUESTER_VIDEO_MAX_BYTES


def _validate_intent(intent: UploadIntent) -> None:
    if intent.media_kind not in (MEDIA_KIND_PHOTO, MEDIA_KIND_VIDEO):
        raise MediaValidationError(f"unknown media kind {intent.media_kind!r}")
    if intent.content_type not in _accepted_types(intent.media_kind):
        raise MediaValidationError("unsupported file type")
    if intent.declared_bytes <= 0 or intent.declared_bytes > _max_bytes(intent.media_kind):
        raise MediaValidationError("file is too large")


def _get_or_open_initial_batch(request_id: uuid.UUID) -> RequestMediaBatch:
    """Row-locked get-or-create of request #1's batch (intake.md §3 "enforced under
    select_for_update() on the batch"). Must be called inside an open transaction.

    **Deliberately not audited** (CLAUDE.md priority 3, considered and left this way): opening
    batch #1 is a side effect of the requester's own `reserve_uploads` call for their own
    request -- itself already excluded from intake.md §6's audit-action list per this module's
    own docstring, since it is a technical pre-step, not a distinct decision by any actor. The
    consequential, audited event for requester media is the per-item `request_media.uploaded`
    (once a file actually lands), not the container being created. This is not the same as
    `reopen_batch` below (`request_media.batch_opened`, audited): that one is a deliberate
    staff decision to reopen media collection on an already-closed request, with its own
    reason -- a discrete leadership action worth a record, unlike a requester's first upload
    on their own still-open request opening their own batch #1."""
    batch = (
        RequestMediaBatch.objects.select_for_update()
        .filter(request_id=request_id, closed_at__isnull=True)
        .order_by("-number")
        .first()
    )
    if batch is not None:
        return batch
    next_number = RequestMediaBatch.objects.filter(request_id=request_id).count() + 1
    m = RULES.media
    return RequestMediaBatch.objects.create(
        id=uuid7(),
        request_id=request_id,
        number=next_number,
        kind=BATCH_KIND_INITIAL if next_number == 1 else BATCH_KIND_REOPENED,
        opened_by_user_id=None,
        reason="",
        opened_at=clock_now(),
        max_photos=m.REQUESTER_MEDIA_BATCH_MAX_PHOTOS,
        max_videos=m.REQUESTER_MEDIA_BATCH_MAX_VIDEOS,
        max_video_seconds=int(m.REQUESTER_MEDIA_MAX_VIDEO_DURATION.total_seconds()),
        rules_version=RULES_VERSION,
    )


def reserve_uploads(ctx: RequesterContext, *, intents: list[UploadIntent]) -> list[ReservedUpload]:
    """Reserves one slot per intent in the request's currently-open batch (opening it if
    needed) and returns a presigned PUT URL for each (intake.md §7 `POST
    /r/<token>/media/intents`). Raises `MediaValidationError` for a bad intent,
    `PermissionDenied` if there is no request yet, `ValueError` if the batch doesn't have
    enough free slots for all of them.
    """
    if ctx.request_id is None:
        raise PermissionDenied("requester.media.upload: no request in this session")
    from ham.requests.services import is_request_open

    if not is_request_open(ctx.request_id):
        raise ValueError("this request is no longer open for new uploads")
    if not intents:
        return []
    for intent in intents:
        _validate_intent(intent)

    wanted_photos = sum(1 for i in intents if i.media_kind == MEDIA_KIND_PHOTO)
    wanted_videos = sum(1 for i in intents if i.media_kind == MEDIA_KIND_VIDEO)

    store = get_object_store()
    reserved: list[ReservedUpload] = []
    with transaction.atomic():
        # Locks the request row itself first, so two concurrent "no batch yet" reservations
        # for the *same* request can't both decide to INSERT batch #1 (a plain SELECT ...
        # FOR UPDATE on RequestMediaBatch has nothing to lock when no row exists yet —
        # without this, two phones opening the initial batch at once race on the
        # (request, number) unique constraint instead of serializing cleanly).
        from ham.requests.models import AssistanceRequest

        AssistanceRequest.objects.select_for_update().get(id=ctx.request_id)
        batch = _get_or_open_initial_batch(ctx.request_id)
        existing = RequestMedia.objects.filter(batch=batch, status__in=SLOT_HOLDING_STATUSES)
        existing_photos = existing.filter(media_kind=MEDIA_KIND_PHOTO).count()
        existing_videos = existing.filter(media_kind=MEDIA_KIND_VIDEO).count()
        if existing_photos + wanted_photos > batch.max_photos:
            raise ValueError("not enough free photo slots in this batch")
        if existing_videos + wanted_videos > batch.max_videos:
            raise ValueError("not enough free video slots in this batch")

        now = clock_now()
        for intent in intents:
            key = _new_key("quarantine")
            item = RequestMedia.objects.create(
                id=uuid7(),
                request_id=ctx.request_id,
                batch=batch,
                media_kind=intent.media_kind,
                status=STATUS_RESERVED,
                quarantine_key=key,
                uploaded_by_type=UPLOADED_BY_REQUESTER,
                uploaded_by_user_id=None,
                reserved_at=now,
            )
            upload = store.presign_put(
                key,
                content_type=intent.content_type,
                max_bytes=_max_bytes(intent.media_kind),
                expires_in=RULES.media.PRESIGNED_UPLOAD_URL_LIFETIME,
            )
            reserved.append(
                ReservedUpload(item_id=item.id, media_kind=item.media_kind, upload=upload)
            )
    return reserved


def _media_item_resource(ctx: ActorContext, *, item_id: uuid.UUID, **_: object) -> object:
    return RequestMedia.objects.filter(id=item_id).select_related("batch").first()


@command("requester.media.upload", resource_from=_media_item_resource)
def complete_upload(ctx: RequesterContext, *, item_id: uuid.UUID) -> CommandResult:
    """Re-checks the actually-uploaded object's size (Q re-check on completion, intake.md §9)
    and enqueues processing. Raises `ValueError` if the item is not `reserved` or nothing was
    actually uploaded to its quarantine key."""
    item = RequestMedia.objects.select_for_update().select_related("batch").get(id=item_id)
    if item.status != STATUS_RESERVED:
        raise ValueError(f"media item is {item.status!r}, not reserved")

    store = get_object_store()
    meta = store.head(item.quarantine_key)
    if meta is None:
        raise ValueError("nothing was uploaded to this reservation yet")

    max_bytes = _max_bytes(item.media_kind)
    if meta.size > max_bytes:
        item.status = "rejected"
        item.failure_code = FAILURE_TOO_LARGE
        item.bytes = meta.size
        item.detected_type = meta.content_type
        item.save(update_fields=["status", "failure_code", "bytes", "detected_type"])
        store.delete(item.quarantine_key)
        return CommandResult(
            value=item,
            audit_action="request_media.rejected",
            target_type="request_media",
            target_id=str(item.id),
            context={"request_id": str(item.request_id)},
        )
    if meta.content_type not in _accepted_types(item.media_kind):
        item.status = "rejected"
        item.failure_code = FAILURE_UNSUPPORTED
        item.bytes = meta.size
        item.detected_type = meta.content_type
        item.save(update_fields=["status", "failure_code", "bytes", "detected_type"])
        store.delete(item.quarantine_key)
        return CommandResult(
            value=item,
            audit_action="request_media.rejected",
            target_type="request_media",
            target_id=str(item.id),
            context={"request_id": str(item.request_id)},
        )

    item.status = STATUS_UPLOADED
    item.bytes = meta.size
    item.detected_type = meta.content_type
    item.uploaded_at = clock_now()
    item.save(update_fields=["status", "bytes", "detected_type", "uploaded_at"])

    from ham import jobs

    jobs.defer("media.process_item", item_id=str(item.id))

    return CommandResult(
        value=item,
        audit_action="request_media.uploaded",
        target_type="request_media",
        target_id=str(item.id),
        context={"request_id": str(item.request_id)},
        outbox=OutboxSpec(
            event_type="RequestMediaStored",
            aggregate_type="request_media",
            aggregate_id=item.id,
            payload={
                "request_id": str(item.request_id),
                "media_id": str(item.id),
                "media_kind": item.media_kind,
            },
        ),
    )


@command("requester.media.remove", resource_from=_media_item_resource)
def remove_item(ctx: RequesterContext, *, item_id: uuid.UUID) -> CommandResult:
    """Requester removes their own item while its batch is still open (Q-118/Q-114)."""
    item = RequestMedia.objects.select_for_update().select_related("batch").get(id=item_id)
    if not item.batch.is_open:
        raise ValueError("this item's batch is no longer open")
    if item.status != STATUS_READY:
        raise ValueError(f"media item is {item.status!r}, not ready")

    store = get_object_store()
    for key in (item.storage_key, item.thumb_key, item.quarantine_key):
        if key:
            store.delete(key)

    item.status = STATUS_REMOVED
    item.removed_at = clock_now()
    item.save(update_fields=["status", "removed_at"])

    return CommandResult(
        value=item,
        audit_action="request_media.removed",
        target_type="request_media",
        target_id=str(item.id),
        context={"request_id": str(item.request_id)},
        outbox=OutboxSpec(
            event_type="RequestMediaDeleted",
            aggregate_type="request_media",
            aggregate_id=item.id,
            payload={
                "request_id": str(item.request_id),
                "media_id": str(item.id),
                "reason_code": "requester_removed",
            },
        ),
    )


def _request_resource(ctx: ActorContext, *, request_id: uuid.UUID, **_: object) -> object:
    @dataclass(frozen=True, slots=True)
    class _Resource:
        request_id: uuid.UUID

    return _Resource(request_id=request_id)


@command("request_media.reopen", resource_from=_request_resource)
def reopen_batch(ctx: ActorContext, *, request_id: uuid.UUID, reason: str) -> CommandResult:
    """Leadership "Ask for more photos" (§46, L11). A reason is required."""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("a reason is required to reopen a batch")

    with transaction.atomic():
        from ham.requests.models import AssistanceRequest

        AssistanceRequest.objects.select_for_update().get(id=request_id)
        close_open_batches(request_id, reason_code="reopened")
        m = RULES.media
        next_number = RequestMediaBatch.objects.filter(request_id=request_id).count() + 1
        batch = RequestMediaBatch.objects.create(
            id=uuid7(),
            request_id=request_id,
            number=next_number,
            kind=BATCH_KIND_REOPENED,
            opened_by_user_id=ctx.user_id,
            reason=reason,
            opened_at=clock_now(),
            max_photos=m.REQUESTER_MEDIA_BATCH_MAX_PHOTOS,
            max_videos=m.REQUESTER_MEDIA_BATCH_MAX_VIDEOS,
            max_video_seconds=int(m.REQUESTER_MEDIA_MAX_VIDEO_DURATION.total_seconds()),
            rules_version=RULES_VERSION,
        )

    return CommandResult(
        value=batch,
        audit_action="request_media.batch_opened",
        target_type="media_batch",
        target_id=str(batch.id),
        reason=reason,
        context={"request_id": str(request_id)},
        outbox=OutboxSpec(
            event_type="RequestMediaBatchOpened",
            aggregate_type="media_batch",
            aggregate_id=batch.id,
            payload={"request_id": str(request_id), "batch_id": str(batch.id)},
        ),
    )


def close_open_batches(request_id: uuid.UUID, *, reason_code: str) -> None:
    """Closes every still-open batch for `request_id` (intake.md §2 "media.services.
    close_open_batches(request_id)"). Called when the request is decided (step 3) or closed
    (`reason_code` is a free-text audit/debug hint, not persisted on the row — the batch's own
    `closed_at` is enough to know it happened). Plain function, not `@command`: it has no
    human actor of its own and is only ever called from inside another action's own
    transaction (a `@command` body, or an outbox subscriber reacting to that action's event).
    """
    RequestMediaBatch.objects.filter(request_id=request_id, closed_at__isnull=True).update(
        closed_at=clock_now()
    )


# --------------------------------------------------------------------------------------
# Read side (foundation.md §7: the *view* declares the action; these are plain queries).
# --------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MediaCounts:
    photos: int
    videos: int


@dataclass(frozen=True, slots=True)
class MediaItemView:
    id: uuid.UUID
    media_kind: str
    status: str
    ready: bool


@dataclass(frozen=True, slots=True)
class MediaGalleryView:
    counts: MediaCounts
    # None for the Administrator (Q-124, Q-138: view-only, photo count only, no reveal).
    items: tuple[MediaItemView, ...] | None


_VISIBLE_STATUSES = (STATUS_READY, "processing", STATUS_UPLOADED)


def media_gallery_for(ctx: ActorContext, request_id: uuid.UUID) -> MediaGalleryView:
    """`request_media.view` (leadership): the Administrator gets counts only (Q-138); every
    other role that reaches this action (Director/AD/Pastor/Board rep) gets the full list.
    Authorization that the caller may reach this action at all is the view's own
    `@requires_action("request_media.view")` — this only decides *how much* to show once
    that's already true (Q-124's masking is service-layer behaviour, not a matrix flag, same
    as `requester_pii.reveal`)."""
    items_qs = RequestMedia.objects.filter(
        request_id=request_id, status__in=_VISIBLE_STATUSES
    ).order_by("reserved_at")
    counts = MediaCounts(
        photos=items_qs.filter(media_kind=MEDIA_KIND_PHOTO).count(),
        videos=items_qs.filter(media_kind=MEDIA_KIND_VIDEO).count(),
    )
    has_full_access = bool(ctx.effective_roles & _FULL_ACCESS_ROLES)
    if not has_full_access:
        return MediaGalleryView(counts=counts, items=None)
    items = tuple(
        MediaItemView(
            id=i.id, media_kind=i.media_kind, status=i.status, ready=i.status == STATUS_READY
        )
        for i in items_qs
    )
    return MediaGalleryView(counts=counts, items=items)


def view_urls_for(request_id: uuid.UUID) -> dict[uuid.UUID, tuple[str | None, str | None]]:
    """`{item_id: (thumb_url, view_url)}` presigned GET URLs for every ready item of a
    request (intake.md §7 thumb/view endpoints), short-lived (`PRESIGNED_VIEW_URL_LIFETIME`).
    """
    store = get_object_store()
    out: dict[uuid.UUID, tuple[str | None, str | None]] = {}
    lifetime = RULES.media.PRESIGNED_VIEW_URL_LIFETIME
    for item in RequestMedia.objects.filter(request_id=request_id, status=STATUS_READY):
        thumb_url = (
            store.presign_get(item.thumb_key, expires_in=lifetime) if item.thumb_key else None
        )
        view_url = (
            store.presign_get(item.storage_key, expires_in=lifetime) if item.storage_key else None
        )
        out[item.id] = (thumb_url, view_url)
    return out
