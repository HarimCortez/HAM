"""Dev-only view serving signed local-storage URLs (S2.4a).

Stands in for the browser-facing half of a real object store (presigned PUT/GET) when
`HAM_OBJECT_STORE_BACKEND` is `LocalObjectStore`. Mounted unconditionally in `config/urls.py`
(harmless in production, which always configures the R2 adapter instead — nothing here is
reachable without a tamper-proof, time-limited, single-purpose signed token; there is no
listing, no unauthenticated key access). This is infrastructure, not a `@command`-wrapped
domain action, so it deliberately does not go through `ham.authz`/`ham.audit` — the token
itself *is* the capability, exactly like a real presigned S3 URL. Authorization for *who gets
handed a token in the first place* happens earlier, in `ham.media`'s services.
"""

from __future__ import annotations

from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
)
from django.views.decorators.csrf import csrf_exempt

from .local import LocalObjectStore, is_expired, unsign_payload


@csrf_exempt
def local_storage_object(request: HttpRequest, token: str) -> HttpResponse:
    payload = unsign_payload(token)
    if payload is None:
        return HttpResponseForbidden("invalid token")
    if is_expired(payload):
        return HttpResponseForbidden("token expired")

    store = LocalObjectStore()
    key = payload["key"]
    op = payload.get("op")

    if op == "get":
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        meta = store.head(key)
        if meta is None:
            return HttpResponseNotFound()
        return HttpResponse(store.get_object(key), content_type=meta.content_type)

    if op == "put":
        if request.method != "PUT":
            return HttpResponseNotAllowed(["PUT"])
        content_type = payload["ct"]
        declared_length = payload["len"]
        body = request.body
        if len(body) != declared_length:
            return HttpResponseBadRequest(
                "object size does not match the length this URL was signed for"
            )
        request_content_type = (request.content_type or "").split(";")[0].strip()
        if request_content_type != content_type:
            return HttpResponseBadRequest("content type does not match this URL's signature")
        store.put_object(key, body, content_type=content_type)
        return HttpResponse(status=204)

    return HttpResponseForbidden("invalid token")  # pragma: no cover - unreachable op values
