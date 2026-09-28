"""A minimal Content-Security-Policy middleware (security review M6).

Not `django-csp` (not a project dependency, and this app's policy is a handful of directives —
adding a whole library for one header felt like the wrong trade for "keep it simple",
CLAUDE.md priority 4). Every directive is `'self'` except where the app shell genuinely needs
otherwise:

- `worker-src 'self'` / the default `script-src 'self'` — the PWA service worker
  (`ham/web`'s `/sw.js`) is same-origin.
- `manifest-src 'self'` — `/manifest.webmanifest` is same-origin.
- `font-src 'self'` — brand fonts are self-hosted (`design-system/brands/<id>/fonts`,
  foundation.md §2.2), never a remote font CDN.
- `style-src 'self' 'unsafe-inline'` — HTMX/the current templates use a few inline `style=`
  attributes; tightening this to a nonce-based policy is future work once the frontend
  engineer's markup no longer needs it.
- `connect-src 'self'` — HTMX requests and the offline queue only ever call same-origin API
  routes (foundation.md §1: "HAM must keep working if any integration is down" — nothing here
  talks to a third party directly from the browser).
- `frame-ancestors 'none'` (matches `X_FRAME_OPTIONS = DENY` — nobody may frame HAM at all
  today); the public-embed step (Q-005) will widen this to the church's own site only,
  never to arbitrary hosts, once that screen exists.

Only installed in `config/settings/prod.py`'s `MIDDLEWARE` (dev/test skip it so a local
`DEBUG=True` run and Playwright/pytest never have to work around a CSP violation while
templates are still being built).
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "manifest-src 'self'",
        "worker-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
)


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        return response
