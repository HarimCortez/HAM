"""UUIDv7 identifiers (foundation.md §3: "All IDs are UUIDv7").

UUIDv7 embeds a millisecond timestamp ahead of random bits, so primary keys sort roughly by
creation time. That keeps Postgres's PK index append-mostly (unlike UUIDv4) while still being
non-guessable, which matters for anything referenced by an external token (media ids, secure
links, §69).
"""

from __future__ import annotations

import os
import time
import uuid

from django.db import models

try:  # pragma: no cover - exercised via uuid7() either way
    from uuid6 import uuid7 as _library_uuid7
except ImportError:  # pragma: no cover
    _library_uuid7 = None  # type: ignore[assignment]


def uuid7() -> uuid.UUID:
    """Return a new UUIDv7. Prefers the `uuid6` library; falls back to a hand-rolled
    implementation (RFC 9562) so id generation never hard-depends on one package."""
    if _library_uuid7 is not None:
        return _library_uuid7()
    return _uuid7_fallback()


def _uuid7_fallback() -> uuid.UUID:
    ts_ms = int(time.time() * 1000)
    rand = bytearray(os.urandom(10))
    b = bytearray(ts_ms.to_bytes(6, "big")) + rand
    b[6] = (b[6] & 0x0F) | 0x70  # version 7
    b[8] = (b[8] & 0x3F) | 0x80  # RFC 4122 variant
    return uuid.UUID(bytes=bytes(b))


class UUID7Field(models.UUIDField):
    """A UUID primary-key field defaulting to a fresh UUIDv7 value."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("primary_key", True)
        kwargs.setdefault("default", uuid7)
        kwargs.setdefault("editable", False)
        super().__init__(*args, **kwargs)

    def deconstruct(self):  # type: ignore[no-untyped-def]
        # Django's generic deconstruct() drops kwargs equal to models.Field defaults
        # (primary_key=False), and __init__ above would then re-default it to True on a
        # migration round-trip. Always emit primary_key explicitly so non-PK uses survive.
        name, path, args, kwargs = super().deconstruct()
        kwargs["primary_key"] = self.primary_key
        return name, path, args, kwargs
