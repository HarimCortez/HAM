"""Leadership request screens L1-L11 (intake.md §7; docs/ux/intake.md §6; S2.8).

Every view declares its action via `@requires_action` (route guard, foundation.md §7); the
service layer (`ham.requests.services`/`ham.media.services`) re-checks through the matrix on
every write, so a template-level "don't show the button" is never the only guard (CLAUDE.md).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from django.contrib import messages
from django.http import FileResponse, HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from ham.authz import roles
from ham.authz.commands import ImpersonationBlocked, PermissionDenied
from ham.authz.guard import requires_action
from ham.authz.matrix import authorize
from ham.identity.services import display_names_for
from ham.media.services import get_ready_item, media_gallery_for, open_media_stream
from ham.platform.clock import now as clock_now
from ham.requests import presentation
from ham.requests.models import (
    Approval,
    ApprovalOutcome,
    ApprovalRoute,
    ApprovalStage,
    NeedCategory,
    Reconsideration,
    Requester,
    RequestQuestion,
    UrgencyReview,
)
from ham.requests.queries import (
    can_see_needs_phone_check,
    contact_verifications,
    get_request_by_id,
    get_request_detail,
    is_masked_view,
    list_requests,
    needs_phone_check_list,
    outcome_summary,
    request_history,
)
from ham.requests.queries import can_view_history as queries_can_view_history
from ham.requests.queries_questions import question_thread, waiting_on_requester
from ham.requests.services import reveal_requester_pii
from ham.requests.services_decisions import (
    RECONSIDERATION_NOTE_MAX_CHARS,
    approve_request,
    change_category,
    decide_reconsideration,
    record_decision_phoned,
    record_reconsideration_by_phone,
    reject_request,
    review_urgency,
    undo_decision,
)
from ham.requests.services_questions import (
    ANSWER_MAX_LENGTH,
    QUESTION_MAX_LENGTH,
    ask_question,
    record_phone_answer,
    withdraw_question,
)
from ham.requests.states import (
    CancelReason,
    RequestStatus,
    UrgencyStatus,
    VerificationMethod,
    decision_is_undoable,
    may_decide_reconsideration,
)

_DIR_AD = frozenset({roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR})
_PAS_BRD = frozenset({roles.PASTOR, roles.BOARD_REPRESENTATIVE})

# N7: the fixed set of `requests_list` tab keys (`_tabs_for` below) -- `request_detail`'s
# "Back to Requests" link reflects whatever `?tab=` it was reached with straight back into
# another link's query string, so it's whitelisted against this set rather than passed
# through free-form, even though Django's auto-escaping already blocks attribute breakout.
_KNOWN_LIST_TABS = frozenset(
    {"phone_check", "awaiting", "waiting", "reconsideration", "decided", "all"}
)


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
    # S3.6 (approvals.md A7): "Waiting on requester" and "Reconsideration" are Pastor/Board
    # rep/Director/AD only -- the Administrator's tab set stays "Awaiting approval, Decided,
    # All" (view only), unchanged from step 2.
    if ctx.effective_roles & (_DIR_AD | _PAS_BRD):
        tabs.append(
            {
                "key": "waiting",
                "label": "Waiting on requester",
                "count": len(waiting_on_requester(ctx)),
            }
        )
        tabs.append(
            {
                "key": "reconsideration",
                "label": "Reconsideration",
                "count": len(list_requests(ctx, view="reconsideration")),
            }
        )
    if ctx.effective_roles & (_DIR_AD | _PAS_BRD | {roles.ADMINISTRATOR}):
        tabs.append(
            {
                "key": "decided",
                "label": "Decided",
                "count": len(list_requests(ctx, view="decided")),
            }
        )
    if ctx.effective_roles & (_DIR_AD | {roles.ADMINISTRATOR}):
        tabs.append({"key": "all", "label": "All", "count": len(list_requests(ctx))})
    return tabs


def _rows_for_tab(ctx, tab: str, *, reference_number: int | None, category: str, status: str):
    # Usability M11: the search box and category select apply on every tab, not only "All"
    # -- a Director who types a HAM # or picks a category on "Needs a phone check" or
    # "Awaiting approval" expects it to actually filter, not silently do nothing.
    if tab == "phone_check":
        rows = needs_phone_check_list(ctx)
    elif tab == "awaiting":
        rows = list_requests(
            ctx, status=RequestStatus.AWAITING_APPROVAL.value, reference_number=reference_number
        )
    elif tab == "waiting":
        # S3.6: `waiting_on_requester` returns its own row shape (no status/urgency, per
        # `queries_questions.WaitingOnRequesterRow`) -- re-key against the full, already-scoped
        # `RequestListRow` set so the template only ever handles one row shape, and its own
        # (oldest-question-first) ordering is preserved.
        by_id = {r.id: r for r in list_requests(ctx, reference_number=reference_number)}
        rows = [by_id[w.id] for w in waiting_on_requester(ctx) if w.id in by_id]
    elif tab == "reconsideration":
        rows = list_requests(ctx, view="reconsideration", reference_number=reference_number)
    elif tab == "decided":
        rows = list_requests(ctx, view="decided", reference_number=reference_number)
    else:  # "all"
        rows = list_requests(ctx, status=status or None, reference_number=reference_number)
    if tab == "phone_check" and reference_number is not None:
        rows = [r for r in rows if r.reference_number == reference_number]
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
            "status_icons": presentation.STATUS_ICONS,
            "selected_id": str(selected_detail["detail"].id) if selected_detail else "",
            "selected": selected_detail,
            "filter_count": sum(1 for v in (category, status) if v),
        },
    )


@require_http_methods(["GET"])
@requires_action("request.needs_phone_check.list")
def requests_needs_phone_check(request):
    return requests_list(request, forced_tab="phone_check")


# --------------------------------------------------------------------------------------
# S3.6: the Decision card (docs/ux/approvals.md A1 "Decision panel"; design-system/screens/
# approvals.md C§33). Built straight from the domain models, the same way
# `_build_detail_context` already reaches into `ham.requests.models.Requester` for its own
# has_email check -- `ham.requests.queries`/`queries_questions` are parallel slices' files.
# --------------------------------------------------------------------------------------
def _decision_panel(ctx, request_row, detail, *, has_email: bool) -> dict | None:
    status = request_row.status
    if status not in {
        RequestStatus.AWAITING_APPROVAL.value,
        RequestStatus.APPROVED.value,
        RequestStatus.REJECTED.value,
        RequestStatus.RECONSIDERATION_PENDING.value,
    }:
        return None

    from ham.identity.services import user_holds_global_role

    masked = is_masked_view(ctx)
    impersonating = ctx.is_impersonating
    now = clock_now()
    names_cache: dict = {}

    def name_of(user_id):
        if user_id is None:
            return ""
        if user_id not in names_cache:
            names_cache.update(display_names_for([user_id]))
        return names_cache.get(user_id, "")

    is_pastor = roles.PASTOR in ctx.effective_roles
    is_board = roles.BOARD_REPRESENTATIVE in ctx.effective_roles
    is_dir_ad = bool(ctx.effective_roles & _DIR_AD)

    open_question = (
        RequestQuestion.objects.filter(
            request_id=request_row.id, answered_at__isnull=True, closed_at__isnull=True
        )
        .order_by("asked_at")
        .first()
    )
    question_marker = None
    if open_question is not None and not masked:
        question_marker = {
            "asked_by": name_of(open_question.asked_by_user_id),
            "age": presentation.relative_age(open_question.asked_at, now=now),
        }

    panel: dict = {
        "masked": masked,
        "impersonating": impersonating,
        "can_ask_question": authorize(ctx, "request.question.ask", request_row).allowed,
        "can_change_category": authorize(ctx, "request.category.change", request_row).allowed,
        "question_marker": question_marker,
        "has_email": has_email,
    }

    # -------- AWAITING_APPROVAL --------
    if status == RequestStatus.AWAITING_APPROVAL.value:
        can_approve = authorize(ctx, "request.approve", request_row).allowed
        can_reject = authorize(ctx, "request.reject", request_row).allowed
        can_urgency_review = authorize(ctx, "request.urgency.review", request_row).allowed
        urgent_awaiting_cert = (
            request_row.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value
        )
        panel.update(
            {
                "state": "awaiting",
                "accent": "urgent" if urgent_awaiting_cert else "awaiting",
                "can_approve": can_approve,
                "can_reject": can_reject,
                "can_certify_and_approve": can_approve and is_pastor and urgent_awaiting_cert,
                "can_decline_urgency_link": can_urgency_review and urgent_awaiting_cert,
                "is_pastor_only": is_pastor and not is_board,
                "is_board_only": is_board and not is_pastor,
                "dual_role": is_pastor and is_board,
                "is_dir_ad_awareness": is_dir_ad and not (can_approve or can_reject),
                "urgent_awaiting_cert": urgent_awaiting_cert,
                "board_cant_certify_note": is_board and not is_pastor and urgent_awaiting_cert,
                "waiting_since": request_row.status_changed_at,
            }
        )
        return panel

    # -------- RECONSIDERATION_PENDING --------
    if status == RequestStatus.RECONSIDERATION_PENDING.value:
        try:
            recon = request_row.reconsideration
        except Reconsideration.DoesNotExist:
            recon = None
        authority = None
        if recon is not None:
            original_active = True
            if recon.route == ApprovalRoute.PASTORAL.value:
                original_active = user_holds_global_role(
                    recon.original_decider_user_id, roles.PASTOR
                )
            authority = may_decide_reconsideration(
                recon.route,
                ctx.effective_roles,
                actor_id=str(ctx.user_id) if ctx.user_id else None,
                original_decider_id=str(recon.original_decider_user_id),
                original_decider_is_active_pastor=original_active,
            )
        can_decide = bool(
            authority
            and authority.allowed
            and authorize(ctx, "request.reconsideration.decide", request_row).allowed
        )
        panel.update(
            {
                "state": "reconsideration",
                "accent": "reconsideration",
                "recon": recon,
                "recon_note_masked": masked,
                "original_decider_name": name_of(recon.original_decider_user_id) if recon else "",
                "is_board_route": bool(recon and recon.route == ApprovalRoute.BOARD.value),
                "can_decide": can_decide and not masked and not impersonating,
                "needs_take_over": bool(
                    authority and authority.allowed and authority.took_over_from
                ),
                "take_over_from_name": name_of(uuid.UUID(authority.took_over_from))
                if authority and authority.took_over_from
                else "",
            }
        )
        return panel

    # -------- APPROVED / REJECTED (decided or pending undo) --------
    live_approvals = list(
        Approval.objects.filter(request_id=request_row.id, undone_at__isnull=True).order_by(
            "decided_at"
        )
    )
    latest = live_approvals[-1] if live_approvals else None
    if latest is None:
        return None
    is_decider = bool(ctx.user_id) and ctx.user_id == latest.decided_by_user_id
    pending = (
        is_decider and not masked and decision_is_undoable(latest.decided_at, now, latest.undone_at)
    )
    is_final = status == RequestStatus.REJECTED.value and request_row.closed_at is not None
    urgency_line = ""
    if request_row.urgency_status == UrgencyStatus.CERTIFIED.value:
        urgency_line = "Urgency certified"
    elif request_row.urgency_status == UrgencyStatus.NOT_CERTIFIED.value:
        urgency_line = "Urgency not certified"
    elif request_row.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value:
        urgency_line = "Not yet certified"

    certify_after_approval = (
        status == RequestStatus.APPROVED.value
        and request_row.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value
        and authorize(ctx, "request.urgency.review", request_row).allowed
        and not impersonating
    )

    tell_by_phone = None
    if not has_email and is_dir_ad and not masked:
        if latest.requester_phoned_at is not None:
            tell_by_phone = {
                "told": True,
                "by": name_of(latest.requester_phoned_by_user_id),
                "at": latest.requester_phoned_at,
            }
        else:
            tell_by_phone = {"told": False}

    accent = (
        "pending"
        if pending
        else ("approved" if status == RequestStatus.APPROVED.value else "rejected")
    )
    panel.update(
        {
            "state": "pending" if pending else "decided",
            "accent": accent,
            "outcome": latest.outcome,
            "stage": latest.stage,
            "route": latest.route,
            "decided_by_name": name_of(latest.decided_by_user_id),
            "decided_at": latest.decided_at,
            "board_decided_on": latest.board_decided_on,
            "is_decider": is_decider,
            "pending": pending,
            "undo_deadline": latest.effective_at if pending else None,
            "approval_id": latest.id,
            "message": (
                "" if masked or latest.outcome != ApprovalOutcome.REJECTED.value else latest.reason
            ),
            "approval_note": (
                ""
                if masked or latest.outcome != ApprovalOutcome.APPROVED.value
                else latest.approval_note
            ),
            "urgent_approval": latest.urgent_approval,
            "urgency_line": urgency_line,
            "certify_after_approval": certify_after_approval,
            "is_final": is_final,
            "reconsideration_deadline": (
                request_row.reconsideration_deadline_at
                if not is_final and status == RequestStatus.REJECTED.value
                else None
            ),
            "took_over_from_name": (
                name_of(latest.took_over_from_user_id) if latest.took_over_from_user_id else ""
            ),
            "tell_by_phone": tell_by_phone,
            "can_undo": is_decider and not masked and not impersonating,
            "can_record_reconsideration_phone": (
                status == RequestStatus.REJECTED.value
                and not is_final
                and not pending
                and not masked
                and not impersonating
                and authorize(ctx, "request.reconsideration.record_phone", request_row).allowed
            ),
        }
    )
    return panel


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
    history = request_history(request_row)
    history_names = display_names_for([e.actor_user_id for e in history if e.actor_user_id])

    can_cancel = authorize(ctx, "request.cancel", request_row).allowed
    can_verify_phone = (
        detail.status == RequestStatus.NEEDS_PHONE_CHECK.value
        and authorize(ctx, "request.contact_verify_phone", request_row).allowed
    )
    can_reopen_media = authorize(ctx, "request_media.reopen", request_row).allowed
    # Usability M11 (L11): a no-email request can't be asked for more photos by email -- show
    # the trigger disabled with the reason instead of leading to a dead-end sheet.
    has_email = Requester.objects.filter(request_id=request_id).exclude(email=None).exists()
    # PRD guardian M2/N5: `ham.requests.queries.can_view_history` (not a bare `authorize()`
    # call) -- never true for the Administrator, even while impersonating a role that would
    # otherwise qualify (Q-151), which a plain `authorize()` call can't express on its own.
    can_view_history = queries_can_view_history(ctx)
    # PRD guardian M2 / visual QA M15 / usability M12: the earlier-request panel is gated on
    # the same `request.history.view` action as the History section -- the Administrator
    # (view-only, §9) never holds it, so `matches` stays `[]` and L5 doesn't render for them.
    # Pastors/Board reps hold it but must not see a match that's still stuck in
    # NEEDS_PHONE_CHECK (they can't open it -- "Open" would be a dead end).
    can_view_matches = can_view_history
    matches = outcome_summary(request_row) if can_view_matches else []
    pastor_only = ctx.effective_roles & _PAS_BRD and not (
        ctx.effective_roles & (_DIR_AD | {roles.ADMINISTRATOR})
    )
    if pastor_only:
        matches = [m for m in matches if m.status != RequestStatus.NEEDS_PHONE_CHECK.value]

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
        "status_icon": presentation.status_icon(detail.status),
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
        "hazards": presentation.hazard_labels(detail.known_hazards),
        # UX M4/N-M1: composed at display time only, from the two separate stored fields --
        # never re-derived from a prefixed/mutated string.
        "urgency_line": presentation.urgency_line(
            detail.urgency_reason, detail.urgency_justification
        ),
        "availability_labels": presentation.availability_labels(detail.preferred_availability),
        "can_view_matches": can_view_matches,
        "matches": [
            {
                "request_id": m.request_id,
                "display_number": m.display_number,
                "need_category_label": presentation.need_category_label(m.need_category),
                "submitted_at": m.submitted_at,
                "status_label": presentation.status_label(m.status),
                "status_tone": presentation.status_tone(m.status),
                "cancel_reason_label": presentation.cancel_reason_label(m.cancel_reason_code)
                if m.cancel_reason_code
                else "",
                "reasons": [presentation.match_reason_label(r) for r in m.reasons],
            }
            for m in matches
        ],
        # M14: one "Close this one as a duplicate..." action at the panel's end, preselected
        # with the newest match -- not repeated on every match card.
        "newest_match_id": matches[0].request_id if matches else None,
        "history": [
            {
                "label": e.label,
                "occurred_at": e.occurred_at,
                "actor": history_names.get(e.actor_user_id, "") if e.actor_user_id else "",
                "title": e.title,
            }
            for e in history
        ]
        if can_view_history
        else [],
        "can_view_history": can_view_history,
        "can_cancel": can_cancel,
        "can_verify_phone": can_verify_phone,
        "can_reopen_media": can_reopen_media,
        "has_email": has_email,
        "revealed": revealed,
        "is_director": roles.HAM_DIRECTOR in ctx.effective_roles,
        # S3.6 (docs/ux/approvals.md A1 "Decision panel"): the whole decision state/actions
        # block, built once here so both the standalone page and the split-view pane render
        # the identical thing.
        "decision": _decision_panel(ctx, request_row, detail, has_email=has_email),
        # S3.6 (docs/ux/approvals.md A4/A5/L16 "Questions and answers thread"). Masking
        # (Administrator, Q-124/Q-151) is applied inside `question_thread` itself.
        "questions": [
            {
                "row": q,
                "asked_by": display_names_for([q.asked_by_user_id]).get(q.asked_by_user_id, ""),
            }
            for q in question_thread(ctx, request_id)
        ],
        "can_withdraw_question": authorize(ctx, "request.question.withdraw", request_row).allowed,
        "can_record_phone_answer": authorize(
            ctx, "request.question.record_answer", request_row
        ).allowed,
    }


@require_http_methods(["GET"])
@requires_action("request.view")
@never_cache
def request_detail(request, request_id: uuid.UUID):
    ctx = request.actor
    context = _build_detail_context(ctx, request_id)
    if context is None:
        return render(request, "web/not_found.html", status=404)
    context["standalone"] = True
    context["heading_tag"] = "h2"
    # Usability M11: "Back to Requests" returns to the tab this row came from, instead of the
    # default tab, so a Director triaging "Needs a phone check" doesn't lose their place.
    # N7: whitelisted against the known tab keys -- an unrecognized value is dropped, not
    # reflected back into the link's query string.
    requested_tab = request.GET.get("tab", "")
    context["back_tab"] = requested_tab if requested_tab in _KNOWN_LIST_TABS else ""
    return render(request, "web/request_detail.html", context)


@require_http_methods(["POST"])
@requires_action("request.view")
@never_cache
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
    context["heading_tag"] = "h2"
    return render(request, "web/request_detail.html", context)


# --------------------------------------------------------------------------------------
# L9 phone check sheet
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.contact_verify_phone")
@never_cache
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
def _close_reasons(request_row) -> list[tuple[str, str]]:
    reasons = list(presentation.CANCEL_REASON_LABELS.items())
    if request_row.status != RequestStatus.NEEDS_PHONE_CHECK.value:
        reasons = [
            (code, label)
            for code, label in reasons
            if code != CancelReason.COULDNT_REACH_THEM.value
        ]
    return reasons


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
        # H3 (privacy/security): never put the free-text note in a redirect URL (Location
        # header, access logs, browser history, Referer). Re-render the form directly with
        # the posted values and a 422, the same PRG-avoidance pattern R6 already uses for its
        # own error case.
        return render(
            request,
            "web/request_close.html",
            {
                "request_row": request_row,
                "reasons": _close_reasons(request_row),
                "preselected_reason": reason_code,
                "prefilled_note": note,
                "is_impersonating": ctx.is_impersonating,
            },
            status=422,
        )

    # The L5 "Close this one as a duplicate..." link passes the matched request's id only
    # (never its free text) -- this view resolves the display number itself so nothing a
    # client sends ends up verbatim in the prefilled note.
    prefilled_note = ""
    duplicate_of = request.GET.get("duplicate_of", "")
    if duplicate_of:
        try:
            duplicate_uuid = uuid.UUID(duplicate_of)
        except ValueError:
            duplicate_uuid = None
        if duplicate_uuid is not None:
            duplicate_row = get_request_by_id(ctx, duplicate_uuid)
            if duplicate_row is not None:
                prefilled_note = f"Same as {duplicate_row.display_number}"

    return render(
        request,
        "web/request_close.html",
        {
            "request_row": request_row,
            "reasons": _close_reasons(request_row),
            "preselected_reason": request.GET.get("reason", ""),
            "prefilled_note": prefilled_note,
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


# --------------------------------------------------------------------------------------
# PRD guardian M3 / UX B1: leadership thumb/view routes. Streamed through the app (never a
# client-visible presigned storage URL) with `Cache-Control: no-store`, so nothing about a
# requester's photo ever sits in a shared cache or browser history entry independent of a
# signed-in leader's own session. The Administrator holds `request_media.view` (counts only,
# Q-138) but is excluded here by `is_masked_view` -- the route guard alone isn't enough,
# same reasoning as `_build_detail_context`'s gallery masking.
#
# N1 fix: `get_request_by_id(ctx, request_id)` (the same scoping `list_requests`/the detail
# page use) runs *first* -- a request that isn't in ctx's visible-status scope (e.g. a Pastor
# against a still-NEEDS_PHONE_CHECK request, Q-025 Director/AD-only) 404s here before we ever
# touch storage, exactly like guessing the request id on the detail page would. The bytes are
# then streamed via `FileResponse` (`open_media_stream`), never loaded whole into memory.
# --------------------------------------------------------------------------------------
def _serve_media(
    request, request_id: uuid.UUID, media_id: uuid.UUID, *, variant: Literal["thumb", "view"]
):
    ctx = request.actor
    if is_masked_view(ctx):
        return HttpResponseForbidden()
    if get_request_by_id(ctx, request_id) is None:
        return HttpResponseNotFound()
    item = get_ready_item(request_id=request_id, media_id=media_id)
    if item is None:
        return HttpResponseNotFound()
    result = open_media_stream(item, variant=variant)
    if result is None:
        return HttpResponseNotFound()
    stream, content_type = result
    response = FileResponse(stream, content_type=content_type)
    response["Cache-Control"] = "no-store"
    return response


@require_http_methods(["GET"])
@requires_action("request_media.view")
def request_media_thumb(request, request_id: uuid.UUID, media_id: uuid.UUID):
    return _serve_media(request, request_id, media_id, variant="thumb")


@require_http_methods(["GET"])
@requires_action("request_media.view")
def request_media_view(request, request_id: uuid.UUID, media_id: uuid.UUID):
    return _serve_media(request, request_id, media_id, variant="view")


@require_http_methods(["GET"])
@requires_action("request_media.view")
def request_media_viewer(request, request_id: uuid.UUID, media_id: uuid.UUID):
    """FIX-G UX minor: the installed PWA has no browser chrome, so the raw `/view` route (an
    `<img>`/`<video>` `src`, unchanged below) left a photo/video with no way back. This is a
    minimal HTML page around it -- "<- Back to HAM #NNN" -- that a gallery thumbnail's own
    `<a href>` now points at instead of the raw file (`ham/web/templates/web/
    _request_media_gallery.html`). Same scope (`get_request_by_id`) and masking
    (`is_masked_view`) as `_serve_media`, and the same `Cache-Control: no-store` -- this page
    is just as much a leader-only view of the request as the bytes it embeds."""
    ctx = request.actor
    if is_masked_view(ctx):
        return HttpResponseForbidden()
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None:
        return render(request, "web/not_found.html", status=404)
    item = get_ready_item(request_id=request_id, media_id=media_id)
    if item is None:
        return render(request, "web/not_found.html", status=404)
    context = {
        "request_row": request_row,
        "item": item,
        "view_url": reverse(
            "web:request_media_view", kwargs={"request_id": request_id, "media_id": media_id}
        ),
    }
    response = render(request, "web/request_media_viewer.html", context)
    response["Cache-Control"] = "no-store"
    return response


# ============================================================================================
# S3.6: decision, question and reconsideration sheets (docs/ux/approvals.md A2-A12;
# design-system/screens/approvals.md §2). Every mutating view here delegates to an already
# `@command`-wrapped service in `ham.requests.services_decisions`/`services_questions`, which
# re-checks authorization/state through the matrix and `ham.requests.states` on every call --
# the route-level `@requires_action` below is the fast, template-adjacent guard, never the
# only one (CLAUDE.md).
# ============================================================================================


def _decision_error_redirect(request, request_id: uuid.UUID, *, expected_status: str):
    """A3/A13 "someone decided first": every decision-sheet POST that raises `ValueError`
    lands here. We don't try to distinguish every `Refusal` code from the outside (that's
    `ham.requests.states`'s own job) -- a plain, honest message covers both "someone else
    already recorded a decision while you were looking" (concurrency, the common real case)
    and any other validation refusal, and nothing was changed either way."""
    ctx = request.actor
    current = get_request_by_id(ctx, request_id)
    if current is not None and current.status != expected_status:
        messages.error(
            request,
            "Someone else already decided this request while you were looking. "
            "Nothing was changed.",
        )
    else:
        messages.error(request, "That didn't go through. Nothing was changed. Try again.")
    return redirect("web:request_detail", request_id=request_id)


def _dual_role(ctx) -> bool:
    return bool({roles.PASTOR, roles.BOARD_REPRESENTATIVE} <= ctx.effective_roles)


def _default_route(ctx) -> str:
    if (
        roles.BOARD_REPRESENTATIVE in ctx.effective_roles
        and roles.PASTOR not in ctx.effective_roles
    ):
        return ApprovalRoute.BOARD.value
    return ApprovalRoute.PASTORAL.value


def _route_from_post(request, ctx) -> str:
    posted = request.POST.get("route", "")
    if posted in (ApprovalRoute.PASTORAL.value, ApprovalRoute.BOARD.value):
        return posted
    return _default_route(ctx)


def _board_date_from_post(request) -> dt.date | None:
    raw = request.POST.get("board_decided_on", "").strip()
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


# --------------------------------------------------------------------------------------
# A2 / A2u / A2b: approve
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.approve")
@never_cache
def request_approve(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None:
        return render(request, "web/not_found.html", status=404)
    if request_row.status != RequestStatus.AWAITING_APPROVAL.value:
        # A13 "someone decided first": a stale link/tab (e.g. the other route decided while
        # this sheet was open) gets the same clean alert a failed POST would, not a 404.
        return _decision_error_redirect(
            request, request_id, expected_status=RequestStatus.AWAITING_APPROVAL.value
        )

    urgent_awaiting_cert = request_row.urgency_status == UrgencyStatus.AWAITING_CERTIFICATION.value
    is_pastor = roles.PASTOR in ctx.effective_roles
    urgent_mode = (
        urgent_awaiting_cert and is_pastor and request.GET.get("mode", "urgent") != "normal"
    )
    has_email = Requester.objects.filter(request_id=request_id).exclude(email=None).exists()

    if request.method == "POST":
        route = _route_from_post(request, ctx)
        board_decided_on = (
            _board_date_from_post(request) if route == ApprovalRoute.BOARD.value else None
        )
        certify_urgent = urgent_awaiting_cert and request.POST.get("mode") == "urgent"
        decline_urgency = urgent_awaiting_cert and request.POST.get("mode") == "not_urgent"
        try:
            approve_request(
                ctx,
                request_id=request_id,
                route=route,
                board_decided_on=board_decided_on,
                certify_urgent=certify_urgent,
                decline_urgency=decline_urgency,
                approval_note=request.POST.get("approval_note", "").strip(),
                told_by_phone=request.POST.get("told_by_phone") == "on",
            )
        except (PermissionDenied, ValueError):
            return _decision_error_redirect(
                request, request_id, expected_status=RequestStatus.AWAITING_APPROVAL.value
            )
        messages.success(request, f"Approved · {request_row.display_number}")
        return redirect("web:request_detail", request_id=request_id)

    return render(
        request,
        "web/request_approve.html",
        {
            "request_row": request_row,
            "urgent_mode": urgent_mode,
            "urgent_awaiting_cert": urgent_awaiting_cert,
            "dual_role": _dual_role(ctx),
            "default_route": _default_route(ctx),
            "has_email": has_email,
            "urgency_line": presentation.urgency_line(
                request_row.urgency_reason, request_row.urgency_justification
            ),
        },
    )


# --------------------------------------------------------------------------------------
# A2n: not urgent (standalone urgency review, "Not urgent: leave for normal review")
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.urgency.review")
@never_cache
def request_decline_urgency(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if (
        request_row is None
        or request_row.status != RequestStatus.AWAITING_APPROVAL.value
        or request_row.urgency_status != UrgencyStatus.AWAITING_CERTIFICATION.value
    ):
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        try:
            review_urgency(ctx, request_id=request_id, certify=False)
        except (PermissionDenied, ValueError):
            return _decision_error_redirect(
                request, request_id, expected_status=RequestStatus.AWAITING_APPROVAL.value
            )
        messages.success(request, f"Left for normal review · {request_row.display_number}")
        return redirect("web:request_detail", request_id=request_id)

    return render(request, "web/request_decline_urgency.html", {"request_row": request_row})


# --------------------------------------------------------------------------------------
# A2c: certify as urgent, after an earlier Board approval left it awaiting certification
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.urgency.review")
@never_cache
def request_certify_urgency(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if (
        request_row is None
        or request_row.urgency_status != UrgencyStatus.AWAITING_CERTIFICATION.value
    ):
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        try:
            review_urgency(ctx, request_id=request_id, certify=True)
        except (PermissionDenied, ValueError):
            messages.error(request, "That didn't go through. Try again.")
            return redirect("web:request_detail", request_id=request_id)
        messages.success(request, f"Certified as urgent · {request_row.display_number}")
        return redirect("web:request_detail", request_id=request_id)

    return render(
        request,
        "web/request_certify_urgency.html",
        {
            "request_row": request_row,
            "urgency_line": presentation.urgency_line(
                request_row.urgency_reason, request_row.urgency_justification
            ),
        },
    )


# --------------------------------------------------------------------------------------
# A3: decline (also Board "didn't approve")
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.reject")
@never_cache
def request_reject(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None:
        return render(request, "web/not_found.html", status=404)
    if request_row.status != RequestStatus.AWAITING_APPROVAL.value:
        return _decision_error_redirect(
            request, request_id, expected_status=RequestStatus.AWAITING_APPROVAL.value
        )

    has_email = Requester.objects.filter(request_id=request_id).exclude(email=None).exists()

    if request.method == "POST":
        route = _route_from_post(request, ctx)
        board_decided_on = (
            _board_date_from_post(request) if route == ApprovalRoute.BOARD.value else None
        )
        reason_code = request.POST.get("reason_code", "")
        message = request.POST.get("message", "").strip()
        if not reason_code or not message:
            messages.error(
                request, "Choose why HAM can't help, and write what we'll tell the requester."
            )
        else:
            try:
                reject_request(
                    ctx,
                    request_id=request_id,
                    route=route,
                    reason_code=reason_code,
                    message=message,
                    board_decided_on=board_decided_on,
                    told_by_phone=request.POST.get("told_by_phone") == "on",
                )
            except (PermissionDenied, ValueError):
                return _decision_error_redirect(
                    request, request_id, expected_status=RequestStatus.AWAITING_APPROVAL.value
                )
            messages.success(request, f"Declined · {request_row.display_number}")
            return redirect("web:request_detail", request_id=request_id)
        return render(
            request,
            "web/request_reject.html",
            {
                "request_row": request_row,
                "has_email": has_email,
                "dual_role": _dual_role(ctx),
                "default_route": _default_route(ctx),
                "reason_choices": presentation.REJECTION_REASON_LABELS.items(),
                "prefills": presentation.REJECTION_REASON_PREFILLS,
                "selected_reason": reason_code,
                "message": message,
                "max_chars": presentation.DECLINE_MESSAGE_MAX_CHARS,
            },
            status=422,
        )

    return render(
        request,
        "web/request_reject.html",
        {
            "request_row": request_row,
            "has_email": has_email,
            "dual_role": _dual_role(ctx),
            "default_route": _default_route(ctx),
            "reason_choices": presentation.REJECTION_REASON_LABELS.items(),
            "prefills": presentation.REJECTION_REASON_PREFILLS,
            "selected_reason": "",
            "message": "",
            "max_chars": presentation.DECLINE_MESSAGE_MAX_CHARS,
        },
    )


# --------------------------------------------------------------------------------------
# U1: undo (decider only, inside the window)
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.decision.undo")
@never_cache
def request_decision_undo(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None:
        return render(request, "web/not_found.html", status=404)

    approval_id_raw = request.GET.get("approval_id") or request.POST.get("approval_id")
    review_id_raw = request.GET.get("review_id") or request.POST.get("review_id")
    approval = None
    review = None
    try:
        if approval_id_raw:
            approval = Approval.objects.get(pk=approval_id_raw, request_id=request_id)
        elif review_id_raw:
            review = UrgencyReview.objects.get(pk=review_id_raw, request_id=request_id)
    except (Approval.DoesNotExist, UrgencyReview.DoesNotExist, ValueError, TypeError):
        return render(request, "web/not_found.html", status=404)
    if approval is None and review is None:
        return render(request, "web/not_found.html", status=404)

    record = approval or review
    assert record is not None
    now = clock_now()
    window_open = decision_is_undoable(record.decided_at, now, record.undone_at)

    if request.method == "POST":
        try:
            if approval is not None:
                undo_decision(ctx, approval_id=approval.id)
            else:
                assert review is not None
                undo_decision(ctx, review_id=review.id)
        except (PermissionDenied, ValueError):
            messages.error(
                request,
                "The time to undo has passed, or it's already been undone. The decision stands.",
            )
            return redirect("web:request_detail", request_id=request_id)
        messages.success(request, f"Undone · {request_row.display_number}")
        return redirect("web:request_detail", request_id=request_id)

    return render(
        request,
        "web/request_decision_undo.html",
        {
            "request_row": request_row,
            "window_open": window_open,
            "undo_deadline": record.effective_at,
            "is_urgency_review": review is not None,
            "urgent_approval": bool(approval and approval.urgent_approval),
            "approval_id": approval.id if approval else "",
            "review_id": review.id if review else "",
        },
    )


# --------------------------------------------------------------------------------------
# A9: reconsideration decision (with take-over, Q-157)
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.reconsideration.decide")
@never_cache
def request_reconsideration_decide(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None:
        return render(request, "web/not_found.html", status=404)
    if request_row.status != RequestStatus.RECONSIDERATION_PENDING.value:
        return _decision_error_redirect(
            request, request_id, expected_status=RequestStatus.RECONSIDERATION_PENDING.value
        )
    try:
        recon = request_row.reconsideration
    except Reconsideration.DoesNotExist:
        return render(request, "web/not_found.html", status=404)

    is_board_route = recon.route == ApprovalRoute.BOARD.value
    original_active = True
    if not is_board_route:
        from ham.identity.services import user_holds_global_role

        original_active = user_holds_global_role(recon.original_decider_user_id, roles.PASTOR)
    is_original = str(ctx.user_id) == str(recon.original_decider_user_id)
    # Q-157: if the original pastor no longer holds an active Pastor role, every pastor may
    # decide it without the take-over tick (still recorded as a take-over by the service).
    needs_take_over = not is_board_route and not is_original and original_active

    approve_mode = request.GET.get("outcome", "approve") != "decline"

    if request.method == "POST":
        approve_mode = request.POST.get("outcome", "approve") != "decline"
        take_over = request.POST.get("take_over") == "on"
        reason = request.POST.get("reason", "").strip()
        reason_code = request.POST.get("reason_code", "")
        if approve_mode:
            ok = bool(reason)
            if not ok:
                messages.error(
                    request, "Add a short reason. Every reconsideration decision needs one."
                )
        else:
            ok = bool(reason_code) and bool(reason)
            if not ok:
                messages.error(
                    request, "Choose why HAM can't help, and write what we'll tell the requester."
                )
        if needs_take_over and not take_over:
            ok = False
            messages.error(request, "Tick to confirm the original decider isn't available.")
        if ok:
            try:
                decide_reconsideration(
                    ctx,
                    request_id=request_id,
                    approve=approve_mode,
                    reason=reason,
                    reason_code=reason_code if not approve_mode else "",
                    take_over=take_over,
                )
            except (PermissionDenied, ValueError):
                return _decision_error_redirect(
                    request,
                    request_id,
                    expected_status=RequestStatus.RECONSIDERATION_PENDING.value,
                )
            messages.success(request, f"Recorded · {request_row.display_number}")
            return redirect("web:request_detail", request_id=request_id)

    return render(
        request,
        "web/request_reconsideration_decide.html",
        {
            "request_row": request_row,
            "recon": recon,
            "is_board_route": is_board_route,
            "needs_take_over": needs_take_over,
            "original_decider_name": display_names_for([recon.original_decider_user_id]).get(
                recon.original_decider_user_id, ""
            ),
            "approve_mode": approve_mode,
            "reason_choices": presentation.REJECTION_REASON_LABELS.items(),
            "prefills": presentation.REJECTION_REASON_PREFILLS,
            "board_decided_on_default": clock_now().date(),
        },
    )


# --------------------------------------------------------------------------------------
# A12: record a reconsideration request by phone (Director, AD; Q-159)
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.reconsideration.record_phone")
@never_cache
def request_reconsideration_phone(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if (
        request_row is None
        or request_row.status != RequestStatus.REJECTED.value
        or request_row.closed_at is not None
    ):
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        note = request.POST.get("note", "").strip()
        confirmed = request.POST.get("confirmed") == "on"
        if not confirmed:
            messages.error(request, "Tick to confirm the requester asked by phone to reconsider.")
        elif len(note) > RECONSIDERATION_NOTE_MAX_CHARS:
            messages.error(request, "That note is too long.")
        else:
            try:
                record_reconsideration_by_phone(ctx, request_id=request_id, note=note)
            except (PermissionDenied, ValueError):
                messages.error(request, "That didn't go through. Try again.")
            else:
                messages.success(request, f"Recorded · {request_row.display_number}")
                return redirect("web:request_detail", request_id=request_id)

    return render(
        request,
        "web/request_reconsideration_phone.html",
        {"request_row": request_row, "max_chars": RECONSIDERATION_NOTE_MAX_CHARS},
    )


# --------------------------------------------------------------------------------------
# A11: tell by phone ("Call to share a decision"; Director, AD)
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.decision.record_phoned")
@never_cache
def request_decision_phoned(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None:
        return render(request, "web/not_found.html", status=404)
    approval = (
        Approval.objects.filter(
            request_id=request_id, stage=ApprovalStage.INITIAL.value, undone_at__isnull=True
        )
        .order_by("-decided_at")
        .first()
    )
    if approval is None:
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        confirmed = request.POST.get("confirmed") == "on"
        if not confirmed:
            messages.error(request, "Tick to confirm you told the requester by phone.")
        else:
            try:
                record_decision_phoned(ctx, request_id=request_id)
            except (PermissionDenied, ValueError):
                messages.error(request, "That's already been recorded, or didn't go through.")
            else:
                messages.success(request, f"Marked as told · {request_row.display_number}")
                return redirect("web:request_detail", request_id=request_id)

    try:
        revealed = reveal_requester_pii(ctx, request_id=request_id, surface="tell_by_phone")
    except PermissionDenied:
        revealed = None

    return render(
        request,
        "web/request_decision_phoned.html",
        {
            "request_row": request_row,
            "approval": approval,
            "revealed": revealed,
            "message": (
                approval.reason if approval.outcome == ApprovalOutcome.REJECTED.value else ""
            ),
            "reconsideration_deadline": request_row.reconsideration_deadline_at,
        },
    )


# --------------------------------------------------------------------------------------
# A4: ask a question (incl. no-email "call and record" variant)
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.question.ask")
@never_cache
def request_question_ask(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if (
        request_row is None
        or request_row.closed_at is not None
        or request_row.status == RequestStatus.NEEDS_PHONE_CHECK.value
    ):
        return render(request, "web/not_found.html", status=404)
    has_email = Requester.objects.filter(request_id=request_id).exclude(email=None).exists()
    open_question = (
        RequestQuestion.objects.filter(
            request_id=request_id, answered_at__isnull=True, closed_at__isnull=True
        )
        .order_by("asked_at")
        .first()
    )

    if request.method == "POST":
        question_text = request.POST.get("question", "").strip()
        phone_answer = request.POST.get("phone_answer", "").strip() if not has_email else ""
        phone_confirmed = request.POST.get("phone_confirmed") == "on"
        if not question_text:
            messages.error(request, "Write your question.")
        elif len(question_text) > QUESTION_MAX_LENGTH:
            messages.error(request, "That question is too long.")
        elif not has_email and phone_answer and not phone_confirmed:
            messages.error(request, "Tick to confirm you spoke with the requester by phone.")
        else:
            try:
                ask_question(
                    ctx, request_id=request_id, question=question_text, phone_answer=phone_answer
                )
            except (PermissionDenied, ValueError) as exc:
                messages.error(request, str(exc) or "That didn't go through. Try again.")
            else:
                messages.success(request, f"Question sent · {request_row.display_number}")
                return redirect("web:request_detail", request_id=request_id)

    try:
        revealed = reveal_requester_pii(ctx, request_id=request_id, surface="ask_question")
    except PermissionDenied:
        revealed = None

    return render(
        request,
        "web/request_question_ask.html",
        {
            "request_row": request_row,
            "has_email": has_email,
            "open_question": open_question,
            "revealed": revealed if not has_email else None,
            "max_chars": QUESTION_MAX_LENGTH,
            "answer_max_chars": ANSWER_MAX_LENGTH,
        },
    )


# --------------------------------------------------------------------------------------
# A5: record their answer (phone)
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.question.record_answer")
@never_cache
def request_question_record_answer(request, request_id: uuid.UUID, question_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    question = RequestQuestion.objects.filter(pk=question_id, request_id=request_id).first()
    if request_row is None or question is None:
        return render(request, "web/not_found.html", status=404)
    if question.answered_at is not None or question.closed_at is not None:
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        answer = request.POST.get("answer", "").strip()
        confirmed = request.POST.get("confirmed") == "on"
        if not answer:
            messages.error(request, "Write what they said.")
        elif len(answer) > ANSWER_MAX_LENGTH:
            messages.error(request, "That answer is too long.")
        elif not confirmed:
            messages.error(request, "Tick to confirm you spoke with the requester by phone.")
        else:
            try:
                record_phone_answer(ctx, question_id=question_id, answer=answer)
            except (PermissionDenied, ValueError):
                messages.error(request, "That didn't go through. Try again.")
            else:
                messages.success(request, f"Answer saved · {request_row.display_number}")
                return redirect("web:request_detail", request_id=request_id)

    try:
        revealed = reveal_requester_pii(ctx, request_id=request_id, surface="record_answer")
    except PermissionDenied:
        revealed = None

    return render(
        request,
        "web/request_question_record_answer.html",
        {
            "request_row": request_row,
            "question": question,
            "revealed": revealed,
            "asked_by": display_names_for([question.asked_by_user_id]).get(
                question.asked_by_user_id, ""
            ),
            "max_chars": ANSWER_MAX_LENGTH,
        },
    )


# --------------------------------------------------------------------------------------
# Withdraw a question (asker, Director, AD)
# --------------------------------------------------------------------------------------
@require_http_methods(["POST"])
@requires_action("request.question.withdraw")
def request_question_withdraw(request, request_id: uuid.UUID, question_id: uuid.UUID):
    ctx = request.actor
    question = RequestQuestion.objects.filter(pk=question_id, request_id=request_id).first()
    if question is None:
        return render(request, "web/not_found.html", status=404)
    try:
        withdraw_question(ctx, question_id=question_id)
    except (PermissionDenied, ValueError):
        messages.error(request, "That didn't go through. Try again.")
    else:
        messages.success(request, "Question withdrawn")
    return redirect("web:request_detail", request_id=request_id)


# --------------------------------------------------------------------------------------
# A6: change category (Director, AD; Q-109)
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@requires_action("request.category.change")
@never_cache
def request_category_change(request, request_id: uuid.UUID):
    ctx = request.actor
    request_row = get_request_by_id(ctx, request_id)
    if request_row is None or request_row.closed_at is not None:
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        need_category = request.POST.get("need_category", "")
        try:
            change_category(ctx, request_id=request_id, need_category=need_category)
        except ImpersonationBlocked:
            messages.error(request, "That didn't go through. Try again.")
        except (PermissionDenied, ValueError):
            messages.error(request, "Choose a different category to save.")
        else:
            messages.success(request, f"Category changed · {request_row.display_number}")
            return redirect("web:request_detail", request_id=request_id)

    return render(
        request,
        "web/request_category_change.html",
        {
            "request_row": request_row,
            "category_choices": NeedCategory.choices,
        },
    )
