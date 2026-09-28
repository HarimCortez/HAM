"""Sign-in, two-step sign-in, step-up, sign-out and impersonation screens (foundation.md §7,
docs/ux/auth-and-access.md §4 A/C/D/I). Views only adapt HTTP <-> `ham.identity` services; no
domain rule lives here (CLAUDE.md "Keep domain rules out of controllers/handlers").
"""

from __future__ import annotations

import uuid
from typing import cast

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as django_logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from ham.authz.context import SESSION_KEY_MFA_SATISFIED, SESSION_KEY_STEP_UP, ActorContext
from ham.authz.guard import requires_action
from ham.identity import authn, mfa
from ham.identity.models import User
from ham.identity.web import handle_command_errors, safe_next_url
from ham.platform.clock import now as clock_now
from ham.rules import RULES


def actor_of(request: HttpRequest) -> ActorContext:
    """`request.actor` (set by `ham.identity.middleware.ActorContextMiddleware`) typed for
    mypy, which doesn't know about this dynamically-attached attribute (see that module's
    `# type: ignore[attr-defined]` on the assignment side)."""
    return cast(ActorContext, request.actor)  # type: ignore[attr-defined]


SESSION_PENDING_MFA_USER_ID = "ham_pending_mfa_user_id"
SESSION_PENDING_NEXT = "ham_pending_next"
SESSION_MFA_ATTEMPTS = "ham_mfa_attempts"
SESSION_ENROLL_SECRET = "ham_totp_enroll_secret"


# ---------------------------------------------------------------------------------------
# A1/A2: email -> code+link
# ---------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def sign_in(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect(safe_next_url(request))

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        next_url = safe_next_url(request)
        if not email or "@" not in email:
            return render(
                request, "web/auth/sign_in.html", {"error": "Enter a full email address."}
            )
        result = authn.request_sign_in(email=email, next_url=next_url)
        request.session["ham_sign_in_email"] = email
        if result.status == "rate_limited":
            return render(
                request,
                "web/auth/sign_in_rate_limited.html",
                {"retry_at": result.retry_at},
            )
        return redirect(reverse("web:sign_in_code"))
    return render(request, "web/auth/sign_in.html", {})


@require_http_methods(["GET", "POST"])
def sign_in_code(request: HttpRequest) -> HttpResponse:
    email = request.session.get("ham_sign_in_email", "")
    if not email:
        return redirect(reverse("web:sign_in"))

    if request.method == "POST":
        if request.POST.get("resend"):
            authn.request_sign_in(email=email, next_url=request.session.get("ham_pending_next", ""))
            messages.success(request, "Sent again. Use the newest email.")
            return redirect(reverse("web:sign_in_code"))

        code = request.POST.get("code", "")
        result = authn.verify_code(email=email, code=code)
        if not result.ok:
            return render(
                request,
                "web/auth/sign_in_code.html",
                {"email": email, "error": _code_error_message(result)},
            )
        return _after_email_verified(request, email=email, next_url=result.next_url)

    minutes = int(RULES.auth.SIGN_IN_CODE_LIFETIME.total_seconds() // 60)
    return render(request, "web/auth/sign_in_code.html", {"email": email, "minutes": minutes})


def _code_error_message(result: authn.VerifyResult) -> str:
    if result.reason == "expired":
        return "That code has expired. Request a new one below."
    if result.reason == "locked":
        return (
            "That code was entered incorrectly a few times, so we turned it off to protect "
            "your account. Request a new code below."
        )
    if result.reason == "wrong":
        return f"That code doesn't match the one we sent. {result.attempts_left} tries left."
    return "We couldn't find a pending sign-in for this email. Request a new one below."


@require_http_methods(["GET", "POST"])
def sign_in_link(request: HttpRequest, token: str) -> HttpResponse:
    if request.method == "GET":
        # GET only *checks* validity; it never consumes the link (a link must survive a
        # mail-scanner's GET prefetch, docs/ux/auth-and-access.md A "no typing").
        valid = authn.link_is_valid(token=token)
        return render(request, "web/auth/sign_in_link.html", {"token": token, "valid": valid})

    result = authn.consume_link(token=token)
    if not result.ok:
        return render(
            request,
            "web/auth/sign_in_link.html",
            {"token": token, "valid": False, "consumed": True},
        )
    return _after_email_verified(request, email=result.email, next_url=result.next_url)


def _after_email_verified(request: HttpRequest, *, email: str, next_url: str) -> HttpResponse:
    request.session.pop("ham_sign_in_email", None)
    user = User.objects.filter(email=email).first()
    if user is None or not user.is_active or user.is_disabled:
        return render(request, "web/auth/sign_in_no_account.html", {})

    if not mfa.mfa_required(user):
        authn.complete_sign_in(request, user=user)
        return redirect(next_url or reverse("web:home"))

    trusted_cookie = request.COOKIES.get(mfa.TRUSTED_DEVICE_COOKIE_NAME, "")
    if mfa.is_enrolled(user) and trusted_cookie and mfa.check_trusted_device(user, trusted_cookie):
        authn.complete_sign_in(request, user=user)
        request.session[SESSION_KEY_MFA_SATISFIED] = True
        return redirect(next_url or reverse("web:home"))

    request.session[SESSION_PENDING_MFA_USER_ID] = str(user.id)
    request.session[SESSION_PENDING_NEXT] = next_url
    request.session[SESSION_MFA_ATTEMPTS] = 0
    if mfa.is_enrolled(user):
        return redirect(reverse("web:sign_in_mfa"))
    return redirect(reverse("web:mfa_setup"))


# ---------------------------------------------------------------------------------------
# C4 / E1-E2: authenticator challenge (and recovery code)
# ---------------------------------------------------------------------------------------
def _pending_mfa_user(request: HttpRequest) -> User | None:
    raw = request.session.get(SESSION_PENDING_MFA_USER_ID)
    if not raw:
        return None
    return User.objects.filter(pk=raw, is_active=True, disabled_at__isnull=True).first()


def _restart_sign_in(request: HttpRequest) -> HttpResponse:
    for key in (SESSION_PENDING_MFA_USER_ID, SESSION_PENDING_NEXT, SESSION_MFA_ATTEMPTS):
        request.session.pop(key, None)
    messages.error(request, "For your safety, please start again from your email (PRD-GAP Q-072).")
    return redirect(reverse("web:sign_in"))


@require_http_methods(["GET", "POST"])
def sign_in_mfa(request: HttpRequest) -> HttpResponse:
    user = _pending_mfa_user(request)
    if user is None:
        return redirect(reverse("web:sign_in"))

    if request.method == "POST":
        code = request.POST.get("code", "")
        use_recovery = bool(request.POST.get("use_recovery"))
        ok = (
            mfa.verify_recovery_code(user, code) is not None
            if use_recovery
            else mfa.verify_totp(user, code)
        )
        if not ok:
            attempts = request.session.get(SESSION_MFA_ATTEMPTS, 0) + 1
            request.session[SESSION_MFA_ATTEMPTS] = attempts
            if attempts >= mfa.MFA_CODE_MAX_ATTEMPTS:
                return _restart_sign_in(request)
            return render(
                request,
                "web/auth/sign_in_mfa.html",
                {
                    "error": "That code didn't match. Try the current one.",
                    "use_recovery": use_recovery,
                },
            )

        next_url = request.session.pop(SESSION_PENDING_NEXT, "") or reverse("web:home")
        request.session.pop(SESSION_PENDING_MFA_USER_ID, None)
        request.session.pop(SESSION_MFA_ATTEMPTS, None)
        authn.complete_sign_in(request, user=user)
        request.session[SESSION_KEY_MFA_SATISFIED] = True
        response = redirect(next_url)
        if request.POST.get("trust_device"):
            _set_trusted_device_cookie(response, user)
        return response

    use_recovery = bool(request.GET.get("recovery"))
    return render(request, "web/auth/sign_in_mfa.html", {"use_recovery": use_recovery})


def _set_trusted_device_cookie(response: HttpResponse, user: User) -> None:
    cookie_value, expires_at = mfa.create_trusted_device(user)
    response.set_cookie(
        mfa.TRUSTED_DEVICE_COOKIE_NAME,
        cookie_value,
        expires=expires_at,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )


# ---------------------------------------------------------------------------------------
# C1-C3: enrollment wizard
# ---------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def mfa_setup(request: HttpRequest) -> HttpResponse:
    # Reachable two ways: mid-sign-in (pending user, not yet fully logged in) or later, by an
    # already-signed-in person who still hasn't enrolled (Q-045: they kept non-MFA access).
    pending_user = _pending_mfa_user(request)
    user = pending_user or (request.user if request.user.is_authenticated else None)
    if user is None:
        return redirect(reverse("web:sign_in"))
    if mfa.is_enrolled(user) and pending_user is None:
        return redirect(reverse("web:me_security"))

    if request.method == "POST":
        step = request.POST.get("step")
        if step == "connect":
            secret = request.session.get(SESSION_ENROLL_SECRET, "")
            code = request.POST.get("code", "")
            try:
                codes = mfa.confirm_enrollment(user, secret=secret, code=code)
            except ValueError as exc:
                enrollment = mfa.EnrollmentStart(
                    secret=secret,
                    provisioning_uri=mfa.totp.provisioning_uri(
                        secret=secret, email=user.email, issuer="HAM"
                    ),
                    qr_svg="",
                )
                return render(
                    request,
                    "web/auth/mfa_setup_connect.html",
                    {"enrollment": enrollment, "error": str(exc)},
                )
            request.session.pop(SESSION_ENROLL_SECRET, None)
            request.session["ham_recovery_codes_once"] = codes
            return redirect(reverse("web:mfa_setup_codes"))
        return redirect(reverse("web:mfa_setup"))

    enrollment = mfa.start_enrollment(user)
    request.session[SESSION_ENROLL_SECRET] = enrollment.secret
    return render(request, "web/auth/mfa_setup_connect.html", {"enrollment": enrollment})


@require_http_methods(["GET", "POST"])
def mfa_setup_codes(request: HttpRequest) -> HttpResponse:
    codes = request.session.get("ham_recovery_codes_once")
    if not codes:
        return redirect(reverse("web:mfa_setup"))
    if request.method == "POST":
        request.session.pop("ham_recovery_codes_once", None)
        pending_user = _pending_mfa_user(request)
        if pending_user is not None:
            next_url = request.session.pop(SESSION_PENDING_NEXT, "") or reverse("web:home")
            request.session.pop(SESSION_PENDING_MFA_USER_ID, None)
            authn.complete_sign_in(request, user=pending_user)
            request.session[SESSION_KEY_MFA_SATISFIED] = True
            return redirect(next_url)
        # Already-signed-in person completing enrollment later (Q-045): mark satisfied now.
        request.session[SESSION_KEY_MFA_SATISFIED] = True
        return redirect(reverse("web:me_security"))
    return render(request, "web/auth/mfa_setup_codes.html", {"codes": codes})


# ---------------------------------------------------------------------------------------
# D: step-up
# ---------------------------------------------------------------------------------------
_STEP_UP_ACTION_LABELS: dict[str, str] = {
    "role_change": "changing someone's roles",
    "audit_export": "exporting the audit log",
    "mfa_reset": "resetting someone's two-step sign-in",
    "impersonation_start": "troubleshooting as someone else",
    "recovery_codes_regenerate": "making new recovery codes",
    "sign_in_email_change": "changing your sign-in email",
}


@require_http_methods(["GET", "POST"])
@requires_action("shell.use")
def step_up(request: HttpRequest) -> HttpResponse:
    next_url = safe_next_url(request)
    kind = request.GET.get("kind") or request.POST.get("kind") or ""
    label = _STEP_UP_ACTION_LABELS.get(kind, "confirming it's you")

    if request.method == "POST":
        code = request.POST.get("code", "")
        ok = mfa.verify_step_up(actor_of(request), code=code)
        if not ok:
            return render(
                request,
                "web/auth/step_up.html",
                {
                    "error": "That code didn't match.",
                    "kind": kind,
                    "label": label,
                    "next": next_url,
                },
            )
        step_up_at = dict(request.session.get(SESSION_KEY_STEP_UP, {}))
        step_up_at[kind] = clock_now().isoformat()
        request.session[SESSION_KEY_STEP_UP] = step_up_at
        return redirect(next_url)

    return render(
        request, "web/auth/step_up.html", {"kind": kind, "label": label, "next": next_url}
    )


# ---------------------------------------------------------------------------------------
# J2: sign-out
# ---------------------------------------------------------------------------------------
@require_http_methods(["POST"])
@requires_action("shell.use")
def sign_out(request: HttpRequest) -> HttpResponse:
    from ham.identity.services import stop_impersonation

    if actor_of(request).is_impersonating:
        try:
            stop_impersonation(actor_of(request), end_reason="signed_out")
        except Exception:  # noqa: BLE001 - never block sign-out on a cleanup failure
            pass
        request.session.pop("ham_impersonation_id", None)
    if request.user.is_authenticated:
        from ham.audit.services import record as audit_record

        audit_record(
            ctx=None,
            actor_type="user",
            actor_user_id=request.user.id,
            action="auth.sign_out",
            target_type="user",
            target_id=str(request.user.id),
        )
    django_logout(request)
    return render(request, "web/auth/signed_out.html", {})


# ---------------------------------------------------------------------------------------
# F: Me -> Sign-in & security
# ---------------------------------------------------------------------------------------
@require_http_methods(["GET"])
@requires_action("me.security.manage")
def me_security(request: HttpRequest) -> HttpResponse:
    actor = actor_of(request)
    assert actor.user_id is not None
    user = User.objects.get(pk=actor.user_id)
    context = {
        "is_enrolled": mfa.is_enrolled(user),
        "recovery_codes_left": mfa.unused_recovery_code_count(user) if mfa.is_enrolled(user) else 0,
        "trusted_devices": user.trusted_devices.order_by("-created_at"),
        "mfa_required": mfa.mfa_required(user),
    }
    return render(request, "web/auth/me_security.html", context)


@require_http_methods(["POST"])
@handle_command_errors
@requires_action("me.recovery_codes.regenerate")
def me_regenerate_recovery_codes(request: HttpRequest) -> HttpResponse:
    from ham.identity.services import regenerate_own_recovery_codes

    codes = regenerate_own_recovery_codes(actor_of(request))
    request.session["ham_recovery_codes_once"] = codes
    return redirect(reverse("web:mfa_setup_codes"))


@require_http_methods(["POST"])
@requires_action("me.security.manage")
def me_forget_devices(request: HttpRequest) -> HttpResponse:
    actor = actor_of(request)
    assert actor.user_id is not None
    user = User.objects.get(pk=actor.user_id)
    mfa.forget_all_trusted_devices(user)
    messages.success(request, "Trusted devices forgotten. You'll be asked for a code next time.")
    return redirect(reverse("web:me_security"))


# ---------------------------------------------------------------------------------------
# Admin: MFA reset (item 4) and impersonation (item 5)
# ---------------------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
@handle_command_errors
@requires_action("user.mfa_reset")
def admin_mfa_reset(request: HttpRequest, user_id: uuid.UUID) -> HttpResponse:
    from ham.identity.mfa import reset_mfa

    target = User.objects.filter(pk=user_id).first()
    if target is None:
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        try:
            reset_mfa(
                actor_of(request),
                user_id=user_id,
                verification_method=request.POST.get("verification_method", ""),
                note=request.POST.get("note", ""),
            )
        except ValueError as exc:
            return render(
                request,
                "web/auth/admin_mfa_reset_confirm.html",
                {"target": target, "error": str(exc)},
            )
        messages.success(request, "Two-step sign-in reset.")
        return redirect(reverse("web:admin_user_detail", kwargs={"user_id": user_id}))

    return render(request, "web/auth/admin_mfa_reset_confirm.html", {"target": target})


@require_http_methods(["GET", "POST"])
@handle_command_errors
@requires_action("impersonation.start")
def admin_impersonate(request: HttpRequest, user_id: uuid.UUID) -> HttpResponse:
    from ham.identity.services import start_impersonation

    target = User.objects.filter(pk=user_id).first()
    if target is None:
        return render(request, "web/not_found.html", status=404)

    if request.method == "POST":
        try:
            session = start_impersonation(
                actor_of(request), target_user_id=user_id, reason=request.POST.get("reason", "")
            )
        except ValueError as exc:
            return render(
                request,
                "web/auth/admin_impersonate_confirm.html",
                {"target": target, "error": str(exc)},
            )
        request.session["ham_impersonation_id"] = str(session.id)
        return redirect(reverse("web:home"))

    return render(request, "web/auth/admin_impersonate_confirm.html", {"target": target})


@require_http_methods(["POST"])
@handle_command_errors
@requires_action("impersonation.stop")
def impersonation_stop(request: HttpRequest) -> HttpResponse:
    from ham.identity.services import stop_impersonation

    session = stop_impersonation(actor_of(request))
    request.session.pop("ham_impersonation_id", None)
    duration_min = int((clock_now() - session.started_at).total_seconds() // 60)
    messages.success(request, f"Troubleshooting ended · lasted {duration_min} min.")
    return redirect(reverse("web:home"))
