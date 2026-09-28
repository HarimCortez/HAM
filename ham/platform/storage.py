"""``ObjectStore`` protocol + loader (intake.md §2 "Object storage is the second documented
exception to 'integrations only through the outbox'"; §8 S2.4a).

Uploads are synchronous infrastructure, like the database. Domain code (``ham.media``, later)
calls ``get_object_store()`` — which loads ``settings.HAM_OBJECT_STORE_BACKEND`` via
``django.utils.module_loading.import_string`` — and never imports ``ham.integrations.storage``
(the concrete R2/local-filesystem adapters, S2.4a) directly. This keeps the same "domain code
never imports ham.integrations" layering rule intake.md §2 states for the outbox, applied to
this one additional, explicitly-documented exception.

S2.0 ships only the protocol and the loader (a seam); no concrete backend exists yet. Calling
``get_object_store()`` before ``HAM_OBJECT_STORE_BACKEND`` is configured raises ``RuntimeError``
with a message naming the setting, not an opaque import error.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    """Everything a browser needs to PUT one object directly to the store (intake.md §7
    ``POST /r/<token>/media/intents``: "returns presigned PUT URLs signed for exact length and
    type")."""

    url: str
    key: str
    expires_at: dt.datetime


@dataclass(frozen=True, slots=True)
class ObjectMeta:
    """What ``head()`` reports about an existing object (used to re-check size on upload
    completion, intake.md §9 "Size is re-checked on completion")."""

    key: str
    size: int
    content_type: str


class ObjectStore(Protocol):
    """S2.4a implements this against R2 (S3-compatible) and local filesystem backends.

    Every method is a plain synchronous call — no outbox event, no retry queue. A storage
    outage must surface as an ordinary exception the caller handles (CLAUDE.md §70.3 "friendly
    error", intake.md §11 test hook "a storage outage leaves the request intact")."""

    def presign_put(
        self, key: str, *, content_type: str, content_length: int, expires_in: dt.timedelta
    ) -> PresignedUpload:
        """A PUT URL valid only for ``expires_in``, signed for exactly ``content_type`` and
        exactly ``content_length`` bytes (security review M2: a simple S3 PUT presign has no
        native max-size parameter, only an exact one -- ``ContentLength`` is part of what
        SigV4 signs, so a browser that sends a different ``Content-Length`` header gets a
        signature mismatch instead of ever reaching the bucket). The caller already validated
        ``content_length`` against the type's rules-module cap before calling this."""
        ...

    def presign_get(self, key: str, *, expires_in: dt.timedelta) -> str:
        """A short-lived GET URL for viewing/downloading ``key`` (intake.md §3
        ``PRESIGNED_VIEW_URL_LIFETIME``)."""
        ...

    def head(self, key: str) -> ObjectMeta | None:
        """``None`` if ``key`` does not exist (never raises for a missing object)."""
        ...

    def delete(self, key: str) -> None:
        """Deleting a key that doesn't exist is not an error (idempotent, safe to retry)."""
        ...

    def copy(self, src_key: str, dest_key: str) -> None:
        """Server-side copy (e.g. promoting a processed derivative out of ``quarantine/``)."""
        ...

    def get_object(self, key: str) -> bytes:
        """Read an object's bytes directly (S2.4b's processing job/retention sweep: the
        worker is trusted infrastructure with its own storage credentials, unlike a browser,
        so it reads/writes objects directly rather than round-tripping through a presigned
        URL it would have to issue to itself). Raises ``FileNotFoundError`` if ``key`` is
        missing."""
        ...

    def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        """Write an object's bytes directly (see ``get_object``) — used to store a processed
        derivative under its final key."""
        ...

    def open_object(self, key: str) -> BinaryIO:
        """Open a readable binary stream for ``key`` without loading the whole object into
        memory first (N1 fix: the leadership thumb/view routes stream a response through this
        rather than buffering a full photo/video in a Python ``bytes`` object per request).
        Raises ``FileNotFoundError`` if ``key`` is missing, same as ``get_object``."""
        ...


def get_object_store() -> ObjectStore:
    """Loads the configured ``ObjectStore`` implementation. Not cached: tests/`override_settings`
    can swap ``HAM_OBJECT_STORE_BACKEND`` per-test without a stale singleton lingering."""
    from django.conf import settings
    from django.utils.module_loading import import_string

    backend_path = getattr(settings, "HAM_OBJECT_STORE_BACKEND", "") or ""
    if not backend_path:
        raise RuntimeError(
            "HAM_OBJECT_STORE_BACKEND is not configured. Set it to the dotted path of an "
            "ObjectStore implementation (see ham.integrations.storage, S2.4a)."
        )
    backend_cls = import_string(backend_path)
    return backend_cls()  # type: ignore[no-any-return]


__all__ = ["ObjectMeta", "ObjectStore", "PresignedUpload", "get_object_store"]
