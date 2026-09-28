"""The `inapp` outbox subscriber (intake.md §2 "Convention change": `ham.notifications`
registers its own `inapp` outbox subscriber in `NotificationsConfig.ready()` — this is internal
to this module, not a third party like email/calendar/fitness/drive, so it lives here rather
than in `ham.integrations`).

Mirrors `ham.integrations.email.notifications`'s `register_notification` pattern exactly: a
domain module that wants an in-app `Notification` row created when it `ham.outbox.emit(...)`s a
domain event registers a builder here, from its own `AppConfig.ready()`. A builder is handed
only the `OutboxEvent` (ids/codes, §68) and must resolve its own PII-free title text through its
own module's services, under its own least privilege — `ham.notifications` sits *below* every
domain module in the layering (intake.md §2), so it could not read requests/media/identity
details itself even if it wanted to.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from ham.outbox.models import OutboxEvent
from ham.platform.ids import uuid7

from .models import Notification
from .validation import check_title

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InAppNotice:
    """Everything `handle_inapp_event` needs to create one `Notification` row."""

    recipient_user_id: UUID
    kind: str
    subject_type: str
    subject_id: UUID
    title: str
    urgent: bool = False
    requires_ack: bool = False


Builder = Callable[[OutboxEvent], "list[InAppNotice] | InAppNotice | None"]

# S2.6 registers the real per-event builders (requests/media); no builder is registered by this
# slice itself (S2.5 owns only the mechanism).
_builders: dict[str, list[Builder]] = {}


def register_inapp(event_type: str, builder: Builder) -> None:
    """A later module calls this once, from its own `AppConfig.ready()`, to have this
    subscriber create one or more `Notification` rows whenever `event_type` is emitted. The
    builder may return `None` (no notice for this particular event), one `InAppNotice`, or a
    list of them (e.g. one urgent request notifies every pastor). Calling this more than once
    for the same `event_type` appends, it does not replace."""
    _builders.setdefault(event_type, []).append(builder)


def unregister_inapp(event_type: str) -> None:
    """Test-only: undo every `register_inapp` call for `event_type`."""
    _builders.pop(event_type, None)


def handle_inapp_event(event: OutboxEvent) -> None:
    builders = _builders.get(event.event_type)
    if not builders:
        logger.info(
            "outbox.inapp: no notification builder registered for event type",
            extra={"event_type": event.event_type, "event_id": str(event.id)},
        )
        return
    for builder in builders:
        result = builder(event)
        if result is None:
            continue
        notices = result if isinstance(result, list) else [result]
        for notice in notices:
            check_title(notice.title)
            Notification.objects.create(
                id=uuid7(),
                recipient_user_id=notice.recipient_user_id,
                outbox_event_id=event.id,
                kind=notice.kind,
                subject_type=notice.subject_type,
                subject_id=notice.subject_id,
                title=notice.title,
                urgent=notice.urgent,
                requires_ack=notice.requires_ack,
            )
