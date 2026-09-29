"""Fix round FIX-B, security review H4: every requester email must link to the real
secure-page route (`web:request_help_secure_page`, `/request-help/r/<token>`), not the
hard-coded `/r/<token>` guess that 404'd. New file -- `tests/requester_portal/
test_notifications.py` already covers the builders' copy/content in isolation; this checks
the URL each one emits actually resolves, end to end through a real `Client` request.
"""

from __future__ import annotations

import re
import uuid

import pytest
from django.test import Client

from ham.media.services import reopen_batch
from ham.outbox.models import OutboxEvent
from ham.requester_portal import services
from ham.requester_portal.models import RequesterAccessLink
from ham.requester_portal.notifications import (
    _build_more_photos_email,
    _build_new_link_email,
    _build_request_received_email,
)
from ham.requests.services import submit_request
from tests.requests.conftest import actor_ctx, make_payload

pytestmark = pytest.mark.django_db

_URL_RE = re.compile(r"https?://\S+")


@pytest.fixture
def requester_ctx():
    from ham.authz.context import RequesterContext

    return RequesterContext(request_id=None)


@pytest.fixture
def director_ctx():
    return actor_ctx(roles=frozenset({"HAM_DIRECTOR"}))


@pytest.fixture(autouse=True)
def _real_portal_lookups(real_portal_lookups):
    """Order-dependence fix (test-engineer pass, step 3): used to re-register its own copy of
    the real lookups and reset the globals to `None` on teardown rather than restoring them --
    confirmed (running the suite in reverse file order) to leak a `RuntimeError` into later,
    unrelated files. Depending on the shared `tests/conftest.py::real_portal_lookups` fixture
    keeps this file's own behavior identical while its teardown restores the real callables
    instead of `None`."""


def _submit(ctx, **overrides):
    payload = make_payload(
        full_name="Emailed Link Test",
        phone="+13055559911",
        email="emailed.link.test@example.org",
        line1="1 Test Way",
        **overrides,
    )
    return submit_request(ctx, draft_id=uuid.uuid4(), verification_id=uuid.uuid4(), payload=payload)


def _event(event_type: str, *, aggregate_type: str, aggregate_id, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )


def _extract_url(text_body: str) -> str:
    urls = _URL_RE.findall(text_body)
    assert urls, f"no URL found in email body: {text_body!r}"
    return urls[0].rstrip(".")


def _assert_resolves(url: str) -> None:
    path = url.split("://", 1)[1].split("/", 1)[1]
    resp = Client().get(f"/{path}")
    assert resp.status_code == 200, f"{url} did not resolve (got {resp.status_code})"


def test_request_received_email_link_resolves(requester_ctx):
    request = _submit(requester_ctx)
    services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)
    event = _event(
        "RequestSubmitted",
        aggregate_type="request",
        aggregate_id=request.id,
        payload={"request_id": str(request.id), "source": "public_form", "urgent": False},
    )
    email = _build_request_received_email(event)
    assert email is not None
    url = _extract_url(email.text_body)
    assert "/request-help/r/" in url
    _assert_resolves(url)


def test_new_link_email_link_resolves(requester_ctx):
    request = _submit(requester_ctx)
    services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)
    issued = services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_REGENERATED)
    event = _event(
        "RequesterAccessLinkIssued",
        aggregate_type="request",
        aggregate_id=request.id,
        payload={
            "request_id": str(request.id),
            "link_id": str(issued.link.id),
            "kind": "regenerated",
        },
    )
    email = _build_new_link_email(event)
    assert email is not None
    url = _extract_url(email.text_body)
    assert "/request-help/r/" in url
    _assert_resolves(url)


def test_more_photos_email_link_resolves(requester_ctx, director_ctx):
    request = _submit(requester_ctx)
    services.issue_link(request_id=request.id, kind=RequesterAccessLink.KIND_INITIAL)
    # S3.4/Q-173: `reopen_batch` only accepts AWAITING_APPROVAL, RECONSIDERATION_PENDING or
    # APPROVED -- `submit_request` leaves a fresh request at SUBMITTED.
    request.status = "AWAITING_APPROVAL"
    request.save(update_fields=["status"])
    batch = reopen_batch(director_ctx, request_id=request.id, reason="one more of the roof")
    event = _event(
        "RequestMediaBatchOpened",
        aggregate_type="media_batch",
        aggregate_id=batch.id,
        payload={"request_id": str(request.id), "batch_id": str(batch.id)},
    )
    email = _build_more_photos_email(event)
    assert email is not None
    url = _extract_url(email.text_body)
    assert "/request-help/r/" in url
    _assert_resolves(url)
