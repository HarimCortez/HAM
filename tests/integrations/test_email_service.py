from __future__ import annotations

import logging

from django.core import mail

from ham.integrations.email.service import _send_transactional_email_job, send_transactional_email
from ham.platform.crypto import decrypt


def test_send_transactional_email_enqueues_only_an_encrypted_payload(monkeypatch):
    """Security review C2: job args (what Procrastinate stores/may log) must never carry a
    plaintext email address, subject or body — only ciphertext plus the non-sensitive
    category."""
    calls = []
    monkeypatch.setattr(
        "ham.integrations.email.service.jobs.defer",
        lambda name, **kwargs: calls.append((name, kwargs)),
    )
    send_transactional_email(
        to="volunteer@example.org",
        subject="Your sign-in code",
        text_body="Your code is 123456",
        category="sign_in_code",
    )
    assert len(calls) == 1
    name, kwargs = calls[0]
    assert name == "integrations.send_transactional_email"
    assert kwargs["category"] == "sign_in_code"
    assert set(kwargs) == {"payload_encrypted", "category"}
    assert "volunteer@example.org" not in kwargs["payload_encrypted"]
    assert "123456" not in kwargs["payload_encrypted"]
    import json

    decoded = json.loads(decrypt(kwargs["payload_encrypted"]))
    assert decoded["to"] == "volunteer@example.org"
    assert decoded["subject"] == "Your sign-in code"


def test_transactional_email_lands_in_locmem_outbox(mailoutbox):
    import json

    from ham.platform.crypto import encrypt

    payload = encrypt(
        json.dumps(
            {
                "to": "volunteer@example.org",
                "subject": "Your sign-in code",
                "text_body": "Your code is 123456",
                "html_body": None,
            }
        )
    )
    _send_transactional_email_job(payload_encrypted=payload, category="sign_in_code")
    assert len(mailoutbox) == 1
    sent = mailoutbox[0]
    assert sent.to == ["volunteer@example.org"]
    assert sent.subject == "Your sign-in code"
    assert "123456" in sent.body


def test_transactional_email_address_is_never_logged(caplog):
    import json

    from ham.platform.crypto import encrypt

    caplog.set_level(logging.DEBUG)
    mail.outbox = []
    payload = encrypt(
        json.dumps(
            {
                "to": "volunteer@example.org",
                "subject": "Your sign-in code",
                "text_body": "Your code is 123456",
                "html_body": None,
            }
        )
    )
    _send_transactional_email_job(payload_encrypted=payload, category="sign_in_code")
    for record in caplog.records:
        assert "volunteer@example.org" not in record.getMessage()
        assert "volunteer@example.org" not in str(record.__dict__)
