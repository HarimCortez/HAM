"""Route guard middleware (foundation.md §7): every URL must declare an action via
``@requires_action("x")`` or be listed in ``PUBLIC_ROUTES``. Undeclared routes fail closed.

Denied and undeclared routes get the same neutral response (navigation.md §6 "No permission /
not found"), so a project's existence — or a missing action declaration — is never leaked.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from ham.audit.services import record as audit_record

from .commands import _AUDITED_ON_DENIAL
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
        # Reached mid-sign-in, before `django_login()` has run (foundation.md §7): the views
        # themselves check for the pending-login session state and redirect to `sign_in` if
        # it's missing, rather than the route guard denying them outright.
        "sign_in_mfa",
        "mfa_setup",
        "mfa_setup_codes",
        # Security review L5/UX M3: "Sign out" from a mid-sign-in/enrollment screen must work
        # before `django_login()` has run, same reasoning as the other pending-login routes
        # just above — it clears the pending session state itself rather than relying on the
        # guard to already consider the person signed in.
        "sign_in_cancel",
        "manifest",
        "service_worker",
        "offline",
        # S2.4a: the dev-only local-storage adapter's stand-in for a presigned S3/R2 URL.
        # Authorization here is the signed, time-limited, single-purpose token itself (see
        # ham.integrations.storage.dev_views), exactly like a real presigned URL never goes
        # through this ActorContext-based guard either.
        "local-storage-object",
        # S2.7: the public requester screens (PRD §7 "requesters have no account"). Every
        # name here is `ham/web/urls_requester.py`'s own; per-request access control is the
        # draft cookie / access-link token the view itself resolves
        # (`ham.requester_portal.services.resolve_token`), exactly like the sign-in-link
        # family above is public at the route-guard layer and self-checks the token.
        "request_help_start",
        "request_help_begin",
        "request_help_start_over",
        "request_help_step",
        "request_help_verify",
        "request_help_verify_link",
        "request_help_new_link",
        "request_help_saved",
        "request_help_secure_page",
        "request_help_photos",
        "request_help_media_reserve",
        "request_help_media_complete",
        "request_help_media_remove",
        "request_help_link_expired_send",
        "request_help_find",
        # S3.7: step-3 requester screens (approvals-contracts.md §8). Same reasoning -- the
        # access-link token, resolved fresh on every request, is the real control
        # (`requester.question.answer`/`requester.reconsideration.request`, Scope.OWN_REQUEST).
        "request_help_question_answer",
        "request_help_reconsider",
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
        if not ctx.is_authenticated:
            # foundation.md §7 "Unauthenticated requests to protected routes redirect to
            # /sign-in?next=" — distinct from the neutral 404 for a signed-in person who
            # simply lacks the permission (navigation.md §6), which never leaks whether a
            # route needs *more* privilege than "signed in at all".
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{reverse('web:sign_in')}?{query}")
        decision = authorize(ctx, action)
        if not decision.allowed:
            # foundation.md §4 "Denied privileged actions ... write authz.denied. Ordinary
            # denials are not logged, to avoid noise" — same audited-action set commands.py
            # uses for a denial at the service layer, so a route hit and a command call are
            # audited consistently for the same action.
            if action in _AUDITED_ON_DENIAL:
                audit_record(
                    ctx=ctx,
                    action="authz.denied",
                    target_type="action",
                    target_id=action,
                    reason=decision.reason,
                )
            return _not_available(request)
        if decision.blocked_by_impersonation:
            audit_record(
                ctx=ctx,
                action="impersonation.action_blocked",
                target_type="action",
                target_id=action,
                reason="blocked while impersonating (§59)",
            )
            return _not_available(request)
        return None
