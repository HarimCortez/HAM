"""`GET, POST /me` (foundation.md §7; auth-and-access.md §F "Me → Sign-in & security" — this
slice ships the non-security fields; §F's MFA/security rows arrive with S3b at
`/me/security`)."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ham.authz.commands import ImpersonationBlocked
from ham.authz.guard import requires_action
from ham.identity.models import SharedIdentityProfile
from ham.identity.services import update_own_profile


@require_http_methods(["GET", "POST"])
@requires_action("me.view")
def me(request):
    """Item 6: display and save the *same* (effective) identity — `ctx.user_id`, the
    impersonation target when impersonating — never the real signed-in person's own
    ``request.user``. ``me.update`` is blocked while impersonating (matrix), so the form is
    read-only in that case rather than silently editing the wrong person's profile."""
    ctx = request.actor
    profile = SharedIdentityProfile.objects.filter(user_id=ctx.user_id).first()
    errors: dict[str, str] = {}
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        mobile_phone = request.POST.get("mobile_phone", "").strip()
        notify_email = request.POST.get("notify_email") == "on"
        if not full_name:
            errors["full_name"] = "Enter your name."
        if not errors:
            try:
                update_own_profile(
                    ctx,
                    full_name=full_name,
                    mobile_phone=mobile_phone,
                    notify_email=notify_email,
                )
            except ImpersonationBlocked:
                messages.error(
                    request,
                    "Profile changes aren't allowed while acting as someone else.",
                )
                return redirect("web:me")
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
            "read_only": ctx.is_impersonating,
        },
    )
