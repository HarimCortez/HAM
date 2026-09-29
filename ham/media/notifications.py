"""Q-150 (build in step 3): in-app "New photos arrived · HAM #" to the leader who reopened
uploads, once per reopened batch (approvals.md §2.5, approvals-contracts.md §6).

Registered once from `MediaConfig.ready()`, onto the shared `ham.notifications.inapp`
subscriber -- the same `register_inapp` pattern `ham.requests.notifications` already uses.
Titles carry only the HAM # (§68); no requester name, address or media content.
"""

from __future__ import annotations

from ham.notifications.inapp import InAppNotice, register_inapp
from ham.outbox.models import OutboxEvent

from .models import BATCH_KIND_REOPENED, RequestMedia, RequestMediaBatch


def _build_new_photos_notice(event: OutboxEvent) -> InAppNotice | None:
    """Fires exactly once per reopened batch: only for the first item that ever completes an
    upload into a `reopened` batch (`RequestMediaStored`, per-item, only fires once an upload
    actually lands -- `ham.media.services.complete_upload`). Every later item in the same
    batch finds another item with `uploaded_at` already set and stays silent."""
    media_id = event.payload.get("media_id")
    if not media_id:
        return None
    item = RequestMedia.objects.filter(id=media_id).select_related("batch").first()
    if item is None:
        return None
    batch: RequestMediaBatch = item.batch
    if batch.kind != BATCH_KIND_REOPENED or batch.opened_by_user_id is None:
        return None
    # Idempotency/"first one" check: any *other* item in this batch that already completed an
    # upload means this is not the first, so no second notice goes out for the same batch.
    already_notified = (
        RequestMedia.objects.filter(batch=batch, uploaded_at__isnull=False)
        .exclude(id=item.id)
        .exists()
    )
    if already_notified:
        return None
    from ham.requests.models import AssistanceRequest

    request = (
        AssistanceRequest.objects.filter(id=item.request_id).only("id", "reference_number").first()
    )
    if request is None:
        return None
    return InAppNotice(
        recipient_user_id=batch.opened_by_user_id,
        kind="media_new_photos_arrived",
        subject_type="media_batch",
        subject_id=batch.id,
        title=f"New photos arrived · {request.display_number}",
    )


def register() -> None:
    """Called once from `MediaConfig.ready()`."""
    register_inapp("RequestMediaStored", _build_new_photos_notice)


__all__ = ["register"]
