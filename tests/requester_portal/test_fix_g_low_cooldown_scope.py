"""FIX-G Low: the intake code cooldown and hourly send cap are keyed by (email, draft) for
the intake purpose, not by email alone -- otherwise a third party could type a victim's real
email into a draft *they* control and burn the victim's own cooldown/hourly budget, blocking
"resend code" for the victim's real draft for up to an hour.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from ham.jobs import run_due_jobs_now
from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal import verification

pytestmark = pytest.mark.django_db(transaction=True)

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)
EMAIL = "victim@example.org"


@pytest.fixture
def clock() -> FixedClock:
    c = FixedClock(T0)
    set_clock(c)
    return c


def test_attackers_draft_cooldown_does_not_block_the_victims_own_draft(clock: FixedClock):
    attacker_draft = uuid.uuid4()
    victim_draft = uuid.uuid4()

    # The attacker types the victim's real email into a draft they control and requests a
    # code (this is legal on its own -- anyone can type any email into their own draft).
    attacker_result = verification.request_intake_verification(draft_id=attacker_draft, email=EMAIL)
    assert attacker_result.status == "sent"

    # The victim's OWN draft, same email, immediately after -- before the fix, this shared
    # the same email-keyed cooldown and would have come back "cooldown".
    victim_result = verification.request_intake_verification(draft_id=victim_draft, email=EMAIL)
    assert victim_result.status == "sent"
    # Drains the deferred email-send jobs so they don't leak into a later test's own
    # `run_due_jobs_now()` call.
    run_due_jobs_now()


def test_attackers_draft_cannot_exhaust_the_victims_hourly_budget(clock: FixedClock):
    victim_draft = uuid.uuid4()

    # The attacker sends several codes to the victim's email from many different drafts they
    # control, spaced past the per-draft cooldown, well past what would trip a shared
    # per-address hourly cap on its own.
    for _ in range(6):
        clock.advance(dt.timedelta(seconds=31))
        verification.request_intake_verification(draft_id=uuid.uuid4(), email=EMAIL)

    # The victim's own draft, same address, still gets a code -- its hourly budget was never
    # shared with the attacker's unrelated drafts.
    clock.advance(dt.timedelta(seconds=31))
    victim_result = verification.request_intake_verification(draft_id=victim_draft, email=EMAIL)
    assert victim_result.status == "sent"
    run_due_jobs_now()
