"""`handle_command_errors`: the one place a Django view translates the `@command` pipeline's
exceptions (`ham.authz.commands`) into HTTP responses (foundation.md §7 "/step-up?next=").

Any view that calls an `@command`-wrapped service function (e.g. the frontend engineer's Admin
screens calling `grant_global_role`/`revoke_global_role`/`audit.export`) should wrap it with
this decorator so a `StepUpRequired` becomes a redirect to `/step-up?next=<here>&kind=<kind>`
instead of an unhandled 500, and other command errors become the neutral "not available" page
or a plain user-facing message.

    from ham.identity.web import handle_command_errors

    @handle_command_errors
    @requires_action("role.grant_global")
    def grant_role_view(request, user_id):
        ...
        grant_global_role(request.actor, user_id=user_id, role=role)
        ...
"""

from __future__ import annotations

from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from ham.authz.commands import ImpersonationBlocked, PermissionDenied, StepUpRequired

__all__ = ["handle_command_errors", "safe_next_url"]


def safe_next_url(request: HttpRequest, *, default: str = "web:home") -> str:
    """Validates a `?next=` parameter against open-redirect abuse."""
    candidate = request.GET.get("next") or request.POST.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return reverse(default)


def handle_command_errors(view):
    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        try:
            return view(request, *args, **kwargs)
        except StepUpRequired as exc:
            here = request.get_full_path()
            query = urlencode({"next": here, "kind": exc.kind})
            return redirect(f"{reverse('web:step_up')}?{query}")
        except ImpersonationBlocked:
            messages.error(
                request,
                "That isn't available while you're acting as someone else. "
                "Return to your own account to do this.",
            )
            return redirect(safe_next_url(request))
        except PermissionDenied:
            return render(request, "web/not_found.html", status=404)

    return wrapper
