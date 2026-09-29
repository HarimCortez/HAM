"""Q-150 (build in step 3): "New photos arrived · HAM #" in-app notice to the leader who
reopened uploads, once per reopened batch (approvals-contracts.md §6/§7).
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.authz.context import ActorContext, RequesterContext
from ham.jobs import run_due_jobs_now
from ham.media import services
from ham.media.services import UploadIntent
from ham.notifications.models import Notification
from ham.platform.storage import get_object_store
from ham.requests.models import Requester
from ham.requests.states import RequestStatus

from .factories import create_request

pytestmark = pytest.mark.django_db(transaction=True)

_DIRECTOR_ID = uuid.UUID("00000000-0000-7000-8000-000000000021")


def _director_ctx() -> ActorContext:
    return ActorContext(
        user_id=_DIRECTOR_ID,
        real_user_id=None,
        roles=frozenset({roles.HAM_DIRECTOR}),
        is_active=True,
        mfa_satisfied=True,
    )


def _reopened_request(local_storage):
    request = create_request(status=RequestStatus.APPROVED.value)
    Requester.objects.create(request=request, full_name="", email="on-file@example.org")
    services.reopen_batch(_director_ctx(), request_id=request.id, reason="need a close-up")
    return request


def _upload_one(request):
    from ham.media.models import RequestMedia

    ctx = RequesterContext(request_id=request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    store = get_object_store()
    store.put_object(
        RequestMedia.objects.get(id=reserved.item_id).quarantine_key,
        b"x" * 1000,
        content_type="image/jpeg",
    )
    services.complete_upload(ctx, item_id=reserved.item_id)


def test_first_upload_into_a_reopened_batch_notifies_the_reopener_once(local_storage):
    request = _reopened_request(local_storage)

    _upload_one(request)
    run_due_jobs_now()

    notices = Notification.objects.filter(
        recipient_user_id=_DIRECTOR_ID, kind="media_new_photos_arrived"
    )
    assert notices.count() == 1
    assert notices.first().title == f"New photos arrived · {request.display_number}"


def test_a_second_upload_into_the_same_batch_does_not_notify_again(local_storage):
    request = _reopened_request(local_storage)

    _upload_one(request)
    run_due_jobs_now()
    _upload_one(request)
    run_due_jobs_now()

    notices = Notification.objects.filter(
        recipient_user_id=_DIRECTOR_ID, kind="media_new_photos_arrived"
    )
    assert notices.count() == 1


def test_the_initial_batch_never_notifies_anyone(open_request):
    """The initial batch has no `opened_by_user_id` (the requester's own submission, no staff
    reopener) -- `RequestMediaStored` for an ordinary upload must never build a notice."""
    ctx = RequesterContext(request_id=open_request.id)
    reserved = services.reserve_uploads(ctx, intents=[UploadIntent("photo", "image/jpeg", 1000)])[0]
    from ham.media.models import RequestMedia

    store = get_object_store()
    store.put_object(
        RequestMedia.objects.get(id=reserved.item_id).quarantine_key,
        b"x" * 1000,
        content_type="image/jpeg",
    )
    services.complete_upload(ctx, item_id=reserved.item_id)
    run_due_jobs_now()

    assert not Notification.objects.filter(kind="media_new_photos_arrived").exists()
