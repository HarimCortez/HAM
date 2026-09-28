"""R2 / S3-compatible `ObjectStore` adapter (S2.4a, production).

Cloudflare R2 speaks the S3 API, so this is a thin `boto3` client wrapper. Every method is a
plain synchronous call (no outbox event, no retry queue, `ham.platform.storage.ObjectStore`'s
own docstring: "a storage outage must surface as an ordinary exception the caller handles",
CLAUDE.md §70.3).

Settings (`config/settings/base.py`, `docs/dev-environment.md`): `HAM_S3_BUCKET`,
`HAM_S3_ENDPOINT_URL`, `HAM_S3_REGION`, `HAM_S3_ACCESS_KEY_ID`, `HAM_S3_SECRET_ACCESS_KEY`.
Raises `RuntimeError` naming the missing setting if constructed without them, rather than a
confusing `boto3`/network error later.
"""

from __future__ import annotations

import datetime as dt
from typing import BinaryIO

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from django.conf import settings

from ham.platform.storage import ObjectMeta, PresignedUpload


class R2ObjectStore:
    """Implements `ham.platform.storage.ObjectStore` against an R2/S3-compatible bucket."""

    def __init__(self) -> None:
        bucket = getattr(settings, "HAM_S3_BUCKET", "") or ""
        endpoint = getattr(settings, "HAM_S3_ENDPOINT_URL", "") or ""
        access_key = getattr(settings, "HAM_S3_ACCESS_KEY_ID", "") or ""
        secret_key = getattr(settings, "HAM_S3_SECRET_ACCESS_KEY", "") or ""
        missing = [
            name
            for name, value in (
                ("HAM_S3_BUCKET", bucket),
                ("HAM_S3_ENDPOINT_URL", endpoint),
                ("HAM_S3_ACCESS_KEY_ID", access_key),
                ("HAM_S3_SECRET_ACCESS_KEY", secret_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError("R2ObjectStore is missing required settings: " + ", ".join(missing))
        self._bucket = bucket
        region = getattr(settings, "HAM_S3_REGION", "") or "auto"
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            # SigV4 + path-style addressing: what R2 (and most non-AWS S3-compatible
            # endpoints) expect; virtual-hosted-style addressing is an AWS-only default.
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def presign_put(
        self, key: str, *, content_type: str, content_length: int, expires_in: dt.timedelta
    ) -> PresignedUpload:
        now = dt.datetime.now(dt.UTC)
        url = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
                # Security review M2: ``ContentLength`` is signed as part of the URL (SigV4
                # covers every param in ``Params``), so the browser's PUT must send exactly
                # this ``Content-Length`` header or S3 rejects it with a signature mismatch
                # before storing anything. The object's actual size is still re-checked
                # server-side on completion (intake.md §9) as defense in depth.
                "ContentLength": content_length,
            },
            ExpiresIn=int(expires_in.total_seconds()),
        )
        return PresignedUpload(url=url, key=key, expires_at=now + expires_in)

    def presign_get(self, key: str, *, expires_in: dt.timedelta) -> str:
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=int(expires_in.total_seconds()),
        )
        return url

    def head(self, key: str) -> ObjectMeta | None:
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return ObjectMeta(
            key=key,
            size=int(resp.get("ContentLength", 0)),
            content_type=resp.get("ContentType", ""),
        )

    def delete(self, key: str) -> None:
        # S3 DeleteObject is idempotent (204 whether or not the key existed) — matches the
        # protocol's "deleting a key that doesn't exist is not an error" contract for free.
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def copy(self, src_key: str, dest_key: str) -> None:
        self._client.copy_object(
            Bucket=self._bucket,
            Key=dest_key,
            CopySource={"Bucket": self._bucket, "Key": src_key},
        )

    def get_object(self, key: str) -> bytes:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(key) from exc
            raise
        body: bytes = resp["Body"].read()
        return body

    def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def open_object(self, key: str) -> BinaryIO:
        # N1 fix: botocore's `StreamingBody` (the `"Body"` of a `get_object` response) is
        # itself a readable binary stream backed by the underlying HTTP connection -- reading
        # it in chunks (what `django.http.FileResponse` does) never buffers the whole object.
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(key) from exc
            raise
        body: BinaryIO = resp["Body"]
        return body
