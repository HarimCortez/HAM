from __future__ import annotations

import datetime as dt
import uuid

import pytest
from django.db import IntegrityError, transaction

from ham.platform.clock import FixedClock, set_clock
from ham.requester_portal import services
from ham.requester_portal.models import RequesterAccessLink
from ham.rules import RULES

pytestmark = pytest.mark.django_db

T0 = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    c = FixedClock(T0)
    set_clock(c)
    return c


@pytest.fixture(autouse=True)
def _facts_lookup(real_portal_lookups):
    """A fake `ham.requests` facts provider (this slice's app doesn't own that model; see
    `ham.requester_portal.services.register_request_facts_lookup`'s docstring).

    Depends on `real_portal_lookups` (`tests/conftest.py`) purely for fixture-teardown
    *ordering*, not its registration: pytest tears fixtures down in reverse setup order, so
    `real_portal_lookups`'s own teardown (re-registers the real callables) runs *after* this
    fixture's `None` reset below, leaving the globals in a valid state for whatever test runs
    next regardless of file/test order -- this test module still gets its fake for the
    duration of its own tests either way, since this fixture's body runs (and overwrites the
    real one) after `real_portal_lookups`'s setup completes."""
    facts_by_request: dict[uuid.UUID, services.RequestLinkFacts] = {}

    def lookup(request_id: uuid.UUID) -> services.RequestLinkFacts:
        try:
            return facts_by_request[request_id]
        except KeyError:
            raise ValueError(f"unknown request {request_id}") from None

    services.register_request_facts_lookup(lookup)
    yield facts_by_request
    services._request_facts_lookup = None  # noqa: SLF001 - test isolation


def _open(request_id: uuid.UUID, facts_by_request: dict) -> None:
    facts_by_request[request_id] = services.RequestLinkFacts(
        status="AWAITING_APPROVAL", closed_at=None
    )


def _closed(request_id: uuid.UUID, facts_by_request: dict, *, closed_at: dt.datetime) -> None:
    facts_by_request[request_id] = services.RequestLinkFacts(
        status="CANCELLED", closed_at=closed_at
    )


def test_issue_link_and_resolve_round_trip(clock: FixedClock, _facts_lookup):
    request_id = uuid.uuid4()
    _open(request_id, _facts_lookup)

    issued = services.issue_link(request_id=request_id, kind="initial")
    assert issued.link.expires_at is None  # open request, no fixed end yet

    ctx = services.resolve_token(issued.token)
    assert ctx is not None
    assert ctx.request_id == request_id
    assert ctx.link_id == issued.link.id


def test_unknown_or_tampered_token_resolves_to_none(clock: FixedClock, _facts_lookup):
    assert services.resolve_token("this-token-was-never-issued") is None


def test_issuing_a_new_link_revokes_the_old_one_in_the_same_transaction(
    clock: FixedClock, _facts_lookup
):
    request_id = uuid.uuid4()
    _open(request_id, _facts_lookup)
    first = services.issue_link(request_id=request_id, kind="initial")
    second = services.issue_link(request_id=request_id, kind="regenerated")

    first.link.refresh_from_db()
    assert first.link.revoked_at is not None
    assert first.link.revoke_reason == RequesterAccessLink.REVOKE_SUPERSEDED
    assert services.resolve_token(first.token) is None
    assert services.resolve_token(second.token) is not None


def test_partial_unique_constraint_one_live_link_per_request(clock: FixedClock, _facts_lookup):
    request_id = uuid.uuid4()
    _open(request_id, _facts_lookup)
    services.issue_link(request_id=request_id, kind="initial")
    with pytest.raises(IntegrityError), transaction.atomic():
        RequesterAccessLink.objects.create(
            request_id=request_id,
            token_hash="deadbeef" * 8,
            token_ciphertext="x",
            kind=RequesterAccessLink.KIND_INITIAL,
            issued_at=clock.now(),
        )


def test_link_expired_after_close_plus_access_window(clock: FixedClock, _facts_lookup):
    request_id = uuid.uuid4()
    closed_at = T0
    _closed(request_id, _facts_lookup, closed_at=closed_at)
    issued = services.issue_link(request_id=request_id, kind="initial")

    window = RULES.requester_access.REQUESTER_ACCESS_AFTER_CLOSE
    clock.set(closed_at + window - dt.timedelta(seconds=1))
    assert services.resolve_token(issued.token) is not None
    clock.set(closed_at + window)
    assert services.resolve_token(issued.token) is None


def test_regenerated_link_after_access_ended_gets_14_days(clock: FixedClock, _facts_lookup):
    request_id = uuid.uuid4()
    closed_at = T0
    _closed(request_id, _facts_lookup, closed_at=closed_at)
    window = RULES.requester_access.REQUESTER_ACCESS_AFTER_CLOSE
    clock.set(closed_at + window)  # normal access has just ended

    issued = services.issue_link(request_id=request_id, kind="regenerated")
    assert (
        issued.link.expires_at
        == clock.now() + RULES.requester_access.REGENERATED_REQUESTER_LINK_LIFETIME
    )


def test_hmac_key_rotation_still_resolves_old_links(clock: FixedClock, _facts_lookup, settings):
    request_id = uuid.uuid4()
    _open(request_id, _facts_lookup)
    settings.HAM_TOKEN_HMAC_KEYS = "old-key-1"
    issued = services.issue_link(request_id=request_id, kind="initial")

    # Rotate: a new current key first, old key kept for lookups.
    settings.HAM_TOKEN_HMAC_KEYS = "new-key-2,old-key-1"
    ctx = services.resolve_token(issued.token)
    assert ctx is not None
    assert ctx.request_id == request_id
