from __future__ import annotations

import datetime as dt
import uuid

import pytest
from django.core import mail

from ham.jobs import run_due_jobs_now
from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal import verification
from ham.requester_portal.models import RequesterVerificationChallenge
from ham.rules import RULES

pytestmark = [pytest.mark.django_db(transaction=True)]

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)
SECOND = dt.timedelta(seconds=1)
DRAFT_ID = uuid.UUID("00000000-0000-7000-8000-000000000001")


@pytest.fixture
def clock() -> FixedClock:
    c = FixedClock(T0)
    set_clock(c)
    return c


def _request_and_send(email: str = "doris@example.org", draft_id=DRAFT_ID):
    result = verification.request_intake_verification(draft_id=draft_id, email=email)
    assert result.status == "sent"
    run_due_jobs_now()
    return result


def test_code_email_sent(clock: FixedClock):
    mail.outbox.clear()
    _request_and_send()
    assert len(mail.outbox) == 1
    assert "doris" not in mail.outbox[0].subject.lower()  # Q-102 neutral subject


def test_verify_code_success_and_reuse(clock: FixedClock):
    _request_and_send(email="doris@example.org")
    challenge = RequesterVerificationChallenge.objects.get(purpose="intake")
    # We don't have the raw code (only its hash) in this test, so exercise wrong/expired/locked
    # paths and the "no_challenge after consumption" path using the model directly for the
    # correct-code case via a monkeypatched deterministic code.
    from ham.platform import otp

    code = "123456"
    challenge.code_hash = otp.hash_value(code)
    challenge.save(update_fields=["code_hash"])

    result = verification.verify_code(purpose="intake", email="doris@example.org", code=code)
    assert result.ok
    # Reusing the same (now consumed) challenge fails.
    result2 = verification.verify_code(purpose="intake", email="doris@example.org", code=code)
    assert not result2.ok
    assert result2.reason == "no_challenge"


def test_verify_code_wrong_then_expiry_and_lockout(clock: FixedClock):
    _request_and_send(email="mrs.hall@example.org")
    max_attempts = RULES.intake.REQUESTER_CODE_MAX_ATTEMPTS
    for i in range(max_attempts):
        result = verification.verify_code(
            purpose="intake", email="mrs.hall@example.org", code="000000"
        )
        assert not result.ok
        if i < max_attempts - 1:
            assert result.reason == "wrong"
        else:
            assert result.reason == "locked"

    # Locked: even the daily-cap path (a fresh challenge wouldn't reset this) refuses.
    result = verification.verify_code(purpose="intake", email="mrs.hall@example.org", code="000000")
    assert not result.ok
    assert result.reason == "locked"


def test_code_expires(clock: FixedClock):
    _request_and_send(email="expired@example.org")
    clock.advance(RULES.intake.REQUESTER_CODE_LIFETIME + SECOND)
    result = verification.verify_code(purpose="intake", email="expired@example.org", code="000000")
    assert not result.ok
    assert result.reason == "expired"


def test_resend_cooldown(clock: FixedClock):
    _request_and_send(email="doris@example.org")
    result = verification.request_intake_verification(draft_id=DRAFT_ID, email="doris@example.org")
    assert result.status == "cooldown"
    clock.advance(RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN)
    result = verification.request_intake_verification(draft_id=DRAFT_ID, email="doris@example.org")
    assert result.status == "sent"


def test_hourly_email_rate_limit(clock: FixedClock):
    cooldown = RULES.intake.REQUESTER_CODE_RESEND_COOLDOWN
    limit = RULES.intake.REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR
    for _ in range(limit):
        result = verification.request_intake_verification(
            draft_id=DRAFT_ID, email="doris@example.org"
        )
        assert result.status == "sent"
        clock.advance(cooldown)
    result = verification.request_intake_verification(draft_id=DRAFT_ID, email="doris@example.org")
    assert result.status == "rate_limited"


def test_link_flow(clock: FixedClock):
    from ham.platform import otp

    _request_and_send(email="doris@example.org")
    challenge = RequesterVerificationChallenge.objects.get(purpose="intake")
    token = "a-known-raw-token"
    challenge.link_token_hash = otp.hash_value(token)
    challenge.save(update_fields=["link_token_hash"])

    assert verification.link_is_valid(token=token)
    result = verification.consume_link(token=token)
    assert result.ok
    # GET-safe check never consumes; the link is now actually consumed, so it's no longer valid.
    assert not verification.link_is_valid(token=token)
    # Consuming twice fails.
    result2 = verification.consume_link(token=token)
    assert not result2.ok
