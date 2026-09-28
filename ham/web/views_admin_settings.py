"""Admin -> Church settings, Integrations, Rules (foundation.md §7).

Church settings and Integrations retry go through `ham.identity.services`'s
`update_church_profile`/`retry_outbox_delivery` `@command`s (S3b). Rules is fully read-only
against `ham.rules.view.rules_view`.
"""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ham.authz.commands import ImpersonationBlocked, PermissionDenied
from ham.authz.guard import requires_action
from ham.identity.services import retry_outbox_delivery, update_church_profile
from ham.outbox.services import recent_failures, subscriber_status_counts
from ham.platform.church import church_profile
from ham.rules.view import rules_view


@require_http_methods(["GET", "POST"])
@requires_action("church_profile.update")
def admin_church_settings(request):
    church = church_profile()
    errors: dict[str, str] = {}
    values = {
        "ham_phone": church.phone,
        "ham_email": church.email,
        "time_zone": church.time_zone,
        "website_url": church.website_url,
    }
    if request.method == "POST":
        values = {
            "ham_phone": request.POST.get("ham_phone", "").strip(),
            "ham_email": request.POST.get("ham_email", "").strip(),
            "time_zone": request.POST.get("time_zone", "").strip(),
            "website_url": request.POST.get("website_url", "").strip(),
        }
        if not values["time_zone"]:
            errors["time_zone"] = "Enter an IANA time zone, e.g. America/New_York."
        if not errors:
            try:
                update_church_profile(request.actor, **values)
            except ImpersonationBlocked:
                messages.error(
                    request,
                    "Church settings can't be changed while acting as someone else.",
                )
            else:
                messages.success(request, "Church settings updated.")
                return redirect("web:admin_church_settings")
    return render(request, "web/admin_church_settings.html", {"values": values, "errors": errors})


@require_http_methods(["GET"])
@requires_action("integrations.view_status")
def admin_integrations(request):
    return render(
        request,
        "web/admin_integrations.html",
        {
            "counts": subscriber_status_counts(),
            "failures": recent_failures(),
        },
    )


@require_http_methods(["POST"])
@requires_action("outbox.retry")
def admin_integrations_retry(request, delivery_id: uuid.UUID):
    try:
        retry_outbox_delivery(request.actor, delivery_id=delivery_id)
    except ImpersonationBlocked:
        messages.error(request, "Retrying isn't allowed while acting as someone else.")
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Delivery queued for retry.")
    return redirect("web:admin_integrations")


@require_http_methods(["GET"])
@requires_action("rules.view")
def admin_rules(request):
    return render(request, "web/admin_rules.html", {"rules_view": rules_view()})
