"""S3.4/Q-173: `ham.media.services.reopen_batch`'s guard is `ham.requests.states.
accepts_media_reopen` -- only AWAITING_APPROVAL, RECONSIDERATION_PENDING or APPROVED, and
never once closed. A rejection that can still be reconsidered (open, `closed_at` still null)
must be refused too, which the old plain `is_request_open` guard (``closed_at IS NULL``) could
not tell apart from an allowed status.
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.authz.context import ActorContext
from ham.media import services
from ham.media.models import BATCH_KIND_REOPENED
from ham.requests.models import Requester
from ham.requests.states import RequestStatus

from .factories import create_request

pytestmark = pytest.mark.django_db


def _director_ctx() -> ActorContext:
    return ActorContext(
        user_id=uuid.UUID("00000000-0000-7000-8000-000000000011"),
        real_user_id=None,
        roles=frozenset({roles.HAM_DIRECTOR}),
        is_active=True,
        mfa_satisfied=True,
    )


def _with_email(request, *, email="on-file@example.org"):
    Requester.objects.create(request=request, full_name="", email=email)
    return request


@pytest.mark.parametrize(
    "status",
    [
        RequestStatus.AWAITING_APPROVAL.value,
        RequestStatus.RECONSIDERATION_PENDING.value,
        RequestStatus.APPROVED.value,
    ],
)
def test_reopen_allowed_in_media_reopen_statuses(local_storage, status):
    request = _with_email(create_request(status=status))
    batch = services.reopen_batch(_director_ctx(), request_id=request.id, reason="need a close-up")
    assert batch.kind == BATCH_KIND_REOPENED


@pytest.mark.parametrize(
    "status",
    [
        RequestStatus.NEEDS_PHONE_CHECK.value,
        RequestStatus.SUBMITTED.value,
        # Q-173: an open (reconsiderable) rejection is not closed, but must still be refused
        # -- the requester has to ask for reconsideration first.
        RequestStatus.REJECTED.value,
    ],
)
def test_reopen_refused_outside_media_reopen_statuses(local_storage, status):
    request = _with_email(create_request(status=status))
    with pytest.raises(ValueError):
        services.reopen_batch(_director_ctx(), request_id=request.id, reason="need a close-up")


def test_reopen_refused_once_closed(local_storage):
    from ham.platform.clock import now as clock_now

    request = _with_email(
        create_request(status=RequestStatus.CANCELLED.value, closed_at=clock_now())
    )
    with pytest.raises(ValueError):
        services.reopen_batch(_director_ctx(), request_id=request.id, reason="need a close-up")


def test_reopen_refused_on_a_final_rejection(local_storage):
    from ham.platform.clock import now as clock_now

    request = _with_email(
        create_request(status=RequestStatus.REJECTED.value, closed_at=clock_now())
    )
    with pytest.raises(ValueError):
        services.reopen_batch(_director_ctx(), request_id=request.id, reason="need a close-up")
