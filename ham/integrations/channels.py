"""A `NotificationChannel` is a way to reach a person outside HAM (PRD §35).

Email is the only implementation in V1 (`ham.integrations.email.adapters.DjangoEmailChannel`).
SMS is deferred (PRD §75) but callers — `send_transactional_email` and the `email` outbox
subscriber — only ever depend on this Protocol, so adding an SMS channel later never requires
changing a caller (CLAUDE.md "Build a channel interface so SMS can be added later")."""

from __future__ import annotations

from typing import Protocol


class NotificationChannel(Protocol):
    def send(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None,
        category: str,
    ) -> None: ...
