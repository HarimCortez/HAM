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

from ham.audit.services import record as audit_record
from ham.authz.context import SESSION_KEY_MFA_SATISFIED, SESSION_KEY_STEP_UP, ActorContext
from ham.authz.guard import requires_action
from ham.identity import authn, mfa
from ham.identity.models import User
from ham.identity.web import handle_command_errors, safe_next_url
from ham.platform.clock import now as clock_now
from ham.rules import RULES


def _client_ip(request: HttpRequest) -> str:
    """Best-effort client IP for the sign-in rate limit (security review M3). Render (and any
    other reverse proxy) sets `X-Forwarded-For`; only its first hop is trusted here since this
    is a throttle, not an authorization decision."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


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
        ip = _client_ip(request)
        result = authn.request_sign_in(email=email, next_url=next_url, ip_address=ip)
        request.session["ham_sign_in_email"] = email
        request.session[SESSION_PENDING_NEXT] = next_url
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
            resend_result = authn.request_sign_in(
                email=email,
                next_url=request.session.get(SESSION_PENDING_NEXT, ""),
                ip_address=_client_ip(request),
            )
            if resend_result.status == "sent":
                messages.success(request, "Sent again. Use the newest email.")
            elif resend_result.status == "cooldown":
                messages.info(
                    request, "You can resend once the current email has had a moment to arrive."
                )
            else:
                messages.error(request, "Too many sign-in emails for now. Try again later.")
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


def _holds_non_mfa_role(user: User) -> bool:
    """Q-045: whether `user` keeps *some* access even before/without MFA (e.g. Marcus's
    Director+Volunteer combination keeps Volunteer)."""
    from ham.identity.models import RoleAssignment

    return (
        RoleAssignment.objects.filter(user=user, revoked_at__isnull=True)
        .exclude(role__in=RULES.auth.MFA_REQUIRED_ROLES)
        .exists()
    )


def _after_email_verified(request: HttpRequest, *, email: str, next_url: str) -> HttpResponse:
    request.session.pop("ham_sign_in_email", None)
    request.session.pop(SESSION_PENDING_NEXT, None)
    user = User.objects.filter(email=email).first()
    if user is None or not user.is_active or user.is_disabled:
        return render(request, "web/auth/sign_in_no_account.html", {})

    from ham.identity.services import invitation_is_valid

    if not invitation_is_valid(user):
        # This only ever differs from `sign_in_no_account` *after* the person has already
        # proven they answered their own emailed code/link, so it doesn't reopen account
        # enumeration (foundation.md §7: identical response for unknown emails, which this
        # path is never reached for) — it just tells an actually-invited person, correctly,
        # why they can't get in.
        return render(
            request,
            "web/auth/sign_in_no_account.html",
            {
                "error": "This invitation has expired. Ask the person who invited you to "
                "send a new one."
            },
        )

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
    user = _pending_mfa_user(request)
    if user is not None:
        # Security review M7: lockouts are audited (foundation.md §6 "Sign-in failed
        # (lockout) ... system"); ordinary wrong attempts are audited separately below.
        audit_record(
            ctx=None,
            actor_type="system",
            actor_user_id=user.id,
            action="auth.mfa.locked",
            target_type="user",
            target_id=str(user.id),
        )
    for key in (SESSION_PENDING_MFA_USER_ID, SESSION_PENDING_NEXT, SESSION_MFA_ATTEMPTS):
        request.session.pop(key, None)
    messages.error(request, "For your safety, please start again from your email.")
    return redirect(reverse("web:sign_in"))


def _complete_mfa_sign_in(
    request: HttpRequest, *, user: User, trust_device: bool, recovery_codes_left: int | None
) -> HttpResponse:
    next_url = request.session.pop(SESSION_PENDING_NEXT, "") or reverse("web:home")
    request.session.pop(SESSION_PENDING_MFA_USER_ID, None)
    request.session.pop(SESSION_MFA_ATTEMPTS, None)
    authn.complete_sign_in(request, user=user)
    request.session[SESSION_KEY_MFA_SATISFIED] = True
    if recovery_codes_left is not None:
        # UX C4/E2: tell the person plainly they burned a recovery code and how many remain.
        messages.info(
            request,
            f"You signed in with a recovery code. {recovery_codes_left} left. "
            "Set up your new phone from Sign-in & security when you can.",
        )
    response = redirect(next_url)
    if trust_device:
        _set_trusted_device_cookie(response, user)
    return response


@require_http_methods(["GET", "POST"])
def sign_in_mfa(request: HttpRequest) -> HttpResponse:
    user = _pending_mfa_user(request)
    if user is None:
        return redirect(reverse("web:sign_in"))

    if request.method == "POST":
        if request.POST.get("continue_without_mfa"):
            # Q-045 (enrolled but can't use the authenticator right now, no recovery code
            # handy): keep whatever non-MFA access the person also holds; MFA-role
            # permissions stay off until a real MFA/recovery-code sign-in.
            if not _holds_non_mfa_role(user):
                return render(
                    request,
                    "web/auth/sign_in_mfa.html",
                    {
                        "error": "Your account needs two-step sign-in to continue — there's no "
                        "other access to fall back to. Use a recovery code, or ask an "
                        "Administrator to reset two-step sign-in.",
                        "use_recovery": True,
                        "trusted_device_days": int(RULES.auth.MFA_TRUSTED_DEVICE_LIFETIME.days),
                    },
                )
            next_url = request.session.pop(SESSION_PENDING_NEXT, "") or reverse("web:home")
            request.session.pop(SESSION_PENDING_MFA_USER_ID, None)
            request.session.pop(SESSION_MFA_ATTEMPTS, None)
            authn.complete_sign_in(request, user=user)
            messages.info(
                request,
                "Signed in without two-step sign-in for now. Your other access still works; "
                "set up your new phone (or ask an Administrator) to get the rest back.",
            )
            return redirect(next_url)

        code = request.POST.get("code", "")
        use_recovery = bool(request.POST.get("use_recovery"))
        recovery_codes_left: int | None = None
        if use_recovery:
            recovery_codes_left = mfa.verify_recovery_code(user, code)
            ok = recovery_codes_left is not None
        else:
            ok = mfa.verify_totp(user, code)
        if not ok:
            # Security review M7: failed challenges are audited (not every keystroke of a
            # sign-in code, which foundation.md §6 calls noise, but a *wrong MFA attempt*
            # against an already-identified account is worth a record).
            audit_record(
                ctx=None,
                actor_type="system",
                actor_user_id=user.id,
                action="auth.mfa.failed",
                target_type="user",
                target_id=str(user.id),
            )
            attempts = request.session.get(SESSION_MFA_ATTEMPTS, 0) + 1
            request.session[SESSION_MFA_ATTEMPTS] = attempts
            if attempts >= RULES.auth.MFA_CODE_MAX_ATTEMPTS:
                return _restart_sign_in(request)
            return render(
                request,
                "web/auth/sign_in_mfa.html",
                {
                    "error": "That code didn't match. Try the current one.",
                    "use_recovery": use_recovery,
                    "can_continue_without_mfa": _holds_non_mfa_role(user),
                    "trusted_device_days": int(RULES.auth.MFA_TRUSTED_DEVICE_LIFETIME.days),
                },
            )

        return _complete_mfa_sign_in(
            request,
            user=user,
            trust_device=bool(request.POST.get("trust_device")),
            recovery_codes_left=recovery_codes_left,
        )

    use_recovery = bool(request.GET.get("recovery"))
    return render(
        request,
        "web/auth/sign_in_mfa.html",
        {
            "use_recovery": use_recovery,
            "can_continue_without_mfa": _holds_non_mfa_role(user),
            "trusted_device_days": int(RULES.auth.MFA_TRUSTED_DEVICE_LIFETIME.days),
        },
    )


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
_MFA_REPLACE_STEP_UP_KIND = "mfa_replace"


@require_http_methods(["GET", "POST"])
def mfa_setup(request: HttpRequest) -> HttpResponse:
    # Reachable three ways: mid-sign-in (pending user, not yet fully logged in), later by an
    # already-signed-in person who still hasn't enrolled (Q-045: they kept non-MFA access),
    # or (Q-093) an already-*enrolled*, fully signed-in person replacing a lost/new phone.
    pending_user = _pending_mfa_user(request)
    user = pending_user or (request.user if request.user.is_authenticated else None)
    if user is None:
        return redirect(reverse("web:sign_in"))

    if pending_user is not None:
        # Security review C1/PRD B1: a mid-sign-in session only ever proves the person
        # answered the *emailed* code/link. If the account is already enrolled, that session
        # must never be able to reach enrollment (which would silently replace the real
        # authenticator/recovery codes) — it must go through the real TOTP/recovery
        # challenge instead. This is the actual fix for the MFA-bypass-via-re-enrollment
        # finding: previously this branch didn't exist and any pending session reached the
        # `update_or_create` in `mfa.confirm_enrollment` below.
        if mfa.is_enrolled(pending_user):
            return redirect(reverse("web:sign_in_mfa"))
        replacing = False
    else:
        if not mfa.is_enrolled(user):
            replacing = False
        else:
            # Q-093 (proposed default, docs/prd-open-questions.md): replacing an existing
            # authenticator is only allowed once fully signed in *with* two-step sign-in this
            # session (TOTP or a recovery code — never merely "has a cookie"), and only after
            # a fresh step-up. `?replace=1` is how `me_security.html`'s "Set up a new phone"
            # link opts into this; a bare GET here for an already-enrolled, already-signed-in
            # person just goes to the security page, as before.
            if request.GET.get("replace") != "1" and request.POST.get("step") != "connect":
                return redirect(reverse("web:me_security"))
            actor = actor_of(request)
            if not actor.mfa_satisfied:
                return redirect(reverse("web:me_security"))
            if actor.is_impersonating:
                # Security review L2: step-up (and this replacement, which requires one)
                # always uses the real actor's own factors — while impersonating there is no
                # "own" TOTP device to check against the target's, so refuse outright rather
                # than silently checking the wrong person's device.
                messages.error(
                    request,
                    "Replacing an authenticator isn't available while acting as someone else.",
                )
                return redirect(reverse("web:home"))
            if not actor.has_fresh_step_up(
                _MFA_REPLACE_STEP_UP_KIND, now=clock_now(), freshness=RULES.auth.STEP_UP_WINDOW
            ):
                here = request.get_full_path()
                return redirect(
                    f"{reverse('web:step_up')}?next={here}&kind={_MFA_REPLACE_STEP_UP_KIND}"
                )
            replacing = True

    if request.method == "POST":
        step = request.POST.get("step")
        if step == "continue" and pending_user is not None and _holds_non_mfa_role(pending_user):
            # Q-045: "Can't do this now? Continue as a volunteer." — sign in with whatever
            # non-MFA access the person also holds; MFA-role permissions stay off until they
            # finish enrollment.
            next_url = request.session.pop(SESSION_PENDING_NEXT, "") or reverse("web:home")
            request.session.pop(SESSION_PENDING_MFA_USER_ID, None)
            request.session.pop(SESSION_MFA_ATTEMPTS, None)
            request.session.pop(SESSION_ENROLL_SECRET, None)
            authn.complete_sign_in(request, user=pending_user)
            messages.info(
                request,
                "Signed in for now. Set up two-step sign-in when you can to unlock the rest "
                "of your access.",
            )
            return redirect(next_url)
        if step == "connect":
            secret = request.session.get(SESSION_ENROLL_SECRET, "")
            code = request.POST.get("code", "")
            try:
                codes = mfa.confirm_enrollment(user, secret=secret, code=code, replace=replacing)
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
    return render(
        request,
        "web/auth/mfa_setup_connect.html",
        {
            "enrollment": enrollment,
            "replacing": replacing,
            "can_continue_without_mfa": pending_user is not None
            and _holds_non_mfa_role(pending_user),
        },
    )


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
    "mfa_replace": "replacing your authenticator app",
}


_STEP_UP_ATTEMPTS_SESSION_KEY = "ham_step_up_attempts"


def _cancel_url(request: HttpRequest) -> str:
    """UX C1: Cancel must return to where the person came from, never loop back through
    another step-up. `?cancel=` lets a caller be explicit (e.g. `views_audit.py`,
    `views_admin_users.py`); otherwise fall back to the (validated) HTTP referer, then Home."""
    candidate = request.GET.get("cancel") or request.POST.get("cancel") or ""
    if not candidate:
        candidate = request.META.get("HTTP_REFERER", "")
    from django.utils.http import url_has_allowed_host_and_scheme

    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return reverse("web:home")


@require_http_methods(["GET", "POST"])
@requires_action("shell.use")
def step_up(request: HttpRequest) -> HttpResponse:
    next_url = safe_next_url(request)
    cancel_url = _cancel_url(request)
    kind = request.GET.get("kind") or request.POST.get("kind") or ""
    label = _STEP_UP_ACTION_LABELS.get(kind, "confirming it's you")
    actor = actor_of(request)

    if actor.is_impersonating:
        # Security review L2: step-up always checks the *real* actor's own TOTP/recovery
        # factors (`ham.identity.mfa.verify_step_up`'s docstring), but while impersonating
        # `ActorContext.user_id` is the *target* — reaching this screen would otherwise check
        # (and let someone burn) the target's factors instead. Refuse outright rather than
        # silently authenticating against the wrong person's credentials.
        messages.error(request, "Confirming it's you isn't available while acting as someone else.")
        return redirect(reverse("web:home"))

    if request.method == "POST" and request.POST.get("cancel"):
        request.session.pop("ham_pending_role_change", None)
        request.session.pop("ham_step_up_stash", None)
        messages.info(request, "Nothing changed.")
        return redirect(cancel_url)

    if request.method == "POST":
        # Security review H1: unlimited guesses at a fresh authenticator/recovery code. Same
        # shape as the sign-in MFA challenge's lockout (Q-072's rules value), scoped to this
        # session + step-up kind so a lockout on one kind doesn't affect another.
        attempts_by_kind = dict(request.session.get(_STEP_UP_ATTEMPTS_SESSION_KEY, {}))
        if attempts_by_kind.get(kind, 0) >= RULES.auth.MFA_CODE_MAX_ATTEMPTS:
            # Audit the lockout once (the moment it happens), not on every further attempt —
            # but keep refusing every further attempt (never reset the counter here; only a
            # successful step-up, elsewhere below, clears it).
            if attempts_by_kind.get(kind) == RULES.auth.MFA_CODE_MAX_ATTEMPTS:
                audit_record(
                    ctx=actor,
                    action="auth.step_up.locked",
                    target_type="user",
                    target_id=str(actor.user_id),
                )
            attempts_by_kind[kind] = RULES.auth.MFA_CODE_MAX_ATTEMPTS + 1
            request.session[_STEP_UP_ATTEMPTS_SESSION_KEY] = attempts_by_kind
            messages.error(
                request, "Too many tries. Start again when you're ready to confirm it's you."
            )
            return redirect(cancel_url)

        code = request.POST.get("code", "")
        ok = mfa.verify_step_up(actor, code=code)
        if not ok:
            attempts_by_kind[kind] = attempts_by_kind.get(kind, 0) + 1
            request.session[_STEP_UP_ATTEMPTS_SESSION_KEY] = attempts_by_kind
            return render(
                request,
                "web/auth/step_up.html",
                {
                    "error": "That code didn't match.",
                    "kind": kind,
                    "label": label,
                    "next": next_url,
                    "cancel_url": cancel_url,
                },
            )
        attempts_by_kind.pop(kind, None)
        request.session[_STEP_UP_ATTEMPTS_SESSION_KEY] = attempts_by_kind
        step_up_at = dict(request.session.get(SESSION_KEY_STEP_UP, {}))
        step_up_at[kind] = clock_now().isoformat()
        request.session[SESSION_KEY_STEP_UP] = step_up_at
        return redirect(next_url)

    return render(
        request,
        "web/auth/step_up.html",
        {"kind": kind, "label": label, "next": next_url, "cancel_url": cancel_url},
    )


_PENDING_SESSION_KEYS = (
    "ham_sign_in_email",
    SESSION_PENDING_MFA_USER_ID,
    SESSION_PENDING_NEXT,
    SESSION_MFA_ATTEMPTS,
    SESSION_ENROLL_SECRET,
    "ham_recovery_codes_once",
)


@require_http_methods(["POST"])
def sign_in_cancel(request: HttpRequest) -> HttpResponse:
    """Security review L5 / UX M3: "Sign out" from the mid-sign-in/MFA-setup screens must be
    reachable *before* the person is fully authenticated (the ordinary `sign_out` route
    requires `shell.use`, which a pending session doesn't have — it used to bounce to
    `/sign-in?next=/sign-out`, leaving the pending-MFA session keys, including the plaintext
    enrollment secret, sitting in the session on a shared computer) and must clear every
    pending sign-in/enrollment session key, not just log the person out."""
    for key in _PENDING_SESSION_KEYS:
        request.session.pop(key, None)
    if request.user.is_authenticated:
        django_logout(request)
    return render(request, "web/auth/signed_out.html", {})


# ---------------------------------------------------------------------------------------
# J2: sign-out
# ---------------------------------------------------------------------------------------
@require_http_methods(["POST"])
@requires_action("shell.use")
def sign_out(request: HttpRequest) -> HttpResponse:
    from ham.identity.impersonation import end_impersonation
    from ham.identity.models import ImpersonationSession

    actor = actor_of(request)
    if actor.is_impersonating:
        assert actor.impersonation_id is not None
        try:
            # `end_impersonation` (not the `stop_impersonation` command) is the one funnel
            # every non-manual end path uses, so `ImpersonationEnded`/the after-the-fact email
            # (Q-049) fire from exactly one place.
            end_impersonation(
                actor.impersonation_id, reason=ImpersonationSession.END_REASON_SIGNED_OUT
            )
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
    for key in _PENDING_SESSION_KEYS:
        request.session.pop(key, None)
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
        "recovery_codes_total": RULES.auth.MFA_RECOVERY_CODE_COUNT,
        "trusted_device_days": int(RULES.auth.MFA_TRUSTED_DEVICE_LIFETIME.days),
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


@require_http_methods(["POST"])
@requires_action("me.security.manage")
def me_sign_out_everywhere(request: HttpRequest) -> HttpResponse:
    """UX M8: a *real* "sign out everywhere" — every other open session for this person stops
    being privileged on its next request (`ham.identity.mfa.sign_out_everywhere` bumps
    `session_epoch`), and this request also ends its own session/cookies right away."""
    actor = actor_of(request)
    assert actor.user_id is not None
    user = User.objects.get(pk=actor.user_id)
    mfa.sign_out_everywhere(user)
    django_logout(request)
    response = render(request, "web/auth/signed_out.html", {})
    response.delete_cookie(mfa.TRUSTED_DEVICE_COOKIE_NAME)
    return response


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
