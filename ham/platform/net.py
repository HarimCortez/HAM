"""Best-effort client IP resolution (moved out of ``ham.web.auth_views`` in S2.0 so
``ham.requester_portal``'s own public-form rate limits (intake.md §9 "no third-party trackers
or CAPTCHAs") can reuse the exact same, already-reviewed logic — this belongs in
``ham.platform`` because both ``ham.identity`` (sign-in throttling) and every later public
surface need it, and ``ham.platform`` is the one layer everything may import.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


def client_ip(request: HttpRequest) -> str:
    """Security review round 3, N5: a client can send its own, entirely fake
    ``X-Forwarded-For`` prefix — only the right-most ``settings.HAM_TRUSTED_PROXY_COUNT`` hops
    were actually appended by proxies HAM controls. Trusting the *first* hop would let anyone
    bypass a per-IP throttle just by sending a made-up header.
    ``HAM_TRUSTED_PROXY_COUNT = 0`` (no proxy in front, e.g. local dev/tests) means "ignore the
    header entirely, use ``REMOTE_ADDR``"; Render's edge proxy adds exactly one hop.
    """
    trusted = settings.HAM_TRUSTED_PROXY_COUNT
    if trusted > 0:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if len(hops) >= trusted:
            return hops[-trusted]
    return request.META.get("REMOTE_ADDR", "")


__all__ = ["client_ip"]
