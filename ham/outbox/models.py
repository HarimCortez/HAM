"""`outbox_event` and `outbox_delivery` (foundation.md §3).

`OutboxEvent.payload` carries **IDs and codes only, never PII** (§68) — subscribers that need
more detail fetch it themselves through their own module's services, under their own
least-privilege authorization (foundation.md §3 "subscribers fetch details through services
under their own least privilege"). `ham.outbox.validation.validate_payload` enforces this at
`emit()` time; do not weaken that check to make a call site more convenient.
"""

from __future__ import annotations

from django.db import models

from ham.platform.clock import now
from ham.platform.ids import UUID7Field, uuid7


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    DEAD = "dead", "Dead-lettered"


class OutboxEvent(models.Model):
    """One domain fact, written once and never changed (foundation.md §3 §36.4 names, e.g.
    `VolunteerInvited`, `ProjectCompleted`).

    `seq` (not `id`) is the database primary key: Django/Postgres only auto-increment a real
    primary key, and `seq`'s only job is a strictly-ordered, gap-tolerant cursor for pagination
    (foundation.md §3). `id` (UUIDv7) is what everything else — deliveries, `aggregate_id`
    cross-references, external tokens — points to, exactly like every other HAM table.

    `id` is a plain `models.UUIDField`, not `UUID7Field`: that helper defaults
    `primary_key=True` inside its own `__init__` (via `kwargs.setdefault`), which Django's
    generic `Field.deconstruct()`/`clone()` round-trip silently re-adds even when constructed
    with `primary_key=False` (deconstruct omits `primary_key` because it equals the *base*
    Field's default of `False`, then `UUID7Field.__init__` sets it back to `True` on
    reconstruction) — worth fixing in `ham.platform.ids` later, but avoided here rather than
    changing a platform module another slice owns mid-flight.
    """

    seq = models.BigAutoField(primary_key=True)
    id = models.UUIDField(default=uuid7, editable=False, unique=True)
    event_type = models.CharField(max_length=200)
    schema_version = models.PositiveSmallIntegerField(default=1)
    occurred_at = models.DateTimeField(default=now)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.UUIDField()
    payload = models.JSONField(default=dict)
    correlation_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "outbox_event"
        indexes = [
            models.Index(fields=["event_type", "occurred_at"], name="outbox_event_type_time_idx"),
            models.Index(fields=["aggregate_type", "aggregate_id"], name="outbox_event_agg_idx"),
        ]
        ordering = ["seq"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.event_type} ({self.aggregate_type}:{self.aggregate_id})"


class OutboxDelivery(models.Model):
    """One subscriber's delivery record for one event. Adapter failures touch only this
    table (§70.3); `attempts`/`next_attempt_at`/`last_error` drive the dispatcher job's
    retry/backoff/dead-letter (`ham.outbox.dispatch`)."""

    id = UUID7Field()
    event = models.ForeignKey(
        OutboxEvent,
        on_delete=models.PROTECT,
        related_name="deliveries",
        to_field="id",
    )
    subscriber = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    # Scrubbed with ham.platform.logging.scrub before it is ever saved (never raw exception
    # text, which could echo back a caller-supplied string containing PII).
    last_error = models.TextField(blank=True, default="")
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "outbox_delivery"
        constraints = [
            models.UniqueConstraint(
                fields=["event", "subscriber"], name="uniq_outbox_delivery_event_subscriber"
            ),
        ]
        indexes = [
            models.Index(fields=["subscriber", "status"], name="outbox_delivery_sub_status_idx"),
            models.Index(fields=["status", "next_attempt_at"], name="outbox_delivery_due_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.subscriber}:{self.status} for {self.event_id}"
