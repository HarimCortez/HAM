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

# Scope trim (step-1 usability review, prd.md): calendar/drive/fitness are documented no-op
# seams (PRD §50/§51/§36 deferred) so the outbox dispatcher always has somewhere to deliver
# to; showing them as rows on this page would imply those integrations exist. Only the ones
# that actually do something in step 1 are visible here.
_VISIBLE_SUBSCRIBERS = frozenset({"email"})


@require_http_methods(["GET", "POST"])
@requires_action("church_profile.update")
def admin_church_settings(request):
    church = church_profile()
    errors: dict[str, str] = {}
    values: dict[str, object] = {
        "ham_phone": church.phone,
        "ham_email": church.email,
        "time_zone": church.time_zone,
        "website_url": church.website_url,
        "serves_days": list(church.serves_days),
    }
    if request.method == "POST":
        # Q-112: a form that doesn't render the (later, S2.7) serves-days control at all never
        # sends the key — leave the setting unchanged rather than forcing every caller of this
        # endpoint to resend it. A form that *does* render it must send at least one day.
        if "serves_days" in request.POST:
            serves_days_raw = request.POST.getlist("serves_days")
            serves_days = [int(d) for d in serves_days_raw if d.strip().lstrip("-").isdigit()]
        else:
            serves_days = list(church.serves_days)
        values = {
            "ham_phone": request.POST.get("ham_phone", "").strip(),
            "ham_email": request.POST.get("ham_email", "").strip(),
            "time_zone": request.POST.get("time_zone", "").strip(),
            "website_url": request.POST.get("website_url", "").strip(),
            "serves_days": serves_days,
        }
        if not values["time_zone"]:
            errors["time_zone"] = "Enter an IANA time zone, e.g. America/New_York."
        if not values["serves_days"]:
            # Q-112: at least one day HAM serves is required (the intake form's availability
            # question needs at least one option).
            errors["serves_days"] = "Choose at least one day HAM serves requesters."
        if not errors:
            try:
                update_church_profile(request.actor, **values)
            except ImpersonationBlocked:
                messages.error(
                    request,
                    "Church settings can't be changed while acting as someone else.",
                )
            except ValueError as exc:
                # Q-030/§70.5: an unrecognized IANA time zone name, or Q-112 bad serves_days.
                errors["time_zone"] = str(exc)
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
            "counts": [
                row for row in subscriber_status_counts() if row.subscriber in _VISIBLE_SUBSCRIBERS
            ],
            "failures": [d for d in recent_failures() if d.subscriber in _VISIBLE_SUBSCRIBERS],
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
