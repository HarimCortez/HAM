"""Route guard middleware (foundation.md §7): every URL must declare an action via
``@requires_action("x")`` or be listed in ``PUBLIC_ROUTES``. Undeclared routes fail closed.

Denied and undeclared routes get the same neutral response (navigation.md §6 "No permission /
not found"), so a project's existence — or a missing action declaration — is never leaked.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .context import ActorContext
from .matrix import authorize

# URL *names* that never require an action (foundation.md §7): health check, sign-in family
# (S3b), manifest/service worker/offline page, and Django's own static file serving (which
# has no url name to match, so STATIC_URL prefix is checked separately below).
PUBLIC_ROUTES: frozenset[str] = frozenset(
    {
        "healthz",
        "sign_in",
        "sign_in_code",
        "sign_in_link",
        "manifest",
        "service_worker",
        "offline",
    }
)

_ACTION_ATTR = "_ham_action"
NOT_AVAILABLE_TEMPLATE = "web/not_found.html"


def requires_action(action: str) -> Callable:
    """Decorate a view with the action it requires. The route guard denies any view lacking
    this (or absent from ``PUBLIC_ROUTES``) — fail closed, not fail open."""

    def decorator(view: Callable) -> Callable:
        setattr(view, _ACTION_ATTR, action)
        return view

    return decorator


def _not_available(request: HttpRequest) -> HttpResponse:
    # navigation.md §6: identical copy/status for "doesn't exist" and "not allowed". The
    # template is looked up by name (owned by ham.web) so authz never imports the web layer.
    return render(request, NOT_AVAILABLE_TEMPLATE, status=404)


class RouteGuardMiddleware:
    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable,
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        resolver_match = getattr(request, "resolver_match", None)
        url_name = resolver_match.url_name if resolver_match else None
        if url_name in PUBLIC_ROUTES:
            return None
        if request.path.startswith("/static/") or request.path.startswith("/staticfiles/"):
            return None

        action = getattr(view_func, _ACTION_ATTR, None)
        if action is None:
            return _not_available(request)

        ctx = getattr(request, "actor", None) or ActorContext.anonymous()
        decision = authorize(ctx, action)
        if not decision.allowed or decision.blocked_by_impersonation:
            return _not_available(request)
        return None
