"""Identity's own outbox-email builders (Q-037/Q-071/Q-084 invitation, Q-055 role-change
notice, Q-049 impersonation-ended notice): each domain fact ``ham.identity`` emits to the
outbox that should become an email is resolved *here*, using only the ids/codes on the
``OutboxEvent`` (§68) plus identity's own models/services — never a value carried in the
payload itself. Registered once from ``IdentityConfig.ready()``.

Import-linter carve-out: this is the one place ``ham.identity`` may import
``ham.integrations`` (pyproject.toml's "domain modules never import ham.integrations
directly" contract lists this module in ``ignore_imports``, alongside the existing
``ham.identity.authn``/``ham.identity.mfa`` -> ``ham.integrations.email.service`` carve-outs)
— a domain module resolving its own notification content is the documented pattern
(``ham.integrations.email.notifications``'s own module docstring), not a generic integrations
concern.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

from ham.authz import roles
from ham.integrations.email.notifications import (
    NotificationEmail,
    register_notification,
)
from ham.outbox.models import OutboxEvent
from ham.platform.church import church_profile, format_church_time
from ham.rules import RULES

from .models import ImpersonationSession, SharedIdentityProfile, User


def _display_name(user_id: uuid.UUID | str | None) -> str:
    if not user_id:
        return ""
    profile = SharedIdentityProfile.objects.filter(user_id=user_id).select_related("user").first()
    if profile is None:
        return ""
    return profile.display_name or profile.user.email


def _absolute_url(path: str) -> str:
    base = str(settings.HAM_BASE_URL).rstrip("/")
    return f"{base}{path}"


def _sign_in_url(email: str = "") -> str:
    path = reverse("web:sign_in")
    if email:
        path = f"{path}?{urlencode({'email': email})}"
    return _absolute_url(path)


# ---------------------------------------------------------------------------------------
# Invitation email (Q-037, Q-071, Q-084; PRD-guardian B3/C3): sent when `invite_user` emits
# `UserCreated` with an `invited_by` id. `bootstrap_administrator` also emits `UserCreated`
# but never sets `invited_by` — that is not an invitation, so no email is sent for it.
# ---------------------------------------------------------------------------------------
def _build_invitation_email(event: OutboxEvent) -> NotificationEmail | None:
    invited_by = event.payload.get("invited_by")
    if not invited_by:
        return None
    user = User.objects.filter(pk=event.aggregate_id).first()
    if user is None:
        return None
    inviter_name = _display_name(invited_by) or "A HAM leader"
    church = church_profile()
    days = RULES.auth.ACCOUNT_INVITATION_LIFETIME.days
    text = (
        f"{inviter_name} invited you to join HAM at {church.name}.\n\n"
        f"Sign in at {_sign_in_url(user.email)} using this email address to get started.\n\n"
        f"This invitation is valid for {days} days. If it expires, ask {inviter_name} to send "
        "a new one."
    )
    return NotificationEmail(
        to=user.email,
        subject=f"{inviter_name} invited you to HAM at {church.short_name}",
        text_body=text,
        category="account_invited",
    )


# ---------------------------------------------------------------------------------------
# Role grant/removal notice to every active Administrator (Q-055, Q-041).
# ---------------------------------------------------------------------------------------
def _build_role_change_email(event: OutboxEvent) -> list[NotificationEmail] | None:
    subject_user = User.objects.filter(pk=event.aggregate_id).first()
    if subject_user is None:
        return None
    subject_name = _display_name(subject_user.id) or subject_user.email
    role = event.payload.get("role", "")
    role_label = roles.ROLE_LABELS.get(role, role)
    verb = "granted" if event.event_type == "RoleGranted" else "removed"
    changer_id = event.payload.get("granted_by") or event.payload.get("revoked_by")
    changer_name = _display_name(changer_id) or "A HAM leader"
    admin_emails = list(
        User.objects.filter(
            role_assignments__role=roles.ADMINISTRATOR,
            role_assignments__revoked_at__isnull=True,
            is_active=True,
            disabled_at__isnull=True,
        )
        .values_list("email", flat=True)
        .distinct()
    )
    if not admin_emails:
        return None
    church = church_profile()
    text = (
        f"{changer_name} {verb} the {role_label} role for {subject_name}.\n\n"
        f"See this change in the HAM audit log: {_absolute_url(reverse('web:audit_log'))}"
    )
    subject = f"{church.short_name} HAM: role change for {subject_name}"
    return [
        NotificationEmail(to=email, subject=subject, text_body=text, category="role_change_notice")
        for email in admin_emails
    ]


# ---------------------------------------------------------------------------------------
# Impersonation-ended notice to the impersonated person (Q-049), from every end path via
# `ham.identity.impersonation.end_impersonation`.
# ---------------------------------------------------------------------------------------
def _build_impersonation_ended_email(event: OutboxEvent) -> NotificationEmail | None:
    target = User.objects.filter(pk=event.aggregate_id).first()
    if target is None:
        return None
    admin_id = event.payload.get("admin_user_id")
    admin_name = _display_name(admin_id) or "An Administrator"
    session_id = event.payload.get("session_id")
    session = ImpersonationSession.objects.filter(pk=session_id).first() if session_id else None
    reason = session.reason if session else ""
    church = church_profile()
    span = ""
    if session is not None and session.ended_at is not None:
        start_local = format_church_time(session.started_at, church=church)
        end_local = format_church_time(session.ended_at, church=church)
        span = f"from {start_local} to {end_local}"
    text = (
        f"{admin_name} signed in as your HAM account to help with something, "
        f"{span or 'briefly'}, and has returned to their own account.\n\n"
        f"Reason given: {reason or '(none recorded)'}\n\n"
        f"If this doesn't seem right, contact {church.email}."
    )
    return NotificationEmail(
        to=target.email,
        subject=f"{church.short_name} HAM: account activity notice",
        text_body=text,
        category="impersonation_ended_notice",
    )


def register() -> None:
    """Called once from `IdentityConfig.ready()`."""
    register_notification("UserCreated", _build_invitation_email)
    register_notification("RoleGranted", _build_role_change_email)
    register_notification("RoleRevoked", _build_role_change_email)
    register_notification("ImpersonationEnded", _build_impersonation_ended_email)
