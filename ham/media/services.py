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
from functools import partial
from typing import TYPE_CHECKING, BinaryIO, Literal

from django.db import transaction

from ham.audit.services import record as audit_record
from ham.authz.commands import CommandResult, OutboxSpec, PermissionDenied, command
from ham.authz.context import SystemContext
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


class UploadsClosed(ValueError):
    """Every batch for this request is closed and none was ever auto-opened by staff
    (security review L3 / PRD guardian M7): a requester may never open a new batch on their
    own once batch #1 (or any later, staff-opened batch) has closed -- only
    `reopen_batch` (a leadership decision, §46) may open batch #2 and on."""


def _get_or_open_initial_batch(request_id: uuid.UUID) -> RequestMediaBatch:
    """Row-locked get-or-create of request #1's batch (intake.md §3 "enforced under
    select_for_update() on the batch"). Must be called inside an open transaction.

    Security review L3 / PRD guardian M7: this **only ever creates batch #1**. If every batch
    for this request is already closed, it refuses (`UploadsClosed`) rather than silently
    opening a new one -- a requester uploading on their own can never reopen collection once
    staff or the initial batch itself has closed it; only `reopen_batch` (a deliberate
    leadership decision, `request_media.batch_opened`, audited) may do that.

    **Deliberately not audited** (CLAUDE.md priority 3, considered and left this way): opening
    batch #1 is a side effect of the requester's own `reserve_uploads` call for their own
    request -- itself already excluded from intake.md §6's audit-action list per this module's
    own docstring, since it is a technical pre-step, not a distinct decision by any actor. The
    consequential, audited event for requester media is the per-item `request_media.uploaded`
    (once a file actually lands), not the container being created."""
    batch = (
        RequestMediaBatch.objects.select_for_update()
        .filter(request_id=request_id, closed_at__isnull=True)
        .order_by("-number")
        .first()
    )
    if batch is not None:
        return batch
    if RequestMediaBatch.objects.filter(request_id=request_id).exists():
        raise UploadsClosed("uploads are closed")
    m = RULES.media
    return RequestMediaBatch.objects.create(
        id=uuid7(),
        request_id=request_id,
        number=1,
        kind=BATCH_KIND_INITIAL,
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
    `PermissionDenied` if there is no request yet, `UploadsClosed` (a `ValueError`) once every
    batch is closed and none may auto-open (L3/M7), `ValueError` if the batch doesn't have
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
                # Security review M2: sign the exact declared size (already validated <= the
                # type's rules-module cap by `_validate_intent` above), not just a ceiling.
                content_length=intent.declared_bytes,
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
            project_id=item.request_id,
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
            project_id=item.request_id,
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
        project_id=item.request_id,
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
        project_id=item.request_id,
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
    """Leadership "Ask for more photos" (§46, L11). A reason is required.

    PRD-GAP Q-173: the reopen guard is `ham.requests.states.accepts_media_reopen` -- only
    AWAITING_APPROVAL, RECONSIDERATION_PENDING or APPROVED, and never once closed. A plain
    `is_request_open` (``closed_at IS NULL``) used to be enough here in step 2, but step 3
    adds an open (reconsiderable) REJECTED request, which is not closed yet `is_request_open`
    would still say "open" -- that status must refuse a reopen too (the requester must ask
    for reconsideration first, approvals.md §2.2). PRD guardian N10: also refuses a no-email
    request (there is nothing to email the ask to -- Q-025's NEEDS_PHONE_CHECK path has no
    address on file at all, and a later-verified no-email request still has none)."""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("a reason is required to reopen a batch")

    from ham.requests.models import AssistanceRequest
    from ham.requests.states import accepts_media_reopen

    facts = AssistanceRequest.objects.filter(id=request_id).values("status", "closed_at").first()
    if facts is None:
        raise ValueError("this request does not exist")
    if not accepts_media_reopen(facts["status"], facts["closed_at"]):
        raise ValueError(
            "this request is closed or not yet in a state that accepts more photos; "
            "uploads can't be reopened"
        )

    from ham.requests.models import Requester

    if not Requester.objects.filter(request_id=request_id).exclude(email=None).exists():
        raise ValueError("this request has no email on file; there is no one to ask")

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
        project_id=request_id,
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
    # 1-based position among items of the same `media_kind` (accessible alt text, PRD M3 /
    # UX B1: "HAM #024, photo 3" -- never a filename or anything PII-derived).
    index: int
    # "" unless `status == "rejected"` and the reason is worth a leader knowing about (right
    # now only `processing_unavailable` -- a system limitation, not the requester's fault).
    failure_code: str = ""


@dataclass(frozen=True, slots=True)
class MediaGalleryView:
    counts: MediaCounts
    # None for the Administrator (Q-124, Q-138: view-only, photo count only, no reveal).
    items: tuple[MediaItemView, ...] | None


_VISIBLE_STATUSES = (STATUS_READY, "processing", STATUS_UPLOADED)
# PRD M3: a `processing_unavailable` item (the worker had no way to re-encode it, e.g. no
# ffmpeg on this deployment -- never the requester's fault) is worth showing leadership as its
# own state, distinct from every other silently-hidden rejection (too large/wrong type/corrupt
# stay invisible, same as before this fix round).


def media_gallery_for(ctx: ActorContext, request_id: uuid.UUID) -> MediaGalleryView:
    """`request_media.view` (leadership): the Administrator gets counts only (Q-138); every
    other role that reaches this action (Director/AD/Pastor/Board rep) gets the full list.
    Authorization that the caller may reach this action at all is the view's own
    `@requires_action("request_media.view")` — this only decides *how much* to show once
    that's already true (Q-124's masking is service-layer behaviour, not a matrix flag, same
    as `requester_pii.reveal`).

    PRD guardian N9: masking is decided by `ham.requests.queries.is_masked_view(ctx)` (true
    only when the Administrator role is what's granting access and no leadership role also
    would), never by "does this actor hold the Administrator role" alone -- someone who holds
    both Administrator and a leadership role must still see the full gallery."""
    from ham.requests.queries import is_masked_view

    from .models import FAILURE_PROCESSING_UNAVAILABLE

    visible_qs = RequestMedia.objects.filter(request_id=request_id, status__in=_VISIBLE_STATUSES)
    # Usable-media counts (Q-138's "photo count") never include an unprocessable item.
    counts = MediaCounts(
        photos=visible_qs.filter(media_kind=MEDIA_KIND_PHOTO).count(),
        videos=visible_qs.filter(media_kind=MEDIA_KIND_VIDEO).count(),
    )
    if is_masked_view(ctx):
        return MediaGalleryView(counts=counts, items=None)
    unavailable_qs = RequestMedia.objects.filter(
        request_id=request_id, status="rejected", failure_code=FAILURE_PROCESSING_UNAVAILABLE
    )
    items_qs = (visible_qs | unavailable_qs).order_by("reserved_at")
    photo_i = video_i = 0
    items = []
    for i in items_qs:
        if i.media_kind == MEDIA_KIND_PHOTO:
            photo_i += 1
            index = photo_i
        else:
            video_i += 1
            index = video_i
        items.append(
            MediaItemView(
                id=i.id,
                media_kind=i.media_kind,
                status=i.status,
                ready=i.status == STATUS_READY,
                index=index,
                failure_code=i.failure_code,
            )
        )
    return MediaGalleryView(counts=counts, items=tuple(items))


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


def get_ready_item(*, request_id: uuid.UUID, media_id: uuid.UUID) -> RequestMedia | None:
    """Looks up one `ready` item, scoped to `request_id` (PRD M3 leadership thumb/view
    routes). `None` if the item doesn't exist, isn't `ready` yet (still `processing`/etc.),
    or belongs to a different request -- callers treat every case the same (404), never
    distinguishing "wrong request" from "not found" (§68, no enumeration)."""
    return RequestMedia.objects.filter(
        id=media_id, request_id=request_id, status=STATUS_READY
    ).first()


def open_media_stream(
    item: RequestMedia, *, variant: Literal["thumb", "view"]
) -> tuple[BinaryIO, str] | None:
    """Opens a readable stream onto one derivative's bytes straight from storage for the
    leadership thumb/view routes (PRD M3 / UX B1; N1 fix: streamed through the app via
    `django.http.FileResponse`, never buffered whole into a Python `bytes` object, and never a
    client-visible presigned URL) so the route's own `Cache-Control: no-store` response header
    is the only thing that ever describes how long a browser may cache it. `None` if this
    variant has no key (e.g. a video's thumbnail -- videos get no `thumb_key`,
    ``ham.media.jobs.process_item``)."""
    key = item.thumb_key if variant == "thumb" else item.storage_key
    if not key:
        return None
    store = get_object_store()
    try:
        stream = store.open_object(key)
    except FileNotFoundError:  # pragma: no cover - defensive; ready implies the key exists
        return None
    if variant == "thumb":
        content_type = "image/jpeg"
    else:
        content_type = "image/jpeg" if item.media_kind == MEDIA_KIND_PHOTO else "video/mp4"
    return stream, content_type


@dataclass(frozen=True, slots=True)
class MediaBatchView:
    """PRD guardian N11: what the requester's own secure page shows about upload state --
    whether the current batch is still open, and (only when a leader reopened it) their
    reason, so "we asked for more photos: {reason}" can be shown without another round trip.
    """

    is_open: bool
    kind: str
    reason: str


def current_batch_view(request_id: uuid.UUID) -> MediaBatchView | None:
    """The request's most recent batch (by number), or `None` if none has ever been opened."""
    batch = RequestMediaBatch.objects.filter(request_id=request_id).order_by("-number").first()
    if batch is None:
        return None
    return MediaBatchView(is_open=batch.is_open, kind=batch.kind, reason=batch.reason)


def purge_all_for_request(request_id: uuid.UUID) -> int:
    """Deletes every stored object (original/derivative/thumbnail, whatever a given item still
    has a key for) belonging to `request_id`, and audits one `request_media.purged` event per
    item that held a key -- security review M4: the spam purge (`ham.requests.services.
    purge_expired_request`) used to `request.delete()` straight away, cascade-deleting the
    `RequestMedia`/`RequestMediaBatch` rows but leaving their objects orphaned in storage
    forever, since nothing ever told the object store to delete them.

    `ham.requests` sits *below* `ham.media` in the layers contract (`ham.web ->
    ham.requester_portal -> ham.media -> ham.requests -> ...`), so it may never import this
    function directly; `ham.media.apps.MediaConfig.ready()` registers it into
    `ham.requests.services.register_media_purge_hook` instead (the reverse of the lookup
    pattern `ham.requester_portal` uses for its own cross-app queries), and
    `purge_expired_request` calls the hook, inside its own transaction, before deleting the
    request row.

    Plain function, not `@command`: no human actor of its own (the human decision -- and its
    own audit event, `request.purged` -- belongs to the caller); always invoked from inside
    another action's own transaction, same as `close_open_batches` above.

    N6: the actual object-store deletions run via `transaction.on_commit` -- this function is
    always called from inside `purge_expired_request`'s own `@command`-wrapped
    `transaction.atomic()` block, right before it deletes the request row. Deleting storage
    objects synchronously, mid-transaction, means a later failure in that same transaction
    (e.g. the request-row delete, or the audit/outbox write `@command` does after this
    returns) rolls the DB back while the bytes are already gone from storage -- unrecoverable.
    Deferring to `on_commit` means storage deletion only ever runs once the whole purge has
    actually committed."""
    store = get_object_store()
    purged = 0
    for item in RequestMedia.objects.filter(request_id=request_id):
        keys = [k for k in (item.storage_key, item.thumb_key, item.quarantine_key) if k]
        if not keys:
            continue
        for key in keys:
            transaction.on_commit(partial(store.delete, key))
        audit_record(
            ctx=SystemContext(),
            action="request_media.purged",
            target_type="request_media",
            target_id=str(item.id),
            reason="spam_purge",
            project_id=request_id,
            context={"request_id": str(request_id)},
        )
        purged += 1
    return purged
