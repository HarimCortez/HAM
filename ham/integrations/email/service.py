"""`send_transactional_email` — the one documented exception to "only via the outbox"
(foundation.md §1, §8 S4): used by S3b for sign-in codes/links, which need to go out right
away and don't describe a domain fact worth an `OutboxEvent` of their own.

    from ham.integrations.email.service import send_transactional_email
    send_transactional_email(to=..., subject=..., text_body=..., category="sign_in_code")

Security review C2: `to`/`subject`/`text_body` (often a sign-in code or link, or an MFA-reset
notice) must never sit in plaintext in `procrastinate_jobs.args` or in a log line ("Starting
job ...(to=..., text_body=...)"). The whole message is Fernet-encrypted (`ham.platform.crypto`,
the same key/rotation as `ham.identity.crypto`) into a single opaque string before it is handed
to `jobs.defer(...)`, so the job's *args* — which Procrastinate stores in the database and may
log — are just ciphertext. The job function decrypts only inside its own process, right before
calling the channel adapter.
"""

from __future__ import annotations

import json

from ham import jobs
from ham.platform.crypto import decrypt, encrypt

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
    payload = json.dumps(
        {"to": to, "subject": subject, "text_body": text_body, "html_body": html_body}
    )
    jobs.defer(
        _JOB_NAME,
        payload_encrypted=encrypt(payload),
        category=category,
    )


@jobs.job(name=_JOB_NAME)
def _send_transactional_email_job(*, payload_encrypted: str, category: str) -> None:
    payload = json.loads(decrypt(payload_encrypted))
    get_default_channel().send(
        to=payload["to"],
        subject=payload["subject"],
        text_body=payload["text_body"],
        html_body=payload["html_body"],
        category=category,
    )
