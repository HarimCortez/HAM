"""Public requester screens R1-R12 (docs/ux/intake.md; PRD-GAP-free implementation notes are
inline). No `ActorContext`/sign-in is involved anywhere in this module (PRD §7 "requesters
have no account"): every screen here is a `PUBLIC_ROUTES` entry (`ham/authz/guard.py`), and
per-request access control is the token/draft itself, exactly like `ham.web.auth_views`'s own
sign-in-link family. Consequential actions still go through `ham.requester_portal`/
`ham.requests`/`ham.media`'s own `@command`-wrapped services, which authorize the
`RequesterContext` themselves (`ham.authz.matrix`'s `Scope.OWN_REQUEST`).

URL/module note for S2.8 (leadership screens, a different worktree): this module and
`ham/web/urls_requester.py` are the only files this slice (S2.7) adds new routes to inside
`ham/web/`; `ham/web/urls_requests.py`/`urls_inbox.py` are untouched here.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from ham.authz.commands import PermissionDenied
from ham.authz.context import RequesterContext
from ham.media import services as media_services
from ham.platform import net
from ham.platform.church import church_profile
from ham.requester_portal import (
    antiabuse,
    cookies,
    drafts,
    forms,
    projection,
    services,
    verification,
)
from ham.requester_portal.choices import (
    AVAILABILITY_AFTERNOONS,
    AVAILABILITY_ANY_TIME,
    AVAILABILITY_MORNINGS,
    CONTACT_PREFERENCE_LABELS,
    HAZARD_LABELS,
    NEED_CATEGORY_LABELS,
    PROPERTY_TYPE_LABELS,
    URGENCY_REASON_LABELS,
    WEEKDAY_LABELS,
    ContactPreference,
    Hazard,
    NeedCategory,
    PropertyType,
    UrgencyReason,
)
from ham.requester_portal.models import RequesterVerificationChallenge
from ham.requests.certifications import RelationshipToProperty, statement_text_for
from ham.requests.queries import get_request_for_requester
from ham.rules import RULES

# --------------------------------------------------------------------------------------
# Wizard step order and per-step field ownership (for filtering R6's whole-payload
# validation down to the fields *this* step actually collects, docs/ux/intake.md R2-R6
# "error on Continue -> error summary ... focused").
# --------------------------------------------------------------------------------------
STEP_NEED = "need"
STEP_HOME = "home"
STEP_SAFETY = "safety"
STEP_REACHING_YOU = "reaching-you"
STEP_REVIEW = "review"

STEP_ORDER = [STEP_NEED, STEP_HOME, STEP_SAFETY, STEP_REACHING_YOU, STEP_REVIEW]

_STEP_FIELDS: dict[str, set[str]] = {
    STEP_NEED: {
        "need_category",
        "description",
        "urgent_requested",
        "urgency_reason",
        "urgency_justification",
    },
    STEP_HOME: {
        "relationship_to_property",
        "owner_name",
        "line1",
        "line2",
        "city",
        "state",
        "postal_code",
        "property_type",
    },
    STEP_SAFETY: {"hazards", "hazard_note"},
    STEP_REACHING_YOU: {
        "full_name",
        "phone",
        "email",
        "no_email",
        "contact_preference",
        "availability",
        "contact_note",
    },
    STEP_REVIEW: {"attested_statements"},
}

# FIX-D (visual M9): the >=1280 wizard "Good to know" aside (design-system/screens/intake.md
# S§1.2) for each step. R6 has none by design (its form card spans the aside column instead,
# see r6_review.html's `public-card--review` modifier), so it's absent from this map on
# purpose, not an oversight.
_STEP_ASIDE: dict[str, tuple[str, list[str]]] = {
    STEP_NEED: ("Good to know", ["Big or small, tell us. There's no job too small to ask about."]),
    STEP_HOME: (
        "Good to know",
        ["Filling this in for someone else? Answer for them — we'll contact you about it."],
    ),
    STEP_SAFETY: (
        "Why we ask",
        ["This keeps everyone safe, including you. It won't stop us from helping."],
    ),
    STEP_REACHING_YOU: (
        "Good to know",
        ["We'll only use this to reach you about this request and to arrange a visit."],
    ),
}

_STEP_LABELS: dict[str, str] = {
    STEP_NEED: "Your need",
    STEP_HOME: "The home",
    STEP_SAFETY: "Safety at the home",
    STEP_REACHING_YOU: "Reaching you",
    STEP_REVIEW: "Please confirm",
}


def _field_step(field: str) -> str:
    for step, fields in _STEP_FIELDS.items():
        if field in fields:
            return step
    return STEP_REVIEW


def _review_errors(errors: dict[str, str]) -> list[dict[str, str]]:
    """Usability M9: R6's error summary can't link to `#id_<field>` -- the field isn't on the
    review page -- so each error links to its owning step's Edit URL instead, with the step
    name in the message ("Street address is missing · Fix in The home")."""
    out = []
    for field, message in errors.items():
        step = _field_step(field)
        if step == STEP_REVIEW:
            url = "#id_attested_statements"
        else:
            url = reverse("web:request_help_step", kwargs={"step": step})
        out.append({"message": f"{message} · Fix in {_STEP_LABELS[step]}", "url": url})
    return out


_SESSION_INTAKE_SOURCE = "ham_intake_source_code"
_SESSION_VERIFY = "ham_intake_verify"
_SESSION_R7N = "ham_intake_r7n"
_SESSION_FORM_OPENED_AT = "ham_intake_form_opened_at"


def _client_ip(request: HttpRequest) -> str:
    return net.client_ip(request)


def _draft_id(request: HttpRequest) -> UUID | None:
    return cookies.read_resume_draft_id(request)


def _step_index(step: str) -> int:
    return STEP_ORDER.index(step) + 1


def _weekday_choices(church) -> list[tuple[str, str]]:
    return [(str(d), WEEKDAY_LABELS[d]) for d in sorted(church.serves_days)]


def _availability_labels(church) -> dict[str, str]:
    """M1: R6's own label map for `payload.availability` (day numbers + time words), same
    codes `_weekday_choices` already offers as R5's chips."""
    labels = {str(d): WEEKDAY_LABELS[d] for d in church.serves_days}
    labels[AVAILABILITY_ANY_TIME] = "Any time works"
    labels[AVAILABILITY_MORNINGS] = "Mornings"
    labels[AVAILABILITY_AFTERNOONS] = "Afternoons"
    return labels


def _payload_or_empty(draft_id: UUID | None) -> dict:
    """Server-side prefill for the person's *own*, already-cookie-scoped draft, continuing
    the form at the step they stopped on (docs/ux/intake.md "Continue restores every answer
    at the step where the person stopped") -- a different, later, in-scope caller than the
    two `ham.requester_portal.drafts.load_payload` docstring names explicitly (`save_step`/
    `submit_and_issue_link`); this one only ever renders back to the same requester who owns
    this signed cookie, never to an unrelated response (Q-139's actual concern, which is the
    R1 *resume prompt* showing no details -- see `request_help_start` below, which does not
    call this)."""
    if draft_id is None:
        return {}
    return drafts.load_payload(draft_id) or {}


def _errors_for_step(errors: dict[str, str], step: str) -> dict[str, str]:
    fields = _STEP_FIELDS[step]
    return {k: v for k, v in errors.items() if k in fields}


def _base_context(request: HttpRequest) -> dict[str, Any]:
    return {"church": church_profile()}


# --------------------------------------------------------------------------------------
# R1: Ask for help (start)
# --------------------------------------------------------------------------------------
@require_http_methods(["GET"])
def request_help_start(request: HttpRequest) -> HttpResponse:
    code = request.GET.get("c", "").strip().upper()[:6]
    if code:
        request.session[_SESSION_INTAKE_SOURCE] = code

    draft_id = _draft_id(request)
    has_resume = draft_id is not None and drafts.draft_exists_and_live(draft_id)
    context = _base_context(request)
    context["has_resume"] = has_resume
    context["aside_heading"] = "What happens after you ask"
    context["aside_body"] = projection.STATUS_NEXT_STEPS["SUBMITTED"]
    return render(request, "web/requester/r1_start.html", context)


@require_http_methods(["POST"])
def request_help_begin(request: HttpRequest) -> HttpResponse:
    """R1 "Start" (a fresh form) or "Continue my request" (an existing draft already lives in
    this browser's cookie -- nothing to create)."""
    draft_id = _draft_id(request)
    if draft_id is not None and drafts.draft_exists_and_live(draft_id):
        request.session.setdefault(_SESSION_FORM_OPENED_AT, antiabuse.sign_form_opened_at())
        return redirect("web:request_help_step", step=STEP_NEED)

    result = drafts.start_draft(ip_address=_client_ip(request))
    if result.status == "rate_limited" or result.draft is None:
        messages.error(
            request,
            "We can't start a new request from this connection right now. Please try again "
            "in a little while, or call us.",
        )
        return redirect("web:request_help_start")

    # Q-121/§9 anti-abuse: the minimum-fill-time clock starts when the *whole form* is
    # started, not just the review step -- a bot that speed-runs every step still trips it.
    request.session[_SESSION_FORM_OPENED_AT] = antiabuse.sign_form_opened_at()
    response = redirect("web:request_help_step", step=STEP_NEED)
    cookies.set_resume_cookie(response, draft_id=result.draft.id)
    return response


@require_http_methods(["POST"])
def request_help_start_over(request: HttpRequest) -> HttpResponse:
    """Confirmed "Start over": the old draft simply stops being referenced (its cookie is
    cleared); it still self-erases after `INTAKE_DRAFT_LIFETIME` like any other abandoned
    draft (Q-127) -- there is no delete endpoint, by design (append-only rows, purged by
    `ham.requester_portal.jobs.purge_expired_drafts`)."""
    response = redirect("web:request_help_start")
    cookies.clear_resume_cookie(response)
    return response


# --------------------------------------------------------------------------------------
# R2-R6: the wizard steps
# --------------------------------------------------------------------------------------
def _need_data(request: HttpRequest, payload: dict) -> dict:
    """UX M4/N-M1: `urgency_reason` (a code) and `urgency_justification` (the requester's own
    words) are stored as two separate draft keys, exactly as typed/chosen -- never composed
    or prefixed here. The old behavior (`f"{label}. {justification}"`, re-run on every
    re-save) silently rewrote the requester's own text and duplicated the label each time the
    form was edited and re-submitted; composing "Reason label. Their words" now happens only
    at display time (`ham.requests.presentation.urgency_line`, L2)."""
    return {
        "need_category": request.POST.get("need_category", "").strip(),
        "description": request.POST.get("description", "").strip(),
        "urgent_requested": bool(request.POST.get("urgent_requested")),
        "urgency_justification": request.POST.get("urgency_justification", "").strip(),
        "urgency_reason": request.POST.get("urgency_reason", "").strip(),
    }


def _home_data(request: HttpRequest) -> dict:
    return {
        "relationship_to_property": request.POST.get("relationship_to_property", "").strip(),
        "owner_name": request.POST.get("owner_name", "").strip(),
        "line1": request.POST.get("line1", "").strip(),
        "line2": request.POST.get("line2", "").strip(),
        "city": request.POST.get("city", "").strip(),
        "state": request.POST.get("state", "").strip(),
        "postal_code": request.POST.get("postal_code", "").strip(),
        "property_type": request.POST.get("property_type", "").strip(),
    }


def _safety_data(request: HttpRequest) -> dict:
    return {
        "hazards": request.POST.getlist("hazards"),
        "hazard_note": request.POST.get("hazard_note", "").strip(),
    }


def _reaching_you_data(request: HttpRequest) -> dict:
    no_email = bool(request.POST.get("no_email"))
    return {
        "full_name": request.POST.get("full_name", "").strip(),
        "phone": request.POST.get("phone", "").strip(),
        "email": "" if no_email else request.POST.get("email", "").strip(),
        "no_email": no_email,
        "contact_preference": request.POST.get("contact_preference", "").strip(),
        "availability": request.POST.getlist("availability"),
        "note": request.POST.get("note", "").strip(),
    }


_STEP_DATA_FN = {
    STEP_HOME: _home_data,
    STEP_SAFETY: _safety_data,
    STEP_REACHING_YOU: _reaching_you_data,
}


def _step_template(step: str) -> str:
    return {
        STEP_NEED: "web/requester/r2_need.html",
        STEP_HOME: "web/requester/r3_home.html",
        STEP_SAFETY: "web/requester/r4_safety.html",
        STEP_REACHING_YOU: "web/requester/r5_reaching_you.html",
        STEP_REVIEW: "web/requester/r6_review.html",
    }[step]


def _next_step(step: str) -> str:
    idx = STEP_ORDER.index(step)
    return STEP_ORDER[idx + 1]


def _prev_step(step: str) -> str | None:
    idx = STEP_ORDER.index(step)
    return STEP_ORDER[idx - 1] if idx > 0 else None


@require_http_methods(["GET", "POST"])
def request_help_step(request: HttpRequest, step: str) -> HttpResponse:
    if step not in STEP_ORDER:
        return render(request, "web/not_found.html", status=404)

    draft_id = _draft_id(request)
    if draft_id is None or not drafts.draft_exists_and_live(draft_id):
        messages.info(request, "Let's start your request again. Your answers weren't saved yet.")
        return redirect("web:request_help_start")

    if step == STEP_REVIEW:
        return _review_step(request, draft_id)

    if request.method == "POST":
        data_fn = _STEP_DATA_FN.get(step)
        step_data = _need_data(request, {}) if step == STEP_NEED else data_fn(request)  # type: ignore[misc]
        merged = {**_payload_or_empty(draft_id), **step_data}
        church = church_profile()
        _cleaned, all_errors = forms.validate_intake_payload(merged, church=church)
        step_errors = _errors_for_step(all_errors, step)
        drafts.save_step(draft_id, step_data, email=step_data.get("email") or None)
        if step_errors:
            context = _step_context(request, step, merged, step_errors)
            return render(request, _step_template(step), context, status=422)
        return redirect("web:request_help_step", step=_next_step(step))

    payload = _payload_or_empty(draft_id)
    if step == STEP_HOME and not payload.get("state"):
        # Q-147: prefill R3's state from the church's own state ("Florida · Change") --
        # never stored into the draft itself, only shown as the default; the person can still
        # change it (e.g. helping someone in a different state).
        church_state = church_profile().state
        if church_state:
            payload = {**payload, "state": church_state}
    context = _step_context(request, step, payload, {})
    return render(request, _step_template(step), context)


def _step_context(
    request: HttpRequest, step: str, payload: dict, errors: dict[str, str]
) -> dict[str, Any]:
    church = church_profile()
    context = _base_context(request)
    context.update(
        {
            "step": step,
            "step_number": _step_index(step),
            "step_count": len(STEP_ORDER),
            "prev_step": _prev_step(step),
            "payload": payload,
            "errors": errors,
            "need_category_choices": list(NeedCategory),
            "need_category_labels": NEED_CATEGORY_LABELS,
            "urgency_reason_choices": list(UrgencyReason),
            "urgency_reason_labels": URGENCY_REASON_LABELS,
            "relationship_choices": list(RelationshipToProperty),
            "property_type_choices": list(PropertyType),
            "property_type_labels": PROPERTY_TYPE_LABELS,
            "hazard_choices": [h for h in Hazard if h != Hazard.NONE_KNOWN],
            "hazard_labels": HAZARD_LABELS,
            "contact_preference_choices": list(ContactPreference),
            "contact_preference_labels": CONTACT_PREFERENCE_LABELS,
            "weekday_choices": _weekday_choices(church),
            "availability_any_time": AVAILABILITY_ANY_TIME,
            "availability_mornings": AVAILABILITY_MORNINGS,
            "availability_afternoons": AVAILABILITY_AFTERNOONS,
            "availability_labels": _availability_labels(church),
        }
    )
    aside = _STEP_ASIDE.get(step)
    if aside is not None:
        context["aside_heading"], context["aside_body"] = aside
    return context


def _review_step(request: HttpRequest, draft_id: UUID) -> HttpResponse:
    church = church_profile()
    payload = _payload_or_empty(draft_id)

    if request.method == "POST":
        attested = request.POST.getlist("attested_statements")
        step_data = {"attested_statements": attested}
        merged = {**payload, **step_data}
        cleaned, errors = forms.validate_intake_payload(merged, church=church)
        drafts.save_step(draft_id, step_data)
        if cleaned is None:
            step_errors = errors  # every field may be wrong by the time Send is pressed
            context = _step_context(request, STEP_REVIEW, merged, step_errors)
            context["review"] = _review_summary(merged, church)
            context["review_errors"] = _review_errors(step_errors)
            return render(request, _step_template(STEP_REVIEW), context, status=422)

        source_code = request.session.get(_SESSION_INTAKE_SOURCE, "")
        if source_code and not cleaned.get("intake_source_code"):
            drafts.save_step(draft_id, {"intake_source_code": source_code})

        bot = antiabuse.honeypot_tripped(
            request.POST.get(antiabuse.HONEYPOT_FIELD_NAME)
        ) or not antiabuse.min_fill_time_ok(request.session.get(_SESSION_FORM_OPENED_AT))

        if cleaned["no_email"]:
            if bot:
                # Anti-abuse: show the normal "saved" confirmation but write nothing further.
                return render(request, "web/requester/r7n_saved.html", _base_context(request))
            try:
                result = services.submit_and_issue_link(draft_id=draft_id, verification_id=None)
            except services.IntakeSubmissionRateLimited:
                # Q-146: same shape as the honeypot trip above -- show the normal-looking
                # "saved" confirmation, write nothing further, never reveal that a cap exists.
                return render(request, "web/requester/r7n_saved.html", _base_context(request))
            response = redirect("web:request_help_saved")
            cookies.clear_resume_cookie(response)
            request.session[_SESSION_R7N] = {
                "display_number": result.request.display_number,
                "phone": cleaned["phone"],
                "urgent": bool(cleaned["urgent_requested"]),
                "full_name": (cleaned["full_name"] or "").split(" ")[0],
            }
            return response

        email = cleaned["email"] or ""
        if not bot:
            # H2: the result is deliberately unused -- identical UI regardless of "sent",
            # "cooldown" or "rate_limited" (see the docstring note further down).
            verification.request_intake_verification(
                draft_id=draft_id, email=email, ip_address=_client_ip(request)
            )

        request.session[_SESSION_VERIFY] = {
            "purpose": RequesterVerificationChallenge.PURPOSE_INTAKE,
            "email": email,
            "draft_id": str(draft_id),
        }
        # H2: identical UI for "sent", "cooldown" and "rate_limited" -- showing a distinct
        # "too many codes" message here would let someone probe whether an address already
        # has an outstanding request/cap history. `challenge_result.status` is deliberately
        # not branched on; every case lands on the same R8 screen with no flash message.
        return redirect("web:request_help_verify")

    request.session.setdefault(_SESSION_FORM_OPENED_AT, antiabuse.sign_form_opened_at())
    context = _step_context(request, STEP_REVIEW, payload, {})
    context["review"] = _review_summary(payload, church)
    context["honeypot_field"] = antiabuse.HONEYPOT_FIELD_NAME
    return render(request, _step_template(STEP_REVIEW), context)


def _review_summary(payload: dict, church) -> dict[str, Any]:
    relationship_raw = payload.get("relationship_to_property", "")
    try:
        relationship = RelationshipToProperty(relationship_raw)
    except ValueError:
        relationship = None
    need_category_raw = payload.get("need_category", "")
    try:
        need_category_label = NEED_CATEGORY_LABELS[NeedCategory(need_category_raw)]
    except ValueError:
        need_category_label = ""
    return {
        "need_category_label": need_category_label,
        "relationship": relationship,
        "no_email": bool(payload.get("no_email")),
        # B1: R6 renders the certification tick-box wording from the one canonical module
        # (`ham.requests.certifications`) instead of the template hard-coding its own copy —
        # `statement_text` maps each required code (in order: authority tick, then the shared
        # responsibility tick) to its exact wording.
        "statement_text": statement_text_for(relationship) if relationship is not None else {},
    }


# --------------------------------------------------------------------------------------
# R8: Check your email (code entry) -- both purposes share one session-driven view.
# --------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def request_help_verify(request: HttpRequest) -> HttpResponse:
    pending = request.session.get(_SESSION_VERIFY)
    if not pending:
        return redirect("web:request_help_start")

    purpose = pending["purpose"]
    email = pending["email"]
    minutes = int(RULES.intake.REQUESTER_CODE_LIFETIME.total_seconds() // 60)

    if request.method == "POST":
        if request.POST.get("resend"):
            if purpose == RequesterVerificationChallenge.PURPOSE_INTAKE:
                verification.request_intake_verification(
                    draft_id=UUID(pending["draft_id"]), email=email, ip_address=_client_ip(request)
                )
            else:
                request_id = _pending_link_regen_request_id(request)
                if request_id is None:
                    # L8: a stale/missing session key is a normal "start over" case, not a
                    # crash -- `assert` here used to turn it into a 500.
                    return redirect("web:request_help_start")
                services.request_link_regeneration_code(
                    request_id=request_id, email=email, ip_address=_client_ip(request)
                )
            # H2: identical UI for "sent", "cooldown" and "rate_limited" (see the other
            # `request_intake_verification` call site above for the full reasoning) -- a
            # single, always-true message ("if we can resend, it's on its way") rather than
            # branching on the result's status.
            messages.success(request, "If we can send another, it's on its way.")
            return redirect("web:request_help_verify")

        code = request.POST.get("code", "")
        # L6: the lockout budget is scoped per-draft (or per-request, for link regeneration)
        # plus IP, never by the bare email address -- otherwise anyone could lock a real
        # person's address out of intake for a day just by guessing wrong codes against
        # drafts *they* control with the victim's email typed in.
        is_intake = purpose == RequesterVerificationChallenge.PURPOSE_INTAKE
        draft_id = UUID(pending["draft_id"]) if is_intake else None
        request_id = None if draft_id is not None else _pending_link_regen_request_id(request)
        verify_result = verification.verify_code(
            purpose=purpose,
            email=email,
            code=code,
            draft_id=draft_id,
            request_id=request_id,
            ip_address=_client_ip(request),
        )
        if not verify_result.ok or verify_result.challenge is None:
            # M8: "no_challenge" for an intake draft that already became a real request (this
            # exact browser's own session -- it holds `pending["draft_id"]`, proof enough) is
            # not a generic error; show what actually happened instead of an invitation to
            # duplicate the request.
            if (
                verify_result.reason == "no_challenge"
                and purpose == RequesterVerificationChallenge.PURPOSE_INTAKE
            ):
                already_request_id = drafts.consumed_request_id(draft_id) if draft_id else None
                if already_request_id is not None:
                    context = {
                        **_base_context(request),
                        "purpose": purpose,
                        **_already_received_context(already_request_id, reveal=True),
                    }
                    return render(request, "web/requester/r8_verify.html", context)
            return render(
                request,
                "web/requester/r8_verify.html",
                {
                    **_base_context(request),
                    "email": projection.mask_email(email)
                    if purpose != RequesterVerificationChallenge.PURPOSE_INTAKE
                    else email,
                    "minutes": minutes,
                    "error": _verify_error_message(verify_result),
                    "purpose": purpose,
                },
                status=422,
            )
        return _after_verified(request, purpose=purpose, challenge=verify_result.challenge)

    return render(
        request,
        "web/requester/r8_verify.html",
        {
            **_base_context(request),
            "email": projection.mask_email(email)
            if purpose != RequesterVerificationChallenge.PURPOSE_INTAKE
            else email,
            "minutes": minutes,
            "purpose": purpose,
        },
    )


def _verify_error_message(result: verification.VerifyResult) -> str:
    if result.reason == "expired":
        return "That code has expired. Your answers are still saved. Send a new code below."
    if result.reason == "locked":
        return (
            "That code was entered incorrectly a few times, so we turned it off. Send a new "
            "code below, or call us."
        )
    if result.reason == "wrong":
        return f"That code doesn't match. {result.attempts_left} tries left."
    # M8: never invite a duplicate submission -- a recovery that keeps the draft, not "start
    # again". (When this "no_challenge" case is actually an already-submitted draft, the
    # caller renders the dedicated already-received view instead of this message at all.)
    return "We couldn't find a pending code for this email. Send a new code below, or call us."


def _already_received_context(request_id: UUID, *, reveal: bool) -> dict[str, Any]:
    """M8: "confirming a code/link after the draft was already submitted" (another device, a
    reused link) must never look like a dead end that invites a duplicate request, but must
    also never leak which request that draft became to a browser that hasn't itself proven
    anything (a bare, already-used link is not proof -- anyone could have the URL text).

    ``reveal=True`` only when the *caller* has already established that this exact browser
    holds a valid session/link for this draft/request right now (it just typed a code in its
    own session, or its own link-consume POST just succeeded) -- shows the HAM # and a button
    straight to the secure page. ``reveal=False`` shows a neutral message with no HAM # and no
    link at all, for a bare already-used-link GET/POST that proves nothing new."""
    if not reveal:
        return {"already_received": True, "display_number": "", "secure_url": None}
    row = get_request_for_requester(request_id)
    return {
        "already_received": True,
        "display_number": row.display_number if row is not None else "",
        "secure_url": services.current_secure_page_path(request_id),
    }


def _welcome_url(token: str) -> str:
    return reverse("web:request_help_secure_page", kwargs={"token": token}) + "?welcome=1"


def _after_verified(
    request: HttpRequest, *, purpose: str, challenge: RequesterVerificationChallenge
) -> HttpResponse:
    request.session.pop(_SESSION_VERIFY, None)
    if purpose == RequesterVerificationChallenge.PURPOSE_INTAKE:
        # H1: use the *challenge's own* `draft_id`, never the browser's resume cookie -- the
        # cookie could (in principle, or after a stale/forged value) point at a different
        # draft than the one the emailed code was actually sent for; the challenge row is the
        # one thing that's tied to a specific draft at code-send time.
        draft_id = challenge.draft_id
        if draft_id is None:
            return redirect("web:request_help_start")
        try:
            result = services.submit_and_issue_link(
                draft_id=draft_id, verification_id=challenge.id, verification_method="email_code"
            )
        except (ValueError, services.IntakeSubmissionRateLimited):
            # M8: this browser's code just verified correctly (real proof of session), but
            # the draft turned out to already be a request -- e.g. another device's link
            # click won the race a moment earlier. Show what actually happened, with a way to
            # open the secure page, instead of "answers have expired, start again" (which
            # invites a duplicate submission).
            already_request_id = drafts.consumed_request_id(draft_id)
            if already_request_id is not None:
                context = {
                    **_base_context(request),
                    "purpose": RequesterVerificationChallenge.PURPOSE_INTAKE,
                    **_already_received_context(already_request_id, reveal=True),
                }
                return render(request, "web/requester/r8_verify.html", context)
            messages.error(request, "Your answers have expired. Please start again.")
            return redirect("web:request_help_start")
        assert result.issued_link is not None
        response = redirect(_welcome_url(result.issued_link.token))
        cookies.clear_resume_cookie(response)
        return response

    request_id = _pending_link_regen_request_id(request)
    # N3: the challenge's *own* request_id, never blindly trust the session's, must be the
    # one this link gets regenerated for -- same H1 reasoning as the intake path above (a
    # session value could point at a different request than the one the emailed code was
    # actually sent for).
    if request_id is None or challenge.request_id != request_id:
        return redirect("web:request_help_start")
    ctx = RequesterContext(request_id=challenge.request_id)
    issued = services.regenerate_link_for_own_request(
        ctx, verification_id=challenge.id, verification_method="email_code"
    )
    request.session.pop("ham_intake_link_regen_request_id", None)
    return redirect("web:request_help_secure_page", token=issued.token)


def _pending_link_regen_request_id(request: HttpRequest) -> UUID | None:
    raw = request.session.get("ham_intake_link_regen_request_id")
    return UUID(raw) if raw else None


# --------------------------------------------------------------------------------------
# The two emailed, scanner-safe links (intake-contracts.md §8.2 exact paths).
# --------------------------------------------------------------------------------------
def _already_received_for_link_token(token: str) -> UUID | None:
    """M8: if this link token belonged to an intake draft that already became a request
    (whether or not *this* attempt to use the token succeeds), returns that request's id;
    `None` for a token that never maps to an already-submitted draft (a truly unknown/
    not-yet-used token)."""
    challenge = verification.challenge_for_link_token(token)
    if challenge is None or challenge.draft_id is None:
        return None
    return drafts.consumed_request_id(challenge.draft_id)


@require_http_methods(["GET", "POST"])
def request_help_verify_link(request: HttpRequest, token: str) -> HttpResponse:
    if request.method == "GET":
        valid = verification.link_is_valid(token=token)
        context = {**_base_context(request), "token": token, "valid": valid, "kind": "intake"}
        if not valid:
            # M8: a GET proves nothing about who's asking -- never reveal the HAM # or a
            # direct link here (see `_already_received_context`'s `reveal=False` docstring).
            already_request_id = _already_received_for_link_token(token)
            if already_request_id is not None:
                context.update(_already_received_context(already_request_id, reveal=False))
        return render(request, "web/requester/confirm_link.html", context)

    result = verification.consume_link(token=token)
    if not result.ok or result.challenge is None:
        context = {**_base_context(request), "token": token, "valid": False, "kind": "intake"}
        already_request_id = _already_received_for_link_token(token)
        if already_request_id is not None:
            context.update(_already_received_context(already_request_id, reveal=False))
        return render(request, "web/requester/confirm_link.html", context)
    challenge = result.challenge
    if challenge.draft_id is None:
        return render(request, "web/not_found.html", status=404)
    try:
        submission = services.submit_and_issue_link(
            draft_id=challenge.draft_id,
            verification_id=challenge.id,
            verification_method="email_link",
        )
    except (ValueError, services.IntakeSubmissionRateLimited):
        # M8: this link token itself was just freshly, successfully consumed (real proof of
        # inbox access) -- the draft turned out to already be a request via a different,
        # earlier-consumed challenge. Reveal the HAM # and a way in, same as `_after_verified`.
        already_request_id = drafts.consumed_request_id(challenge.draft_id)
        context = {**_base_context(request), "token": token, "valid": False, "kind": "intake"}
        if already_request_id is not None:
            context.update(_already_received_context(already_request_id, reveal=True))
        return render(request, "web/requester/confirm_link.html", context)
    request.session.pop(_SESSION_VERIFY, None)
    assert submission.issued_link is not None
    response = redirect(_welcome_url(submission.issued_link.token))
    cookies.clear_resume_cookie(response)
    return response


@require_http_methods(["GET", "POST"])
def request_help_new_link(request: HttpRequest, token: str) -> HttpResponse:
    if request.method == "GET":
        valid = verification.link_is_valid(token=token)
        return render(
            request,
            "web/requester/confirm_link.html",
            {**_base_context(request), "token": token, "valid": valid, "kind": "new_link"},
        )

    result = verification.consume_link(token=token)
    if not result.ok or result.challenge is None or result.challenge.request_id is None:
        return render(
            request,
            "web/requester/confirm_link.html",
            {**_base_context(request), "token": token, "valid": False, "kind": "new_link"},
        )
    challenge = result.challenge
    ctx = RequesterContext(request_id=challenge.request_id)
    try:
        issued = services.regenerate_link_for_own_request(
            ctx, verification_id=challenge.id, verification_method="email_link"
        )
    except PermissionDenied:
        return render(request, "web/not_found.html", status=404)
    return redirect("web:request_help_secure_page", token=issued.token)


# --------------------------------------------------------------------------------------
# R7N: Request saved (no email, Q-025)
# --------------------------------------------------------------------------------------
@require_http_methods(["GET"])
def request_help_saved(request: HttpRequest) -> HttpResponse:
    info = request.session.pop(_SESSION_R7N, None)
    if not info:
        return redirect("web:request_help_start")
    context = _base_context(request)
    context.update(info)
    return render(request, "web/requester/r7n_saved.html", context)


# --------------------------------------------------------------------------------------
# R10 (and R7 in "welcome" mode): the secure request page.
# --------------------------------------------------------------------------------------
@require_http_methods(["GET"])
@never_cache
def request_help_secure_page(request: HttpRequest, token: str) -> HttpResponse:
    ctx = services.resolve_token(token)
    if ctx is None or ctx.request_id is None:
        owner = services.link_owner_contact(token=token)
        if owner is None:
            return render(request, "web/requester/r12_not_available.html", _base_context(request))
        request_id, email_on_file = owner
        context = _base_context(request)
        context.update(
            {
                "token": token,
                "masked_email": projection.mask_email(email_on_file),
                "has_email": bool(email_on_file),
            }
        )
        return render(request, "web/requester/r11a_link_expired.html", context)

    row = get_request_for_requester(ctx.request_id)
    if row is None:
        return render(request, "web/requester/r12_not_available.html", _base_context(request))

    church = church_profile()
    # `RequesterContext` is duck-type-compatible with `ActorContext` for `.effective_roles`
    # (intake-contracts.md §1) but is not a nominal subtype, hence the ignore.
    gallery = media_services.media_gallery_for(ctx, ctx.request_id)  # type: ignore[arg-type]
    # PRD guardian N11: the secure page used to ignore whether uploads are currently open and
    # why a leader asked for more (the batch's own reason, L11) -- both are needed so R9's
    # "add photos" affordance and any "we asked for more photos because..." copy can be
    # accurate instead of always assuming uploads are open.
    batch = media_services.current_batch_view(ctx.request_id)
    masked = projection.masked_contact(
        email=row.email,
        phone=row.phone,
        line1=row.line1,
        city=row.city,
        postal_code=row.postal_code,
    )
    status_chip_tuple = projection.REQUESTER_STATUS_CHIPS.get(row.status)
    context = _base_context(request)
    context.update(
        {
            "welcome": request.GET.get("welcome") == "1",
            "row": row,
            "token": token,
            # M6: greet by first name only, never the full name; "Thank you." with no comma
            # when there's nothing sensible to put after it (an empty/blank full name).
            "first_name": (row.full_name or "").split(" ")[0] or "",
            "status_sentence": projection.status_wording(
                row.status, cancel_reason=row.cancel_reason_code or None
            ),
            "status_chip": {
                "label": status_chip_tuple[0],
                "tone": status_chip_tuple[1],
                "icon": status_chip_tuple[2],
            }
            if status_chip_tuple
            else {"label": row.status, "tone": "neutral", "icon": "circle-help"},
            "next_steps": projection.STATUS_NEXT_STEPS.get(row.status, []),
            "offers_new_request": projection.cancel_reason_offers_new_request(
                row.cancel_reason_code or None
            ),
            "masked": masked,
            "need_category_label": NEED_CATEGORY_LABELS.get(row.need_category, row.need_category),
            "property_type_label": PROPERTY_TYPE_LABELS.get(row.property_type, row.property_type),
            "hazards": _hazards_display(row.known_hazards),
            "availability": _availability_display(row.preferred_availability),
            "photo_count": gallery.counts.photos,
            "video_count": gallery.counts.videos,
            "can_add_photos": row.status not in {"CANCELLED"} and (batch is None or batch.is_open),
            "batch_open": batch is None or batch.is_open,
            "batch_reopen_reason": batch.reason
            if batch and batch.is_open and batch.kind == "reopened"
            else "",
            "church": church,
        }
    )
    return render(request, "web/requester/r10_secure_page.html", context)


def _hazards_display(stored: str) -> str:
    """`row.known_hazards` is the raw comma-joined codes (plus an optional free-text note in
    parentheses) `services._payload_from_cleaned` stored; show each recognized code's plain
    label, and leave anything this module doesn't recognize (the free-text note) as-is.

    Delegates to `ham.requests.presentation.hazard_labels` (M1) instead of its own
    comma-then-parenthesis parsing, which broke when the note itself contained a comma
    (usability M1's fix note) -- `ham.web` sits above `ham.requests` in the layer order so
    this import is fine, unlike the reverse."""
    from ham.requests.presentation import hazard_labels as _hazard_labels

    parts = []
    for h in _hazard_labels(stored):
        if h["label"]:
            parts.append(f"{h['label']} ({h['note']})" if h["note"] else h["label"])
        elif h["note"]:
            parts.append(h["note"])
    return ", ".join(parts)


def _availability_display(stored: str) -> str:
    from ham.requests.presentation import availability_labels as _availability_labels_fn

    return ", ".join(_availability_labels_fn(stored))


# --------------------------------------------------------------------------------------
# R9: Add photos and videos
# --------------------------------------------------------------------------------------
@require_http_methods(["GET"])
def request_help_photos(request: HttpRequest, token: str) -> HttpResponse:
    ctx = services.resolve_token(token)
    if ctx is None or ctx.request_id is None:
        return render(request, "web/requester/r12_not_available.html", _base_context(request))
    context = _base_context(request)
    context.update(
        {
            "token": token,
            "max_photos": RULES.media.REQUESTER_MEDIA_BATCH_MAX_PHOTOS,
            "max_videos": RULES.media.REQUESTER_MEDIA_BATCH_MAX_VIDEOS,
            "max_video_seconds": int(
                RULES.media.REQUESTER_MEDIA_MAX_VIDEO_DURATION.total_seconds()
            ),
            "photo_types": ",".join(RULES.media.REQUESTER_PHOTO_TYPES),
            "video_types": ",".join(RULES.media.REQUESTER_VIDEO_TYPES),
            "reserve_url": reverse("web:request_help_media_reserve", kwargs={"token": token}),
            "secure_page_url": reverse("web:request_help_secure_page", kwargs={"token": token}),
            "aside_heading": "Good to know",
            "aside_body": [
                "Only the people handling your request will see these.",
                "You can add more later if you need to.",
            ],
        }
    )
    return render(request, "web/requester/r9_photos.html", context)


@require_http_methods(["POST"])
def request_help_media_reserve(request: HttpRequest, token: str) -> HttpResponse:
    """JSON endpoint the TS upload module calls (`frontend/src/upload.ts`): reserves one
    presigned-PUT slot per requested file (`ham.media.services.reserve_uploads`)."""
    ctx = services.resolve_token(token)
    if ctx is None or ctx.request_id is None:
        return HttpResponse(status=404)
    try:
        body = json.loads(request.body or b"{}")
        intents = [
            media_services.UploadIntent(
                media_kind=i["media_kind"],
                content_type=i["content_type"],
                declared_bytes=int(i["declared_bytes"]),
            )
            for i in body.get("files", [])
        ]
    except (KeyError, ValueError, TypeError):
        return HttpResponse(
            json.dumps({"error": "bad request"}), status=400, content_type="application/json"
        )

    try:
        reserved = media_services.reserve_uploads(ctx, intents=intents)
    except media_services.MediaValidationError as exc:
        return HttpResponse(
            json.dumps({"error": str(exc)}), status=422, content_type="application/json"
        )
    except (PermissionDenied, ValueError) as exc:
        return HttpResponse(
            json.dumps({"error": str(exc)}), status=409, content_type="application/json"
        )

    # `reserve_uploads` returns one `ReservedUpload` per intent, in the same order (S2.4b
    # `ham.media.services.reserve_uploads` docstring) -- zip back to each intent's own
    # `content_type` so the browser's PUT sends exactly the header the presigned URL was
    # signed for (`PresignedUpload` carries no headers of its own, S2.4a/S2.4b).
    payload = {
        "files": [
            {
                "item_id": str(r.item_id),
                "media_kind": r.media_kind,
                "put_url": r.upload.url,
                "content_type": intent.content_type,
                "complete_url": reverse(
                    "web:request_help_media_complete",
                    kwargs={"token": token, "item_id": r.item_id},
                ),
            }
            for r, intent in zip(reserved, intents, strict=True)
        ]
    }
    return HttpResponse(json.dumps(payload), content_type="application/json")


@require_http_methods(["POST"])
def request_help_media_complete(request: HttpRequest, token: str, item_id: UUID) -> HttpResponse:
    ctx = services.resolve_token(token)
    if ctx is None or ctx.request_id is None:
        return HttpResponse(status=404)
    try:
        item = media_services.complete_upload(ctx, item_id=item_id)
    except (PermissionDenied, ValueError) as exc:
        return HttpResponse(
            json.dumps({"error": str(exc)}), status=409, content_type="application/json"
        )
    return HttpResponse(
        json.dumps({"status": item.status}),
        content_type="application/json",  # type: ignore[union-attr]
    )


@require_http_methods(["POST"])
def request_help_media_remove(request: HttpRequest, token: str, item_id: UUID) -> HttpResponse:
    ctx = services.resolve_token(token)
    if ctx is None or ctx.request_id is None:
        return HttpResponse(status=404)
    try:
        media_services.remove_item(ctx, item_id=item_id)
    except (PermissionDenied, ValueError) as exc:
        return HttpResponse(
            json.dumps({"error": str(exc)}), status=409, content_type="application/json"
        )
    return HttpResponse(json.dumps({"ok": True}), content_type="application/json")


# --------------------------------------------------------------------------------------
# R11b / R11: link expired "send me a code", Check on your request, R12
# --------------------------------------------------------------------------------------
@require_http_methods(["POST"])
def request_help_link_expired_send(request: HttpRequest, token: str) -> HttpResponse:
    owner = services.link_owner_contact(token=token)
    if owner is None:
        return render(request, "web/requester/r12_not_available.html", _base_context(request))
    request_id, email_on_file = owner
    context = _base_context(request)
    if email_on_file is None:
        context["masked_email"] = ""
        context["has_email"] = False
        context["token"] = token
        return render(request, "web/requester/r11a_link_expired.html", context)

    # H2: identical UI regardless of `result.status` -- see `request_help_step`'s R6 send.
    services.regenerate_link(token=token, email=email_on_file, ip_address=_client_ip(request))
    request.session[_SESSION_VERIFY] = {
        "purpose": RequesterVerificationChallenge.PURPOSE_LINK_REGENERATION,
        "email": email_on_file,
    }
    request.session["ham_intake_link_regen_request_id"] = str(request_id)
    # H2: identical UI regardless of `result.status` (see `request_help_step`'s R6 send for
    # the full reasoning) -- no distinguishing message here either.
    return redirect("web:request_help_verify")


@require_http_methods(["GET", "POST"])
def request_help_find(request: HttpRequest) -> HttpResponse:
    context = _base_context(request)
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        services.find_my_request(email=email, ip_address=_client_ip(request))
        context["submitted_email"] = email
        return render(request, "web/requester/r11b_find_request.html", context)
    return render(request, "web/requester/r11b_find_request.html", context)
