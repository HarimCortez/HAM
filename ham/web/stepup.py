"""`redirect_to_step_up`: builds the `/step-up?next=...&kind=...` redirect (foundation.md §7)
for views that don't use `ham.identity.web.handle_command_errors`'s decorator style (e.g.
`ham.web.views_admin_users`, `ham.web.views_audit`, which catch `StepUpRequired` inline
alongside other command errors). The real `/step-up` screen lives at `ham.web.auth_views.step_up`
(`ham/identity/mfa.py` for the TOTP verification); this module now only re-exports the
redirect-building helper — its S5-authored placeholder view has been replaced.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def redirect_to_step_up(request: HttpRequest, next_url: str, kind: str) -> HttpResponse:
    """Build the `/step-up?next=...&kind=...` redirect (foundation.md §7)."""
    url = reverse("web:step_up")
    return redirect(f"{url}?next={next_url}&kind={kind}")
