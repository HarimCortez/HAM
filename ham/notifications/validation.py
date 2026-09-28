"""PII guard for `Notification.title` (§68), mirroring `ham.outbox.validation.validate_payload`
for the same reason: a builder is handed only ids/codes off the `OutboxEvent` and must not
smuggle a requester name/email/phone/address into the one free-text field a `Notification` row
carries. Deliberately heuristic, not exhaustive — a false positive means the builder should
resolve that detail at render time instead (`ham.notifications.models` module docstring).
"""

from __future__ import annotations

from ham.platform.logging import EMAIL_RE, PHONE_RE


class NotificationTitlePIIError(ValueError):
    """Raised when a builder-supplied notification title looks like it carries PII."""


def check_title(title: str) -> None:
    if EMAIL_RE.search(title):
        raise NotificationTitlePIIError(
            "notification title looks like it contains an email address (§68); resolve "
            "requester/volunteer contact details at render time instead"
        )
    if PHONE_RE.search(title):
        raise NotificationTitlePIIError(
            "notification title looks like it contains a phone number (§68); resolve "
            "requester/volunteer contact details at render time instead"
        )
