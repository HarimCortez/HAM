"""Leadership request screens L1-L11 (intake.md §7; docs/ux/intake.md §6; S2.8).

Every view declares its action via `@requires_action` (route guard, foundation.md §7); the
service layer (`ham.requests.services`/`ham.media.services`) re-checks through the matrix on
every write, so a template-level "don't show the button" is never the only guard (CLAUDE.md).
"""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from ham.authz import roles
from ham.authz.commands import ImpersonationBlocked, PermissionDenied
from ham.authz.guard import requires_action
from ham.authz.matrix import authorize
from ham.identity.services import display_names_for
from ham.media.services import media_gallery_for
from ham.requests import presentation
from ham.requests.queries import (
    can_see_needs_phone_check,
    contact_verifications,
    get_request_by_id,
    get_request_detail,
    list_requests,
    needs_phone_check_list,
    outcome_summary,
    request_history,
)
from ham.requests.services import reveal_requester_pii
from ham.requests.states import CancelReason, RequestStatus, VerificationMethod

_DIR_AD = frozenset({roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR})
_PAS_BRD = frozenset({roles.PASTOR, roles.BOARD_REPRESENTATIVE})


# --------------------------------------------------------------------------------------
# L1 / L8 list
# --------------------------------------------------------------------------------------
def _tabs_for(ctx) -> list[dict]:
    """Which saved views this viewer sees, each with its own count (P§3, UX L1)."""
    tabs: list[dict] = []
    if can_see_needs_phone_check(ctx):
        tabs.append(
            {
                "key": "phone_check",
                "label": "Needs a phone check",
                "count": len(needs_phone_check_list(ctx)),
            }
        )
    if ctx.effective_roles & (_DIR_AD | _PAS_BRD | {roles.ADMINISTRATOR}):
        tabs.append(
            {
                "key": "awaiting",
                "label": "Awaiting approval",
                "count": len(list_requests(ctx, status=RequestStatus.AWAITING_APPROVAL.value)),
            }
        )
    if ctx.effective_roles & (_DIR_AD | {roles.ADMINISTRATOR}):
        tabs.append({"key": "all", "label": "All", "count": len(list_requests(ctx))})
    return tabs


def _rows_for_tab(ctx, tab: str, *, reference_number: int | None, category: str, status: str):
    if tab == "phone_check":
        return needs_phone_check_list(ctx)
    if tab == "awaiting":
        return list_requests(
            ctx, status=RequestStatus.AWAITING_APPROVAL.value, reference_number=reference_number
        )
    # "all"
    rows = list_requests(ctx, status=status or None, reference_number=reference_number)
    if category:
        rows = [r for r in rows if r.need_category == category]
    return rows


def _default_tab(ctx, tabs: list[dict]) -> str:
    keys = [t["key"] for t in tabs]
    if "phone_check" in keys and next(t for t in tabs if t["key"] == "phone_check")["count"] > 0:
        return "phone_check"
    if "awaiting" in keys:
        return "awaiting"
    return keys[0] if keys else "awaiting"


@require_http_methods(["GET"])
@requires_action("request.list")
def requests_list(request, *, forced_tab: str | None = None):
    ctx = request.actor
    tabs = _tabs_for(ctx)
    tab = forced_tab or request.GET.get("tab") or _default_tab(ctx, tabs)
    if tab not in {t["key"] for t in tabs}:
        tab = _default_tab(ctx, tabs)

    q = request.GET.get("q", "").strip()
    reference_number: int | None = None
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        reference_number = int(digits) if digits else -1  # -1 -> matches nothing
    category = request.GET.get("category", "")
    status = request.GET.get("status", "") if tab == "all" else ""

    rows = _rows_for_tab(
        ctx, tab, reference_number=reference_number, category=category, status=status
    )

    selected_id = request.GET.get("id", "")
    selected_detail = None
    if selected_id:
        try:
            selected_uuid = uuid.UUID(selected_id)
        except ValueError:
            selected_uuid = None
        if selected_uuid and any(r.id == selected_uuid for r in rows):
            selected_detail = _build_detail_context(ctx, selected_uuid)
    elif rows:
        selected_detail = _build_detail_context(ctx, rows[0].id)

    return render(
        request,
        "web/requests_list.html",
        {
            "tabs": tabs,
            "active_tab": tab,
            "rows": rows,
            "q": q,
            "category": category,
            "status": status,
            "category_choices": presentation.NEED_CATEGORY_LABELS.items(),
            "status_choices": presentation.STATUS_LABELS.items(),
            "need_category_labels": presentation.NEED_CATEGORY_LABELS,
            "status_labels": presentation.STATUS_LABELS,
            "status_tones": presentation.STATUS_TONES,
            "selected_id": str(selected_detail["detail"].id) if selected_detail else "",
            "selected": selected_detail,
        },
    )


@require_http_methods(["GET"])
@requires_action("request.needs_phone_check.list")
def requests_needs_phone_check(request):
    return requests_list(request, forced_tab="phone_check")


# --------------------------------------------------------------------------------------
# L2 detail (also used for the >=1280 split-view detail pane, via _build_detail_context)
# --------------------------------------------------------------------------------------
def _build_detail_context(ctx, request_id: uuid.UUID, *, revealed=None) -> dict | None:
    detail = get_request_detail(ctx, request_id)
    if detail is None:
        return None
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None:
        return None

    verifications = contact_verifications(request_id)
    latest = verifications[-1] if verifications else None
    names = display_names_for(
        [v.verified_by_user_id for v in verifications if v.verified_by_user_id]
    )
    if detail.status == RequestStatus.NEEDS_PHONE_CHECK.value:
        contact_state = "Phone check needed"
    elif latest and latest.method == VerificationMethod.STAFF_PHONE_CALL.value:
        actor = names.get(latest.verified_by_user_id, "") if latest.verified_by_user_id else ""
        contact_state = f"Verified by phone call{' · ' + actor if actor else ''}"
    elif latest:
        contact_state = "Email confirmed"
    else:
        contact_state = ""

    gallery = media_gallery_for(ctx, request_id)
    matches = outcome_summary(request_row)
    history = request_history(request_row)
    history_names = display_names_for([e.actor_user_id for e in history if e.actor_user_id])

    can_cancel = authorize(ctx, "request.cancel", request_row).allowed
    can_verify_phone = (
        detail.status == RequestStatus.NEEDS_PHONE_CHECK.value
        and authorize(ctx, "request.contact_verify_phone", request_row).allowed
    )
    can_reopen_media = authorize(ctx, "request_media.reopen", request_row).allowed
    can_view_history = authorize(ctx, "request.history.view", request_row).allowed

    return {
        "detail": detail,
        "request_row": request_row,
        "contact_state": contact_state,
        "updates_by": presentation.CONTACT_METHOD_LABELS.get(
            detail.preferred_contact_method, detail.preferred_contact_method
        ),
        "source_label": presentation.SOURCE_LABELS.get(request_row.source, request_row.source),
        "need_category_label": presentation.need_category_label(detail.need_category),
        "status_label": presentation.status_label(detail.status),
        "status_tone": presentation.status_tone(detail.status),
        "property_type_label": presentation.PROPERTY_TYPE_LABELS.get(
            detail.property_type, detail.property_type
        ),
        "relationship_label": presentation.RELATIONSHIP_LABELS.get(
            detail.relationship_to_property, detail.relationship_to_property
        ),
        "cancel_reason_label": presentation.cancel_reason_label(detail.cancel_reason_code)
        if detail.cancel_reason_code
        else "",
        "gallery": gallery,
        "matches": [
            {
                "request_id": m.request_id,
                "display_number": m.display_number,
                "status_label": presentation.status_label(m.status),
                "status_tone": presentation.status_tone(m.status),
                "cancel_reason_label": presentation.cancel_reason_label(m.cancel_reason_code)
                if m.cancel_reason_code
                else "",
                "reasons": [presentation.match_reason_label(r) for r in m.reasons],
            }
            for m in matches
        ],
        "history": [
            {
                "label": e.label,
                "occurred_at": e.occurred_at,
                "actor": history_names.get(e.actor_user_id, "") if e.actor_user_id else "",
            }
            for e in history
        ]
        if can_view_history
        else [],
        "can_view_history": can_view_history,
        "can_cancel": can_cancel,
        "can_verify_phone": can_verify_phone,
        "can_reopen_media": can_reopen_media,
        "revealed": revealed,
        "is_director": roles.HAM_DIRECTOR in ctx.effective_roles,
    }


@require_http_methods(["GET"])
@requires_action("request.view")
def request_detail(request, request_id: uuid.UUID):
    ctx = request.actor
    context = _build_detail_context(ctx, request_id)
    if context is None:
        return render(request, "web/not_found.html", status=404)
    context["standalone"] = True
    return render(request, "web/request_detail.html", context)


@require_http_methods(["POST"])
@requires_action("request.view")
def request_reveal_contact(request, request_id: uuid.UUID):
    """The deliberate "Show contact details" button (Q-024, Q-124). `reveal_requester_pii`
    both authorizes (raises `PermissionDenied` for the Administrator/anyone unauthorized) and
    audits (except a non-impersonating Director), so this view has nothing else to guard."""
    ctx = request.actor
    try:
        revealed = reveal_requester_pii(ctx, request_id=request_id, surface="detail_panel")
    except PermissionDenied:
        return render(request, "web/not_found.html", status=404)
    context = _build_detail_context(ctx, request_id, revealed=revealed)
    if context is None:
        return render(request, "web/not_found.html", status=404)
    context["standalone"] = True
    return render(request, "web/request_detail.html", context)


# --------------------------------------------------------------------------------------
# L9 phone check sheet
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.contact_verify_phone")
def request_phone_check(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None or request_row.status != RequestStatus.NEEDS_PHONE_CHECK.value:
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        confirmed = request.POST.get("confirmed") == "on"
        if not confirmed:
            messages.error(
                request, "Tick the box confirming you spoke with the requester before continuing."
            )
        else:
            from ham.requests.services import verify_by_phone

            try:
                verify_by_phone(ctx, request_id=request_id)
            except ImpersonationBlocked:
                messages.error(
                    request, "Phone checks can't be recorded while acting as someone else."
                )
            except (PermissionDenied, ValueError) as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"Verified by phone call · {request_row.display_number}")
                return redirect("web:request_detail", request_id=request_id)
        return redirect("web:request_phone_check", request_id=request_id)

    try:
        revealed = reveal_requester_pii(ctx, request_id=request_id, surface="phone_check")
    except PermissionDenied:
        return render(request, "web/not_found.html", status=404)

    # Q-148/M6: the phone-check sheet is one of the two places (with the leadership detail
    # view) that shows R5's "anything else about reaching you or visiting?" note.
    detail = get_request_detail(ctx, request_id)
    contact_note = detail.contact_note if detail is not None else ""

    return render(
        request,
        "web/request_phone_check.html",
        {
            "request_row": request_row,
            "revealed": revealed,
            "contact_note": contact_note,
            "is_impersonating": ctx.is_impersonating,
            "is_director": roles.HAM_DIRECTOR in ctx.effective_roles,
        },
    )


# --------------------------------------------------------------------------------------
# L10 close sheet
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.cancel")
def request_close(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None:
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        reason_code = request.POST.get("reason_code", "")
        note = request.POST.get("note", "").strip()
        from ham.requests.services import cancel_request

        try:
            cancel_request(ctx, request_id=request_id, reason_code=reason_code, note=note)
        except ImpersonationBlocked:
            messages.error(request, "Closing a request isn't allowed while acting as someone else.")
        except (PermissionDenied, ValueError):
            messages.error(request, "Choose why you're closing this request.")
        else:
            messages.success(request, f"{request_row.display_number} closed")
            return redirect("web:request_detail", request_id=request_id)
        return redirect(
            f"{reverse('web:request_close', args=[request_id])}?reason={reason_code}&note={note}"
        )

    reasons = list(presentation.CANCEL_REASON_LABELS.items())
    if request_row.status != RequestStatus.NEEDS_PHONE_CHECK.value:
        reasons = [
            (code, label)
            for code, label in reasons
            if code != CancelReason.COULDNT_REACH_THEM.value
        ]
    return render(
        request,
        "web/request_close.html",
        {
            "request_row": request_row,
            "reasons": reasons,
            "preselected_reason": request.GET.get("reason", ""),
            "prefilled_note": request.GET.get("note", ""),
            "is_impersonating": ctx.is_impersonating,
        },
    )


# --------------------------------------------------------------------------------------
# L11 ask for more photos sheet
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request_media.reopen")
def request_more_photos(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None:
        return render(request, "web/not_found.html", status=404)

    # `Requester.email` is P (contact-gated); we only need to know "None on file" here, which
    # is not itself a contact detail (matches L11's "no-email request" copy, not a value).
    from ham.requests.models import Requester

    has_email = Requester.objects.filter(request_id=request_id).exclude(email=None).exists()

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        from ham.media.services import reopen_batch

        try:
            reopen_batch(ctx, request_id=request_id, reason=reason)
        except ImpersonationBlocked:
            messages.error(
                request, "Asking for more photos isn't allowed while acting as someone else."
            )
        except (PermissionDenied, ValueError):
            messages.error(request, "Tell us what would help, so we can ask for photos.")
        else:
            messages.success(request, f"Asked {request_row.display_number} for more photos")
            return redirect("web:request_detail", request_id=request_id)
        return redirect("web:request_more_photos", request_id=request_id)

    from ham.rules import RULES

    return render(
        request,
        "web/request_more_photos.html",
        {
            "request_row": request_row,
            "has_email": has_email,
            "is_impersonating": ctx.is_impersonating,
            "max_photos": RULES.media.REQUESTER_MEDIA_BATCH_MAX_PHOTOS,
        },
    )
