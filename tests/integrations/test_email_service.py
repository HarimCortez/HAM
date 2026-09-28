from __future__ import annotations

import logging

from django.core import mail

from ham.integrations.email.service import _send_transactional_email_job, send_transactional_email


def test_send_transactional_email_enqueues_a_job(monkeypatch):
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
    assert kwargs["to"] == "volunteer@example.org"
    assert kwargs["category"] == "sign_in_code"


def test_transactional_email_lands_in_locmem_outbox(mailoutbox):
    _send_transactional_email_job(
        to="volunteer@example.org",
        subject="Your sign-in code",
        text_body="Your code is 123456",
        html_body=None,
        category="sign_in_code",
    )
    assert len(mailoutbox) == 1
    sent = mailoutbox[0]
    assert sent.to == ["volunteer@example.org"]
    assert sent.subject == "Your sign-in code"
    assert "123456" in sent.body


def test_transactional_email_address_is_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    mail.outbox = []
    _send_transactional_email_job(
        to="volunteer@example.org",
        subject="Your sign-in code",
        text_body="Your code is 123456",
        html_body=None,
        category="sign_in_code",
    )
    for record in caplog.records:
        assert "volunteer@example.org" not in record.getMessage()
        assert "volunteer@example.org" not in str(record.__dict__)
