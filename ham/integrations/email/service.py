"""`send_transactional_email` — the one documented exception to "only via the outbox"
(foundation.md §1, §8 S4): used by S3b for sign-in codes/links, which need to go out right
away and don't describe a domain fact worth an `OutboxEvent` of their own.

    from ham.integrations.email.service import send_transactional_email
    send_transactional_email(to=..., subject=..., text_body=..., category="sign_in_code")

`to` is an email address passed directly by the caller (e.g. from `ham.identity`) — it is
never carried in an outbox payload and never logged here.
"""

from __future__ import annotations

from ham import jobs

from .adapters import get_default_channel

_JOB_NAME = "integrations.send_transactional_email"


def send_transactional_email(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    category: str,
) -> None:
    """Enqueue one email for immediate delivery via a background job (not the outbox)."""
    jobs.defer(
        _JOB_NAME,
        to=to,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        category=category,
    )


@jobs.job(name=_JOB_NAME)
def _send_transactional_email_job(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None,
    category: str,
) -> None:
    get_default_channel().send(
        to=to,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        category=category,
    )
