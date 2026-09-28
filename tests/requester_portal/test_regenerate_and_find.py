from __future__ import annotations

import datetime as dt
import uuid

import pytest
from django.core import mail

from ham.audit.models import AuditEvent
from ham.authz.context import RequesterContext
from ham.jobs import run_due_jobs_now
from ham.outbox.models import OutboxEvent
from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal import services
from ham.requester_portal.models import RequesterAccessLink

pytestmark = pytest.mark.django_db(transaction=True)

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    c = FixedClock(T0)
    set_clock(c)
    return c


@pytest.fixture(autouse=True)
def _lookups():
    facts: dict[uuid.UUID, services.RequestLinkFacts] = {}
    contact: dict[uuid.UUID, str | None] = {}
    by_email: dict[str, list[uuid.UUID]] = {}

    services.register_request_facts_lookup(
        lambda rid: (
            facts.get(rid) or services.RequestLinkFacts(status="AWAITING_APPROVAL", closed_at=None)
        )
    )
    services.register_request_contact_lookup(lambda rid: contact.get(rid))
    services.register_email_to_request_ids_lookup(lambda email: by_email.get(email, []))

    yield {"facts": facts, "contact": contact, "by_email": by_email}

    services._request_facts_lookup = None  # noqa: SLF001
    services._request_contact_lookup = None  # noqa: SLF001
    services._email_to_request_ids_lookup = None  # noqa: SLF001


def test_regenerate_link_matches_email_on_file(clock: FixedClock, _lookups):
    request_id = uuid.uuid4()
    _lookups["contact"][request_id] = "doris@example.org"
    old = services.issue_link(request_id=request_id, kind="initial")

    mail.outbox.clear()
    result = services.regenerate_link(token=old.token, email="doris@example.org")
    assert result.status == "sent"
    run_due_jobs_now()
    assert len(mail.outbox) == 1


def test_regenerate_link_wrong_email_gives_identical_response_and_sends_nothing(
    clock: FixedClock, _lookups
):
    request_id = uuid.uuid4()
    _lookups["contact"][request_id] = "doris@example.org"
    old = services.issue_link(request_id=request_id, kind="initial")

    mail.outbox.clear()
    result = services.regenerate_link(token=old.token, email="not-doris@example.org")
    assert result.status == "sent"  # identical outward result: no enumeration
    run_due_jobs_now()
    assert len(mail.outbox) == 0


def test_regenerate_link_unknown_token_gives_identical_response(clock: FixedClock, _lookups):
    result = services.regenerate_link(token="never-issued", email="doris@example.org")
    assert result.status == "sent"


def test_find_my_request_sends_one_email_per_matching_request_and_none_for_unknown(
    clock: FixedClock, _lookups
):
    r1, r2 = uuid.uuid4(), uuid.uuid4()
    _lookups["by_email"]["doris@example.org"] = [r1, r2]

    mail.outbox.clear()
    known = services.find_my_request(email="doris@example.org")
    run_due_jobs_now()
    assert known.status == "sent"
    assert len(mail.outbox) == 2  # one per matching request (Q-117)

    mail.outbox.clear()
    unknown = services.find_my_request(email="nobody@example.org")
    run_due_jobs_now()
    assert unknown.status == "sent"  # identical response
    assert len(mail.outbox) == 0  # but no email at all (Q-121)


def test_regenerate_link_for_own_request_command_audits_and_emits_outbox(
    clock: FixedClock, _lookups
):
    request_id = uuid.uuid4()
    ctx = RequesterContext(request_id=request_id, link_id=uuid.uuid4())

    result = services.regenerate_link_for_own_request(ctx, verification_id=uuid.uuid4())
    assert isinstance(result.link, RequesterAccessLink)

    event = AuditEvent.objects.get(action="requester_link.regenerated")
    assert event.actor_type == "requester"
    assert event.project_id == request_id

    assert OutboxEvent.objects.filter(event_type="RequesterAccessLinkIssued").exists()
