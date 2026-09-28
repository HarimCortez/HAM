"""The `email` outbox subscriber (entry point (a), foundation.md §8 S4): domain modules that
want an email sent when they `ham.outbox.emit(...)` a domain event register a builder here.

This file does not know about identity/requests/staffing (foundation.md §1 layering); a
builder is given only the `OutboxEvent` (ids and codes, §68) and must resolve the recipient
address and copy itself, through its own module's services under its own least privilege —
never by reading a name/email/phone out of the outbox payload.

No step-1 domain module registers a builder yet: notifications land "with staffing"
(foundation.md §2 module list), and requests/staffing are out of scope for step 1 (foundation
§10). Until a builder is registered for a given `event_type`, this subscriber is a documented
no-op that logs the event type and ids only — exactly like the calendar/fitness/drive stubs.

PRD-GAP Q-078: the PRD does not say *how* an outbox event becomes a specific email (recipient,
subject, body); this per-event-type builder registry is S4's proposed mechanism, not yet
signed off by the product owner.
"""
# PRD-GAP Q-078

from __future__ import annotations

import logging
from collections.abc import Callable

from ham.outbox.models import OutboxEvent

from .adapters import get_default_channel

logger = logging.getLogger(__name__)


class NotificationEmail:
    """Everything `DjangoEmailChannel.send` needs, already resolved by the builder."""

    __slots__ = ("to", "subject", "text_body", "html_body", "category")

    def __init__(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        category: str,
    ) -> None:
        self.to = to
        self.subject = subject
        self.text_body = text_body
        self.html_body = html_body
        self.category = category


Builder = Callable[[OutboxEvent], "NotificationEmail | list[NotificationEmail] | None"]

# S2.0 (intake.md §2 "Email builder registry change (integrations, S2.0): register_notification
# keeps a list of builders per event type"): a list, not a single slot, so one outbox event can
# drive more than one email built by more than one module — e.g. a step-2 `RequestSubmitted`
# needs both a requester-facing "we received your request" email (built by
# `ham.requester_portal.notifications`) and, later, a leadership one, from two different
# modules' own `AppConfig.ready()` registrations, without either module knowing about the
# other's existence.
_builders: dict[str, list[Builder]] = {}


def register_notification(event_type: str, builder: Builder) -> None:
    """A later module calls this once, from its own `AppConfig.ready()`, to have this
    subscriber send an email whenever `event_type` is emitted. The builder may return
    `None` to mean "no email for this particular event" (e.g. a preference was off), one
    `NotificationEmail`, or a list of them (e.g. Q-055: one role-change event notifies every
    active Administrator). Calling this more than once for the same `event_type` (from
    different modules) appends, it does not replace — every registered builder for that event
    type runs."""
    _builders.setdefault(event_type, []).append(builder)


def unregister_notification(event_type: str) -> None:
    """Test-only: undo every `register_notification` call for `event_type`."""
    _builders.pop(event_type, None)


def handle_email_event(event: OutboxEvent) -> None:
    builders = _builders.get(event.event_type)
    if not builders:
        logger.info(
            "outbox.email: no notification builder registered for event type",
            extra={"event_type": event.event_type, "event_id": str(event.id)},
        )
        return
    channel = get_default_channel()
    for builder in builders:
        result = builder(event)
        if result is None:
            continue
        emails = result if isinstance(result, list) else [result]
        for email in emails:
            channel.send(
                to=email.to,
                subject=email.subject,
                text_body=email.text_body,
                html_body=email.html_body,
                category=email.category,
            )
