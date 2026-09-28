"""`identity_user`, `identity_profile`, `identity_role_assignment`, `identity_impersonation`
(foundation.md §3). Only `ham.identity` may query these; everyone else gets an
`ActorContext` (foundation.md §1).
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q

from ham.authz import roles
from ham.platform.ids import UUID7Field


class CIEmailField(models.EmailField):
    """A `citext` column (foundation.md §3: "email (citext, unique, **S**)").

    Postgres `citext` (enabled by the `0001_initial` migration) gives case-insensitive
    uniqueness and lookups without normalizing email case in Python everywhere.
    """

    def db_type(self, connection) -> str:
        return "citext"


class UserManager(BaseUserManager["User"]):
    """HAM users have no usable password (sign-in is by emailed code + MFA, S3b)."""

    use_in_migrations = True

    def _create(self, email: str, **extra_fields: Any) -> User:
        if not email:
            raise ValueError("User requires an email address")
        email = self.normalize_email(email).lower()
        user: User = self.model(email=email, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, **extra_fields: Any) -> User:
        return self._create(email, **extra_fields)

    def get_by_natural_key(self, email: str) -> User:  # type: ignore[override]
        return self.get(email__iexact=email)


class User(AbstractBaseUser):
    """foundation.md §3 "User". States: Invited (no `first_sign_in_at`) -> Active <-> Disabled.

    Deliberately does **not** use `PermissionsMixin` (Django's groups/permissions): HAM has
    its own deny-by-default matrix (`ham.authz`); mixing in Django's permission system would
    be a second, unaudited source of authority.
    """

    id = UUID7Field()
    email = CIEmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by_id = models.UUIDField(null=True, blank=True)  # null = system (bootstrap)
    first_sign_in_at = models.DateTimeField(null=True, blank=True)
    last_sign_in_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    disabled_by_id = models.UUIDField(null=True, blank=True)
    # Q-037/Q-071/Q-084: baseline for the invitation's 7-day validity window. Null until an
    # invited person's leader clicks "Resend invitation"; until then the window is measured
    # from `created_at` (`ham.identity.services.invitation_is_valid`).
    invitation_resent_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "identity_user"

    def __str__(self) -> str:  # pragma: no cover - trivial; never logged (PII, §68)
        return str(self.id)

    @property
    def is_invited(self) -> bool:
        return self.first_sign_in_at is None

    @property
    def is_disabled(self) -> bool:
        return self.disabled_at is not None


class SharedIdentityProfile(models.Model):
    """foundation.md §3 "SharedIdentityProfile" (§36.1 shared-identity seam)."""

    user = models.OneToOneField(
        User, on_delete=models.PROTECT, primary_key=True, related_name="profile"
    )
    full_name = models.CharField(max_length=200, blank=True, default="")
    mobile_phone = models.CharField(max_length=32, blank=True, default="")  # E.164, **S**
    notify_email = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "identity_profile"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Profile({self.user_id})"

    @property
    def display_name(self) -> str:
        """ "Kevin T." — derived, never stored (foundation.md §3)."""
        parts = self.full_name.strip().split()
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        return f"{parts[0]} {parts[-1][0]}."


class RoleAssignment(models.Model):
    """foundation.md §3 "RoleAssignment". Rows are never deleted — a re-grant is a new row;
    revoking sets `revoked_at`/`revoked_by`/`revoke_reason` on the existing row."""

    ROLE_CHOICES = [(r, roles.ROLE_LABELS[r]) for r in sorted(roles.ALL_ROLES)]
    SCOPE_TYPE_CHOICES = [
        (roles.SCOPE_TYPE_PROJECT, "Project"),
        (roles.SCOPE_TYPE_TASK, "Task"),
    ]

    id = UUID7Field()
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="role_assignments")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES)
    # null=True is deliberate: NULL ("no scope") is distinct from "" and is what the CHECK
    # constraint and partial unique indexes below key off of (foundation.md §3).
    scope_type = models.CharField(  # noqa: DJ001
        max_length=16, choices=SCOPE_TYPE_CHOICES, null=True, blank=True
    )
    scope_id = models.UUIDField(null=True, blank=True)

    granted_by_id = models.UUIDField(null=True, blank=True)  # null = system (bootstrap)
    granted_at = models.DateTimeField()
    grant_reason = models.CharField(max_length=500, blank=True, default="")

    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by_id = models.UUIDField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        db_table = "identity_role_assignment"
        constraints = [
            # The role's scope kind must match scope_type (foundation.md §3 CHECK).
            models.CheckConstraint(
                name="role_scope_kind_matches",
                condition=(
                    (
                        Q(role__in=sorted(roles.GLOBAL_ROLES))
                        & Q(scope_type__isnull=True)
                        & Q(scope_id__isnull=True)
                    )
                    | (
                        Q(role=roles.PROJECT_LEADER)
                        & Q(scope_type=roles.SCOPE_TYPE_PROJECT)
                        & Q(scope_id__isnull=False)
                    )
                    | (
                        Q(role=roles.TASK_LEADER)
                        & Q(scope_type=roles.SCOPE_TYPE_TASK)
                        & Q(scope_id__isnull=False)
                    )
                ),
            ),
            # One active global role per user per role (foundation.md §3 partial unique).
            models.UniqueConstraint(
                fields=["user", "role"],
                condition=Q(revoked_at__isnull=True, scope_type__isnull=True),
                name="uniq_active_global_role_per_user",
            ),
            # One active leader per project / per task (Q-039).
            models.UniqueConstraint(
                fields=["role", "scope_type", "scope_id"],
                condition=Q(revoked_at__isnull=True, scope_type__isnull=False),
                name="uniq_active_leader_per_scope",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "role"], name="role_assignment_user_role_idx"),
            models.Index(fields=["scope_type", "scope_id"], name="role_assignment_scope_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.role}@{self.scope_id or 'global'} -> {self.user_id}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class SignInChallenge(models.Model):
    """One emailed sign-in code+link (PRD §60.2, foundation.md §7). The code and the link
    token are one credential (docs/ux/auth-and-access.md A2 "Link and code are one
    credential"): consuming either consumes both, and neither the code nor the raw link
    token is ever stored — only their hashes (`ham.identity.authn`), so a leaked database
    row can't be replayed.

    Created whether or not `email` has an account (foundation.md §7 "identical response for
    unknown emails") — this row exists purely to rate-limit/cooldown by address without ever
    branching visibly on account existence.
    """

    id = UUID7Field()
    email = CIEmailField()
    code_hash = models.CharField(max_length=64)
    link_token_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    # Where to send the person after sign-in (never trusted as an open redirect without the
    # `url_has_allowed_host_and_scheme` check in the view).
    next_url = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        db_table = "identity_sign_in_challenge"
        indexes = [models.Index(fields=["email", "created_at"], name="sign_in_challenge_email_idx")]

    def __str__(self) -> str:  # pragma: no cover - trivial; never logged (email is **S**)
        return f"SignInChallenge({self.id})"


class TOTPDevice(models.Model):
    """One enrolled authenticator per user (foundation.md §3 "MFA"). The secret is
    encrypted at rest (`ham.identity.crypto`, `HAM_FIELD_ENCRYPTION_KEY`)."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, related_name="totp_device"
    )
    secret_encrypted = models.CharField(max_length=255)
    created_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_totp_device"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"TOTPDevice({self.user_id})"

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class RecoveryCode(models.Model):
    """One single-use recovery code (foundation.md §3 "10 recovery codes"). Only the hash is
    stored; codes are shown to the person once, at enrollment or regeneration."""

    id = UUID7Field()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_recovery_code"
        indexes = [models.Index(fields=["user", "used_at"], name="recovery_code_user_used_idx")]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"RecoveryCode({self.user_id})"


class TrustedDevice(models.Model):
    """ "Trust this device for 30 days" (PRD §60.1, Q-010): skips the authenticator challenge
    (never step-up, foundation.md owner-decisions box) until `expires_at` or reset."""

    id = UUID7Field()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trusted_devices")
    token_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()

    class Meta:
        db_table = "identity_trusted_device"
        indexes = [models.Index(fields=["user"], name="trusted_device_user_idx")]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"TrustedDevice({self.user_id})"


class ImpersonationSession(models.Model):
    """foundation.md §3 "ImpersonationSession" (PRD §59)."""

    END_REASON_MANUAL = "manual"
    END_REASON_IDLE_TIMEOUT = "idle_timeout"
    END_REASON_SIGNED_OUT = "signed_out"
    END_REASON_TARGET_DISABLED = "target_disabled"
    END_REASON_CHOICES = [
        (END_REASON_MANUAL, "Manual"),
        (END_REASON_IDLE_TIMEOUT, "Idle timeout"),
        (END_REASON_SIGNED_OUT, "Signed out"),
        (END_REASON_TARGET_DISABLED, "Target disabled"),
    ]

    id = UUID7Field()
    admin_user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="impersonations_started"
    )
    target_user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="impersonations_received"
    )
    reason = models.CharField(max_length=500)  # **S**: may mention a person
    started_at = models.DateTimeField()
    last_activity_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    # null=True: no end reason yet while the session is active (distinct from "").
    end_reason = models.CharField(  # noqa: DJ001
        max_length=20, choices=END_REASON_CHOICES, null=True, blank=True
    )

    class Meta:
        db_table = "identity_impersonation"
        indexes = [
            models.Index(fields=["admin_user", "ended_at"], name="impersonation_admin_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Impersonation({self.admin_user_id} as {self.target_user_id})"
