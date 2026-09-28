"""Admin -> Users & roles (foundation.md §7; auth-and-access.md §G "Users & roles").

G1 list, G2 detail (roles + G3 confirm sheet), invite (B7). The route guard already checked
`user.list` / `user.view` / `role.grant_global` etc. before these views run; per-button
visibility inside the page (e.g. hiding "Reset two-step sign-in" from a Director) is computed
here with `authorize()` directly, matching navigation.md §1 "Nav shows only what you can use".
"""

from __future__ import annotations

import uuid
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from ham.authz import roles
from ham.authz.commands import ImpersonationBlocked, PermissionDenied, StepUpRequired
from ham.authz.guard import requires_action
from ham.authz.matrix import authorize
from ham.identity import services
from ham.identity.models import RoleAssignment, User
from ham.identity.services import (
    DEFAULT_INVITE_ROLES,
    ROLE_CHECKBOX_ORDER,
    ROLE_DESCRIPTIONS,
    UserListFilters,
    cancel_invitation,
    get_user_detail,
    grant_global_role,
    invite_user,
    list_users,
    resend_invitation,
    revoke_global_role,
    update_identity,
)
from ham.rules import RULES

from .stepup import redirect_to_step_up

_ROLE_CHANGE_KIND = dict(RULES.auth.STEP_UP_ACTIONS)["role.grant_global"]
_PENDING_SESSION_KEY = "ham_pending_role_change"


@require_http_methods(["GET"])
@requires_action("user.list")
def admin_users_list(request):
    filters = UserListFilters(
        role=request.GET.get("role", ""),
        status=request.GET.get("status", ""),
        q=request.GET.get("q", ""),
    )
    rows = list_users(filters)
    return render(
        request,
        "web/admin_users_list.html",
        {
            "rows": rows,
            "filters": filters,
            "role_choices": ROLE_CHECKBOX_ORDER,
            "role_labels": roles.ROLE_LABELS,
        },
    )


@require_http_methods(["GET", "POST"])
@requires_action("user.invite")
def admin_users_invite(request):
    errors: dict[str, str] = {}
    values = {"email": "", "first_name": "", "last_name": ""}
    if request.method == "POST":
        values = {
            "email": request.POST.get("email", "").strip(),
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
        }
        if not values["email"]:
            errors["email"] = "Enter an email address."
        if not values["first_name"]:
            errors["first_name"] = "Enter a first name."
        if not errors:
            try:
                user = invite_user(
                    request.actor,
                    email=values["email"],
                    first_name=values["first_name"],
                    last_name=values["last_name"],
                    role_list=DEFAULT_INVITE_ROLES,
                )
            except StepUpRequired:
                return redirect_to_step_up(
                    request, reverse("web:admin_users_invite"), _ROLE_CHANGE_KIND
                )
            except ImpersonationBlocked:
                errors["email"] = "Inviting people isn't allowed while acting as someone else."
            except PermissionDenied:
                errors["email"] = "You don't have permission to invite with that role."
            except ValueError as exc:
                # PRD-guardian B7: `invite_user` raises a friendly message here for a
                # duplicate email; other ValueErrors (e.g. Q-055 missing reason) are already
                # written as person-facing text too.
                errors["email"] = str(exc)
            else:
                messages.success(request, f"Invited {values['email']}.")
                if authorize(request.actor, "user.view").allowed:
                    return redirect("web:admin_user_detail", user_id=user.id)
                # Q-082: an Assistant Director may invite but has no `user.view` — send them
                # to a confirmation they can actually see instead of a 404.
                query = urlencode({"email": values["email"]})
                return redirect(f"{reverse('web:admin_users_invite_sent')}?{query}")
    return render(request, "web/admin_users_invite.html", {"errors": errors, "values": values})


@require_http_methods(["GET"])
@requires_action("user.invite")
def admin_users_invite_sent(request):
    """ "Invitation sent" confirmation reachable by anyone who may invite, even without
    `user.view` (Q-082, item 7: give the Assistant Director a path in)."""
    return render(
        request, "web/admin_users_invite_sent.html", {"email": request.GET.get("email", "")}
    )


def _role_visibility(ctx, detail) -> dict[str, bool]:
    """Which role checkboxes `ctx` may edit for this subject (G2 "Roles the viewer can't
    change render read-only ... 'Only an Administrator can change this'")."""
    can_grant = authorize(ctx, "role.grant_global").allowed
    can_revoke = authorize(ctx, "role.revoke_global").allowed
    is_self = ctx.user_id == detail.user.id
    editable: dict[str, bool] = {}
    for role in ROLE_CHECKBOX_ORDER:
        if is_self:
            editable[role] = False
            continue
        if roles.ADMINISTRATOR in ctx.effective_roles:
            editable[role] = can_grant and can_revoke
        else:
            # Director: every role except Administrator (Q-041).
            editable[role] = (can_grant and can_revoke) and role != roles.ADMINISTRATOR
    return editable


@require_http_methods(["GET", "POST"])
@requires_action("user.view")
def admin_user_detail(request, user_id: uuid.UUID):
    detail = get_user_detail(user_id)
    if detail is None:
        return render(request, "web/not_found.html", status=404)

    ctx = request.actor
    active_roles = set(detail.active_global_roles)
    editable = _role_visibility(ctx, detail)
    pending = None
    review_error = None

    if request.method == "POST" and request.POST.get("stage") == "review":
        submitted = {r for r in request.POST.getlist("roles") if r in ROLE_CHECKBOX_ORDER}
        # Read-only boxes can't be un/checked by this viewer, whatever the client sent.
        locked_on = {r for r in active_roles if not editable.get(r, False)}
        locked_roles = {r for r in ROLE_CHECKBOX_ORDER if not editable.get(r, False)}
        submitted = (submitted - locked_roles) | locked_on
        to_add = sorted(submitted - active_roles)
        to_remove = sorted(active_roles - submitted)

        if not to_add and not to_remove:
            review_error = "No changes selected."
        elif ctx.user_id == detail.user.id:
            review_error = "You can't change your own role. Ask another Administrator."
        elif roles.ADMINISTRATOR in to_remove and _last_admin_after_removal(detail.user.id):
            review_error = "HAM needs at least one Administrator. Add another Administrator first."
        else:
            pending = {
                "add": to_add,
                "remove": to_remove,
                "reason_required": bool(set(to_add) & {roles.PASTOR, roles.BOARD_REPRESENTATIVE})
                and roles.ADMINISTRATOR not in ctx.effective_roles,
            }

    recent_events = []
    if authorize(ctx, "audit.view").allowed:
        from ham.authz.audit_access import list_events_for_target

        recent_events = list_events_for_target(
            ctx, target_type="user", target_id=str(detail.user.id), limit=5
        )

    return render(
        request,
        "web/admin_user_detail.html",
        {
            "detail": detail,
            "active_roles": active_roles,
            "editable": editable,
            "role_order": ROLE_CHECKBOX_ORDER,
            "role_labels": roles.ROLE_LABELS,
            "role_descriptions": ROLE_DESCRIPTIONS,
            "pending": pending,
            "review_error": review_error,
            "can_disable": (
                authorize(ctx, "user.disable").allowed
                and ctx.user_id != detail.user.id
                and detail.status != services.STATUS_INVITED
                # Q-052/Q-079: a Director may not disable an Administrator's account.
                and (
                    roles.ADMINISTRATOR in ctx.effective_roles
                    or roles.ADMINISTRATOR not in active_roles
                )
            ),
            "can_enable": (
                authorize(ctx, "user.enable").allowed
                and (
                    roles.ADMINISTRATOR in ctx.effective_roles
                    or roles.ADMINISTRATOR not in active_roles
                )
            ),
            "can_resend_invitation": (
                authorize(ctx, "user.invitation_resend").allowed
                and detail.status == services.STATUS_INVITED
            ),
            "can_cancel_invitation": (
                authorize(ctx, "user.invitation_cancel").allowed
                and detail.status == services.STATUS_INVITED
            ),
            "can_update_identity": authorize(ctx, "user.update_identity").allowed,
            "can_mfa_reset": authorize(ctx, "user.mfa_reset").allowed,
            "can_impersonate": (
                authorize(ctx, "impersonation.start").allowed
                and ctx.user_id != detail.user.id
                and roles.ADMINISTRATOR not in active_roles
            ),
            "recent_events": recent_events,
        },
    )


def _last_admin_after_removal(user_id: uuid.UUID) -> bool:
    remaining = (
        RoleAssignment.objects.filter(
            role=roles.ADMINISTRATOR,
            revoked_at__isnull=True,
            user__is_active=True,
            user__disabled_at__isnull=True,
        )
        .exclude(user_id=user_id)
        .values("user_id")
        .distinct()
        .count()
    )
    return remaining == 0


@require_http_methods(["POST"])
@requires_action("role.grant_global")
def admin_user_roles_confirm(request, user_id: uuid.UUID):
    to_add = [r for r in request.POST.getlist("add") if r in ROLE_CHECKBOX_ORDER]
    to_remove = [r for r in request.POST.getlist("remove") if r in ROLE_CHECKBOX_ORDER]
    reason = request.POST.get("reason", "").strip()
    ok, redirect_response = _apply_role_changes(request, user_id, to_add, to_remove, reason)
    if redirect_response is not None:
        return redirect_response
    return ok


@require_http_methods(["GET"])
@requires_action("role.grant_global")
def admin_user_roles_resume(request, user_id: uuid.UUID):
    """Landed here after the step-up stub (S3b's real step-up screen will redirect to
    `next=` the same way). Re-applies the diff stashed in the session by
    `_apply_role_changes` before the step-up redirect."""
    pending = request.session.pop(_PENDING_SESSION_KEY, None)
    if not pending or pending.get("user_id") != str(user_id):
        return redirect("web:admin_user_detail", user_id=user_id)
    ok, redirect_response = _apply_role_changes(
        request, user_id, pending["add"], pending["remove"], pending["reason"]
    )
    if redirect_response is not None:
        return redirect_response
    return ok


def _apply_role_changes(request, user_id: uuid.UUID, to_add, to_remove, reason):
    ctx = request.actor
    user = get_object_or_404(User, pk=user_id)
    try:
        # Item 4: multiple role changes in one confirm apply atomically (one transaction, all
        # or nothing). Each `grant_global_role`/`revoke_global_role` call is itself a
        # `@command` with its own `transaction.atomic()`; wrapping them in one more outer
        # atomic block makes a savepoint around the whole batch, so a failure partway (a
        # `StepUpRequired` on the third of three changes, say) rolls every change in this
        # confirm back, not just the one that failed.
        with transaction.atomic():
            for role in to_add:
                grant_global_role(ctx, user_id=user.id, role=role, reason=reason)
            for role in to_remove:
                assignment = RoleAssignment.objects.filter(
                    user=user, role=role, revoked_at__isnull=True, scope_type__isnull=True
                ).first()
                if assignment is not None:
                    revoke_global_role(ctx, assignment_id=assignment.id, reason=reason)
    except StepUpRequired:
        request.session[_PENDING_SESSION_KEY] = {
            "user_id": str(user_id),
            "add": list(to_add),
            "remove": list(to_remove),
            "reason": reason,
        }
        next_url = reverse("web:admin_user_roles_resume", args=[user_id])
        return None, redirect_to_step_up(request, next_url, _ROLE_CHANGE_KIND)
    except ImpersonationBlocked:
        messages.error(
            request,
            "Role and permission changes aren't allowed while acting as someone else. "
            "Return to your account to do this.",
        )
        return redirect("web:admin_user_detail", user_id=user_id), None
    except (PermissionDenied, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect("web:admin_user_detail", user_id=user_id), None

    messages.success(request, "Roles updated.")
    return redirect("web:admin_user_detail", user_id=user_id), None


@require_http_methods(["GET", "POST"])
@requires_action("user.disable")
def admin_user_disable(request, user_id: uuid.UUID):
    """UX C5: turning an account off is behind its own confirmation step with a required
    reason (audited), not a one-tap button — GET shows the confirmation, POST does it."""
    from ham.identity.services import disable_user

    detail = get_user_detail(user_id)
    if detail is None:
        return render(request, "web/not_found.html", status=404)

    if request.method == "GET":
        return render(request, "web/admin_user_disable_confirm.html", {"detail": detail})

    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Enter a reason for turning off this account.")
        return render(
            request,
            "web/admin_user_disable_confirm.html",
            {"detail": detail, "reason_error": True},
        )
    try:
        disable_user(request.actor, user_id=user_id, reason=reason)
    except ImpersonationBlocked:
        messages.error(
            request, "Turning off an account isn't allowed while acting as someone else."
        )
    except (PermissionDenied, ValueError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Account turned off.")
    return redirect("web:admin_user_detail", user_id=user_id)


@require_http_methods(["POST"])
@requires_action("user.invitation_resend")
def admin_user_invitation_resend(request, user_id: uuid.UUID):
    try:
        resend_invitation(request.actor, user_id=user_id)
    except ImpersonationBlocked:
        messages.error(request, "This isn't allowed while acting as someone else.")
    except (PermissionDenied, ValueError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Invitation resent.")
    return redirect("web:admin_user_detail", user_id=user_id)


@require_http_methods(["POST"])
@requires_action("user.invitation_cancel")
def admin_user_invitation_cancel(request, user_id: uuid.UUID):
    reason = request.POST.get("reason", "").strip()
    try:
        cancel_invitation(request.actor, user_id=user_id, reason=reason)
    except ImpersonationBlocked:
        messages.error(request, "This isn't allowed while acting as someone else.")
    except (PermissionDenied, ValueError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Invitation cancelled.")
    return redirect("web:admin_user_detail", user_id=user_id)


@require_http_methods(["GET", "POST"])
@requires_action("user.update_identity")
def admin_user_identity_update(request, user_id: uuid.UUID):
    """`POST /admin/users/<id>/identity` (item 7): a small form on the user detail page for
    an Administrator to correct a person's name/phone (e.g. someone who can't sign in to fix
    it themselves, Q-051)."""
    detail = get_user_detail(user_id)
    if detail is None:
        return render(request, "web/not_found.html", status=404)
    values = {
        "full_name": detail.profile.full_name if detail.profile else "",
        "mobile_phone": detail.profile.mobile_phone if detail.profile else "",
    }
    errors: dict[str, str] = {}
    if request.method == "POST":
        values = {
            "full_name": request.POST.get("full_name", "").strip(),
            "mobile_phone": request.POST.get("mobile_phone", "").strip(),
        }
        if not values["full_name"]:
            errors["full_name"] = "Enter a name."
        if not errors:
            update_identity(request.actor, user_id=user_id, **values)
            messages.success(request, "Updated.")
            return redirect("web:admin_user_detail", user_id=user_id)
    return render(
        request,
        "web/admin_user_identity_update.html",
        {"detail": detail, "values": values, "errors": errors},
    )


@require_http_methods(["POST"])
@requires_action("user.enable")
def admin_user_enable(request, user_id: uuid.UUID):
    from ham.identity.services import enable_user

    try:
        enable_user(request.actor, user_id=user_id, reason=request.POST.get("reason", ""))
    except ImpersonationBlocked:
        messages.error(request, "Turning on an account isn't allowed while acting as someone else.")
    except (PermissionDenied, ValueError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Account turned on.")
    return redirect("web:admin_user_detail", user_id=user_id)
