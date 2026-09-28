"""`media_request_batch`, `media_request_item` (intake.md §3, S2.4b).

Storage keys (`quarantine_key`, `storage_key`, `thumb_key`) are random UUIDs (`ham.platform.
ids.uuid7`, prefixed by media kind) with no request/requester identifier in them at all
(§69, test hook "no PII in storage keys") — the *row* is access-controlled (`ham.authz`), not
the key.
"""

from __future__ import annotations

from django.db import models

from ham.platform.ids import UUID7Field

MEDIA_KIND_PHOTO = "photo"
MEDIA_KIND_VIDEO = "video"
MEDIA_KIND_CHOICES = ((MEDIA_KIND_PHOTO, "Photo"), (MEDIA_KIND_VIDEO, "Video"))

BATCH_KIND_INITIAL = "initial"
BATCH_KIND_REOPENED = "reopened"
BATCH_KIND_CHOICES = ((BATCH_KIND_INITIAL, "Initial"), (BATCH_KIND_REOPENED, "Reopened"))

STATUS_RESERVED = "reserved"
STATUS_UPLOADED = "uploaded"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_REJECTED = "rejected"
STATUS_REMOVED = "removed"
STATUS_PURGED = "purged"
STATUS_CHOICES = (
    (STATUS_RESERVED, "Reserved"),
    (STATUS_UPLOADED, "Uploaded"),
    (STATUS_PROCESSING, "Processing"),
    (STATUS_READY, "Ready"),
    (STATUS_REJECTED, "Rejected"),
    (STATUS_REMOVED, "Removed"),
    (STATUS_PURGED, "Purged"),
)
# A slot is taken by any item in one of these statuses (intake.md §3 "Slot counting").
SLOT_HOLDING_STATUSES = (STATUS_RESERVED, STATUS_UPLOADED, STATUS_PROCESSING, STATUS_READY)

FAILURE_TOO_LONG = "too_long"
FAILURE_TOO_LARGE = "too_large"
FAILURE_UNSUPPORTED = "unsupported"
FAILURE_CORRUPT = "corrupt"
# Not in intake.md's original list: this slice's degrade path (task brief) for when ffmpeg
# isn't available to re-encode a video at all — the item is marked failed and the original is
# still deleted (never served), rather than silently leaving it stuck in `processing` forever.
FAILURE_PROCESSING_UNAVAILABLE = "processing_unavailable"
FAILURE_CHOICES = (
    (FAILURE_TOO_LONG, "Too long"),
    (FAILURE_TOO_LARGE, "Too large"),
    (FAILURE_UNSUPPORTED, "Unsupported"),
    (FAILURE_CORRUPT, "Corrupt"),
    (FAILURE_PROCESSING_UNAVAILABLE, "Processing unavailable"),
)

UPLOADED_BY_REQUESTER = "requester"
UPLOADED_BY_USER = "user"
UPLOADED_BY_CHOICES = ((UPLOADED_BY_REQUESTER, "Requester"), (UPLOADED_BY_USER, "User"))


class RequestMediaBatch(models.Model):
    id = UUID7Field()
    request = models.ForeignKey(
        "requests.AssistanceRequest", on_delete=models.CASCADE, related_name="media_batches"
    )
    number = models.PositiveIntegerField()
    kind = models.CharField(max_length=16, choices=BATCH_KIND_CHOICES)
    # Null for the initial batch (opened by the requester's own submission, no staff actor).
    opened_by_user_id = models.UUIDField(null=True, blank=True)
    # Required when kind == "reopened" (§46) — enforced in ham.media.services, not here.
    reason = models.TextField(blank=True, default="")
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    # Snapshot of the rules in force when this batch was opened (§34/§76: a later rules
    # change must never retroactively change what an already-open batch allows).
    max_photos = models.PositiveIntegerField()
    max_videos = models.PositiveIntegerField()
    max_video_seconds = models.PositiveIntegerField()
    rules_version = models.CharField(max_length=32)

    class Meta:
        db_table = "media_request_batch"
        constraints = [
            models.UniqueConstraint(fields=["request", "number"], name="media_batch_unique_number")
        ]
        indexes = [models.Index(fields=["request", "closed_at"], name="media_batch_open_idx")]
        ordering = ("request_id", "number")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"RequestMediaBatch({self.id}, #{self.number}, {self.kind})"

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


class RequestMedia(models.Model):
    id = UUID7Field()
    request = models.ForeignKey(
        "requests.AssistanceRequest", on_delete=models.CASCADE, related_name="media_items"
    )
    batch = models.ForeignKey(RequestMediaBatch, on_delete=models.CASCADE, related_name="items")
    media_kind = models.CharField(max_length=8, choices=MEDIA_KIND_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_RESERVED)

    # Storage (ham.platform.storage keys — random, non-guessable, no request id in them).
    quarantine_key = models.CharField(max_length=200, blank=True, default="")
    storage_key = models.CharField(max_length=200, blank=True, default="")
    thumb_key = models.CharField(max_length=200, blank=True, default="")

    detected_type = models.CharField(max_length=64, blank=True, default="")
    bytes = models.PositiveBigIntegerField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    failure_code = models.CharField(max_length=32, blank=True, default="", choices=FAILURE_CHOICES)

    uploaded_by_type = models.CharField(max_length=16, choices=UPLOADED_BY_CHOICES)
    uploaded_by_user_id = models.UUIDField(null=True, blank=True)

    reserved_at = models.DateTimeField()
    uploaded_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "media_request_item"
        indexes = [
            models.Index(fields=["batch", "status"], name="media_item_batch_status_idx"),
            models.Index(fields=["request", "status"], name="media_item_request_status_idx"),
        ]
        ordering = ("reserved_at",)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"RequestMedia({self.id}, {self.media_kind}, {self.status})"
