"""`GET, POST /me` (foundation.md §7; auth-and-access.md §F "Me → Sign-in & security" — this
slice ships the non-security fields; §F's MFA/security rows arrive with S3b at
`/me/security`)."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ham.authz.guard import requires_action
from ham.identity.services import update_own_profile


@require_http_methods(["GET", "POST"])
@requires_action("me.view")
def me(request):
    ctx = request.actor
    profile = getattr(request.user, "profile", None)
    errors: dict[str, str] = {}
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        mobile_phone = request.POST.get("mobile_phone", "").strip()
        notify_email = request.POST.get("notify_email") == "on"
        if not full_name:
            errors["full_name"] = "Enter your name."
        if not errors:
            update_own_profile(
                ctx,
                full_name=full_name,
                mobile_phone=mobile_phone,
                notify_email=notify_email,
            )
            messages.success(request, "Your profile was updated.")
            return redirect("web:me")
        # Fall through to re-render with the attempted values and the error.
        profile_view = {"full_name": full_name, "mobile_phone": mobile_phone}
        notify_email_view = notify_email
    else:
        profile_view = {
            "full_name": profile.full_name if profile else "",
            "mobile_phone": profile.mobile_phone if profile else "",
        }
        notify_email_view = profile.notify_email if profile else True
    return render(
        request,
        "web/me.html",
        {
            "profile": profile_view,
            "notify_email": notify_email_view,
            "errors": errors,
        },
    )
