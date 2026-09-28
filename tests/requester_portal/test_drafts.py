from __future__ import annotations

import datetime as dt
import uuid

import pytest

from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal import drafts
from ham.requester_portal.models import IntakeDraft
from ham.rules import RULES

pytestmark = pytest.mark.django_db

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    c = FixedClock(T0)
    set_clock(c)
    return c


def test_start_draft_stores_no_plaintext(clock: FixedClock):
    result = drafts.start_draft(ip_address="203.0.113.5", email="doris@example.org")
    assert result.status == "created"
    assert result.draft is not None
    row = IntakeDraft.objects.get(pk=result.draft.id)
    assert "doris" not in row.payload_ciphertext
    assert "@" not in row.payload_ciphertext
    assert row.expires_at == T0 + RULES.intake.INTAKE_DRAFT_LIFETIME


def test_start_draft_rate_limited_per_ip(clock: FixedClock):
    for _ in range(RULES.intake.INTAKE_FORMS_PER_IP_PER_HOUR):
        assert drafts.start_draft(ip_address="203.0.113.5").status == "created"
    assert drafts.start_draft(ip_address="203.0.113.5").status == "rate_limited"
    # A different IP is unaffected.
    assert drafts.start_draft(ip_address="203.0.113.9").status == "created"


def test_save_step_merges_and_survives_errors(clock: FixedClock):
    started = drafts.start_draft(ip_address="203.0.113.5")
    assert started.draft is not None
    draft_id = started.draft.id

    drafts.save_step(draft_id, {"full_name": "Doris Palmer"})
    drafts.save_step(draft_id, {"phone": "3055550177"})

    payload = drafts.load_payload(draft_id)
    assert payload == {"full_name": "Doris Palmer", "phone": "3055550177"}

    # A step "survives errors": saving again after a caller-side validation failure elsewhere
    # doesn't lose what was already saved.
    drafts.save_step(draft_id, {"full_name": "Doris P. Palmer"})
    payload = drafts.load_payload(draft_id)
    assert payload is not None
    assert payload["full_name"] == "Doris P. Palmer"
    assert payload["phone"] == "3055550177"


def test_save_step_unknown_draft_is_a_noop():
    assert drafts.save_step(uuid.UUID("00000000-0000-7000-8000-000000000099"), {"x": 1}) is None


def test_draft_erased_after_24h(clock: FixedClock):
    started = drafts.start_draft(ip_address="203.0.113.5")
    assert started.draft is not None
    draft_id = started.draft.id
    clock.advance(RULES.intake.INTAKE_DRAFT_LIFETIME - dt.timedelta(seconds=1))
    assert drafts.load_payload(draft_id) is not None
    clock.advance(dt.timedelta(seconds=1))
    assert drafts.load_payload(draft_id) is None
    assert drafts.save_step(draft_id, {"x": 1}) is None


def test_mark_consumed_prevents_further_edits(clock: FixedClock):
    started = drafts.start_draft(ip_address="203.0.113.5")
    assert started.draft is not None
    draft_id = started.draft.id
    request_id = uuid.UUID("00000000-0000-7000-8000-0000000000aa")
    drafts.mark_consumed(draft_id, request_id=request_id)
    assert drafts.save_step(draft_id, {"x": 1}) is None
    assert drafts.load_payload(draft_id) is None


def test_purge_job_deletes_expired_drafts(clock: FixedClock):
    from ham.requester_portal.jobs import purge_expired_drafts

    drafts.start_draft(ip_address="203.0.113.5")
    clock.advance(RULES.intake.INTAKE_DRAFT_LIFETIME + dt.timedelta(seconds=1))
    deleted = purge_expired_drafts(0)
    assert deleted == 1
    assert IntakeDraft.objects.count() == 0
