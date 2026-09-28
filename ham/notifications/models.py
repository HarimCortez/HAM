"""`notifications_notification` (intake.md §3 "Notification").

Only the **Updates** section of the Inbox and the urgent banner are ever backed by a stored
row. "Needs response" is never stored here — it is computed live by the attention-provider
registry (`ham.notifications.attention`), so resolving an item anywhere (e.g. a request leaving
Awaiting Approval) clears it everywhere without a job to keep a stored copy in sync
(navigation.md §4, intake.md §3).

`title` must never carry a P/C field (requester name, address, contact, circumstances, §68):
the owning module resolves those, if the viewer is authorized, at render time through its own
services — this row only carries enough (ids + a PII-free title) to list and link the update.
`ham.notifications.validation.check_title` enforces this the same way
`ham.outbox.validation.validate_payload` enforces it for outbox payloads.
"""

from __future__ import annotations

from django.db import models

from ham.platform.clock import now
from ham.platform.ids import UUID7Field


class Notification(models.Model):
    id = UUID7Field()
    recipient_user_id = models.UUIDField()
    # Nullable: a notification could in principle be created outside the outbox pipeline (none
    # do today), and the source event is never required to render or resolve one.
    outbox_event_id = models.UUIDField(null=True, blank=True)
    # A short code identifying which builder created this row (e.g.
    # "request_awaiting_approval"), used for grouping/testing, never shown verbatim to a user.
    kind = models.CharField(max_length=100)
    subject_type = models.CharField(max_length=50)
    subject_id = models.UUIDField()
    title = models.CharField(max_length=200)
    urgent = models.BooleanField(default=False)
    # §10/§35: an urgent notification the recipient must expressly acknowledge (the app-wide
    # banner). Never true for an ordinary Update.
    requires_ack = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=now)
    read_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_notification"
        indexes = [
            models.Index(
                fields=["recipient_user_id", "created_at"], name="notif_recipient_created_idx"
            ),
            models.Index(
                fields=["recipient_user_id", "read_at"], name="notif_recipient_unread_idx"
            ),
            # The urgent-banner query (intake.md §3, §10): this recipient's unacknowledged,
            # ack-required notifications.
            models.Index(
                fields=["recipient_user_id", "requires_ack", "acknowledged_at"],
                name="notif_recipient_ack_idx",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial; never logs PII
        return f"Notification({self.kind}) -> {self.recipient_user_id}"
