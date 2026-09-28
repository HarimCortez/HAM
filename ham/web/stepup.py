"""Temporary stand-in for S3b's real `/step-up` screen (foundation.md §7 `GET, POST
`/step-up?next=`` — "signed-in MFA role" refreshes step-up freshness with a TOTP challenge).

S3b is building the real screen and session write in parallel (see this slice's task list:
"S3b will also provide a helper — if absent in your worktree write a tiny local one"). This
stub has **no TOTP check at all** — it exists only so the S5 screens that raise
`StepUpRequired` (role grant/revoke, MFA reset, audit export, "Troubleshoot as...") have
somewhere to redirect to and a way to resume the original action for tests/screenshots.

**Merge note:** delete `step_up_stub` and this module's URL registration once S3b's real
`web:step_up` view lands; nothing else needs to change because callers only ever do
`redirect_to_step_up(request, next_url, kind)`, never reference this module's internals.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from ham.authz.context import SESSION_KEY_STEP_UP
from ham.authz.guard import requires_action
from ham.platform.clock import now as clock_now


def _safe_next(request: HttpRequest, candidate: str | None) -> str:
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}):
        return candidate
    return reverse("web:home")


def redirect_to_step_up(request: HttpRequest, next_url: str, kind: str) -> HttpResponse:
    """Build the `/step-up?next=...&kind=...` redirect (foundation.md §7)."""
    url = reverse("web:step_up")
    return redirect(f"{url}?next={next_url}&kind={kind}")


@require_http_methods(["GET", "POST"])
@requires_action("shell.use")
def step_up_stub(request: HttpRequest) -> HttpResponse:
    next_url = _safe_next(request, request.GET.get("next") or request.POST.get("next"))
    kind = request.GET.get("kind") or request.POST.get("kind") or ""
    if not request.user.is_authenticated:
        return redirect("web:home")
    if request.method == "POST":
        step_up_at = dict(request.session.get(SESSION_KEY_STEP_UP, {}))
        step_up_at[kind] = clock_now().isoformat()
        request.session[SESSION_KEY_STEP_UP] = step_up_at
        return redirect(next_url)
    return render(request, "web/step_up_stub.html", {"next": next_url, "kind": kind})
