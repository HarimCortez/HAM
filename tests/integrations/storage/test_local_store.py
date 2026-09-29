"""LocalObjectStore + the dev-only signed-URL view (S2.4a). Presign expiry, size/content-type
enforcement, head/delete/copy, and no-PII-key checks."""

from __future__ import annotations

import datetime as dt
import time
import uuid

import pytest
from django.test import Client, override_settings

from ham.integrations.storage.local import LocalObjectStore

# Robustness (test-engineer pass, step 3): every test below that builds a presigned URL and
# then strips a base URL back off it to get a request `path` must strip the *same* base the
# view will actually be served under, or it silently mis-splits (or errors) whenever
# `HAM_BASE_URL` differs from the code default -- e.g. a developer's shell exporting
# `HAM_BASE_URL` for local Playwright/manual testing before running `pytest`. Pinning it here,
# module-wide, makes every test in this file independent of the ambient environment rather
# than each test hardcoding the literal string by hand.
pytestmark = pytest.mark.usefixtures("_pin_ham_base_url")


@pytest.fixture
def _pin_ham_base_url(settings):
    settings.HAM_BASE_URL = "http://localhost:8000"


@pytest.fixture
def store(tmp_path, settings):
    settings.HAM_LOCAL_STORAGE_ROOT = str(tmp_path)
    return LocalObjectStore()


def test_put_object_then_head_and_get_object(store):
    key = str(uuid.uuid4())
    store.put_object(key, b"hello world", content_type="image/jpeg")
    meta = store.head(key)
    assert meta is not None
    assert meta.size == 11
    assert meta.content_type == "image/jpeg"
    assert store.get_object(key) == b"hello world"


def test_head_missing_key_returns_none(store):
    assert store.head(str(uuid.uuid4())) is None


def test_get_object_missing_key_raises(store):
    with pytest.raises(FileNotFoundError):
        store.get_object(str(uuid.uuid4()))


def test_delete_is_idempotent(store):
    key = str(uuid.uuid4())
    store.put_object(key, b"x", content_type="image/jpeg")
    store.delete(key)
    assert store.head(key) is None
    store.delete(key)  # no error deleting again


def test_copy_duplicates_object_and_metadata(store):
    src, dest = str(uuid.uuid4()), str(uuid.uuid4())
    store.put_object(src, b"payload", content_type="video/mp4")
    store.copy(src, dest)
    assert store.get_object(dest) == b"payload"
    assert store.head(dest).content_type == "video/mp4"


def test_copy_missing_source_raises(store):
    with pytest.raises(FileNotFoundError):
        store.copy(str(uuid.uuid4()), str(uuid.uuid4()))


def test_unsafe_key_rejected(store):
    with pytest.raises(ValueError):
        store.put_object("../../etc/passwd", b"x", content_type="image/jpeg")


def test_presign_put_url_round_trips_via_dev_view(db, store, settings):
    key = str(uuid.uuid4())
    upload = store.presign_put(
        key, content_type="image/jpeg", content_length=10, expires_in=dt.timedelta(minutes=15)
    )
    assert upload.key == key
    assert upload.expires_at > dt.datetime.now(dt.UTC)

    path = upload.url.split(settings.HAM_BASE_URL, 1)[1]
    client = Client()
    resp = client.put(path, data=b"small file", content_type="image/jpeg")
    assert resp.status_code == 204
    assert store.get_object(key) == b"small file"


def test_presign_put_rejects_oversize_body(db, store):
    key = str(uuid.uuid4())
    upload = store.presign_put(
        key, content_type="image/jpeg", content_length=5, expires_in=dt.timedelta(minutes=15)
    )
    path = upload.url.split("http://localhost:8000", 1)[1]
    resp = Client().put(path, data=b"way too big", content_type="image/jpeg")
    assert resp.status_code == 400
    assert store.head(key) is None


def test_presign_put_rejects_undersize_body(db, store):
    """Security review M2: the PUT is signed for an *exact* length, not just a ceiling -- a
    body shorter than declared is refused too, not silently accepted."""
    key = str(uuid.uuid4())
    upload = store.presign_put(
        key, content_type="image/jpeg", content_length=50, expires_in=dt.timedelta(minutes=15)
    )
    path = upload.url.split("http://localhost:8000", 1)[1]
    resp = Client().put(path, data=b"too small", content_type="image/jpeg")
    assert resp.status_code == 400
    assert store.head(key) is None


def test_presign_put_rejects_wrong_content_type(db, store):
    key = str(uuid.uuid4())
    upload = store.presign_put(
        key, content_type="image/jpeg", content_length=1, expires_in=dt.timedelta(minutes=15)
    )
    path = upload.url.split("http://localhost:8000", 1)[1]
    resp = Client().put(path, data=b"x", content_type="image/png")
    assert resp.status_code == 400


def test_presign_get_serves_stored_object(db, store):
    key = str(uuid.uuid4())
    store.put_object(key, b"view me", content_type="image/jpeg")
    url = store.presign_get(key, expires_in=dt.timedelta(seconds=60))
    path = url.split("http://localhost:8000", 1)[1]
    resp = Client().get(path)
    assert resp.status_code == 200
    assert resp.content == b"view me"
    assert resp["Content-Type"] == "image/jpeg"


def test_presigned_url_expires(db, store):
    key = str(uuid.uuid4())
    store.put_object(key, b"view me", content_type="image/jpeg")
    url = store.presign_get(key, expires_in=dt.timedelta(seconds=0))
    path = url.split("http://localhost:8000", 1)[1]
    time.sleep(0.05)
    resp = Client().get(path)
    assert resp.status_code == 403


def test_tampered_token_is_rejected(db, store):
    key = str(uuid.uuid4())
    store.put_object(key, b"view me", content_type="image/jpeg")
    url = store.presign_get(key, expires_in=dt.timedelta(seconds=60))
    path = url.split("http://localhost:8000", 1)[1]
    tampered = path[:-1] + ("A" if path[-1] != "A" else "B")
    resp = Client().get(tampered)
    assert resp.status_code == 403


@override_settings(HAM_BASE_URL="http://localhost:8000")
def test_storage_key_contains_no_pii(store):
    # Keys are UUIDs, chosen by the caller (ham.media) — this just documents/pins that a
    # LocalObjectStore never derives a key from content it is given.
    key = str(uuid.uuid4())
    store.put_object(key, b"x", content_type="image/jpeg")
    assert store.head(key) is not None
    # nothing in the key itself is anything but the UUID the caller supplied
    uuid.UUID(key)
