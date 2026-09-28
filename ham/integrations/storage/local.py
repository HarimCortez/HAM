"""Local-filesystem `ObjectStore` adapter (S2.4a, dev/test).

Files live under `settings.HAM_LOCAL_STORAGE_ROOT`. There is no real "presigned URL" without
a cloud storage service behind it, so `presign_put`/`presign_get` return a URL to
`ham.integrations.storage.dev_views.local_storage_object` — a small Django view, mounted
unconditionally in `config/urls.py` (harmless outside dev/test: every request must carry a
tamper-proof, time-limited, single-purpose signed token; there is nothing to reach without
one) — that performs the PUT/GET itself. This keeps the calling code (`ham.media`) identical
between the local adapter and the real R2 adapter: both are just "do an HTTP PUT/GET against
this URL".
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from django.conf import settings
from django.core.signing import BadSignature, Signer

from ham.platform.storage import ObjectMeta, PresignedUpload

_SIGNER_SALT = "ham.integrations.storage.local"
_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.-]*$")


def _signer() -> Signer:
    return Signer(salt=_SIGNER_SALT)


def sign_payload(payload: dict) -> str:
    return _signer().sign_object(payload)


def unsign_payload(token: str) -> dict | None:
    """Returns the payload, or `None` if the token was tampered with / malformed. Does not
    check expiry — that's the caller's job (`dev_views.local_storage_object`), since it needs
    to answer "expired" (403) differently from "invalid" (403) for observability, and
    `ObjectStore` callers never see this token at all."""
    try:
        payload: dict = _signer().unsign_object(token)
    except BadSignature:
        return None
    return payload


def is_expired(payload: dict, *, now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now(dt.UTC)
    exp = dt.datetime.fromisoformat(payload["exp"])
    return now >= exp


def _safe_key(key: str) -> str:
    """Refuses a key that could escape `HAM_LOCAL_STORAGE_ROOT` (path traversal) — same
    protection real object storage gives for free by having no filesystem at all."""
    if not key or not _SAFE_KEY_RE.match(key) or "/../" in f"/{key}/" or key.endswith(".."):
        raise ValueError(f"unsafe object key: {key!r}")
    return key


class LocalObjectStore:
    """Implements `ham.platform.storage.ObjectStore` against the local filesystem."""

    def __init__(self) -> None:
        self._root = Path(getattr(settings, "HAM_LOCAL_STORAGE_ROOT", "") or "")
        if not self._root:
            raise RuntimeError("HAM_LOCAL_STORAGE_ROOT is not configured")

    def _object_path(self, key: str) -> Path:
        return self._root / "objects" / _safe_key(key)

    def _meta_path(self, key: str) -> Path:
        return self._root / "meta" / f"{_safe_key(key)}.json"

    def _base_url(self) -> str:
        base_url = getattr(settings, "HAM_BASE_URL", "") or "http://localhost:8000"
        return base_url.rstrip("/")

    def presign_put(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: dt.timedelta
    ) -> PresignedUpload:
        now = dt.datetime.now(dt.UTC)
        expires_at = now + expires_in
        token = sign_payload(
            {
                "op": "put",
                "key": key,
                "ct": content_type,
                "max": max_bytes,
                "exp": expires_at.isoformat(),
            }
        )
        url = f"{self._base_url()}/dev/storage/{token}"
        return PresignedUpload(url=url, key=key, expires_at=expires_at)

    def presign_get(self, key: str, *, expires_in: dt.timedelta) -> str:
        now = dt.datetime.now(dt.UTC)
        expires_at = now + expires_in
        token = sign_payload({"op": "get", "key": key, "exp": expires_at.isoformat()})
        return f"{self._base_url()}/dev/storage/{token}"

    def head(self, key: str) -> ObjectMeta | None:
        meta_path = self._meta_path(key)
        if not meta_path.exists():
            return None
        import json

        data = json.loads(meta_path.read_text())
        return ObjectMeta(key=key, size=data["size"], content_type=data["content_type"])

    def delete(self, key: str) -> None:
        self._object_path(key).unlink(missing_ok=True)
        self._meta_path(key).unlink(missing_ok=True)

    def copy(self, src_key: str, dest_key: str) -> None:
        meta = self.head(src_key)
        if meta is None:
            raise FileNotFoundError(src_key)
        data = self.get_object(src_key)
        self.put_object(dest_key, data, content_type=meta.content_type)

    def get_object(self, key: str) -> bytes:
        path = self._object_path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        import json

        obj_path = self._object_path(key)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(data)
        meta_path = self._meta_path(key)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps({"size": len(data), "content_type": content_type}))
