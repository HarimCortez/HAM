"""manage.py seed_dev

Creates the fictional example.org personas from foundation.md §2.11 for local development
and Playwright smoke tests. Refuses to run when `HAM_ENV=production`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from ham.authz import roles
from ham.identity import mfa
from ham.identity.crypto import encrypt
from ham.identity.models import RoleAssignment, SharedIdentityProfile, TOTPDevice, User
from ham.platform.clock import now as clock_now
from ham.platform.env import refuse_in_production

# Fixed dev-only TOTP secrets (foundation.md §2.11), one per §60.1 persona, so Playwright and
# local sign-in don't need a real authenticator app. Never used outside development
# (`refuse_in_production` below refuses the whole command in production).
DEV_TOTP_SECRETS: dict[str, str] = {
    "nadia@example.org": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
    "marcus@example.org": "MZXW6YTBOI5FCTLTMZXW6YTBOI5FCTLT",
    "andre@example.org": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
    "ruth@example.org": "OBQXG43XN5ZGI4A7OBQXG43XN5ZGI4A7",
    "samuel@example.org": "NRSWG4TFOQYTEMZUNRSWG4TFOQYTEMZU",
}

# (email, full name, roles) — foundation.md §2.11.
PERSONAS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("nadia@example.org", "Nadia Pierre", (roles.ADMINISTRATOR,)),
    ("marcus@example.org", "Marcus Bell", (roles.HAM_DIRECTOR, roles.VOLUNTEER)),
    ("andre@example.org", "Andre Whitfield", (roles.ASSISTANT_DIRECTOR,)),
    ("ruth@example.org", "Ruth Alvarez", (roles.PASTOR,)),
    ("samuel@example.org", "Samuel Grant", (roles.BOARD_REPRESENTATIVE,)),
    ("luis@example.org", "Luis Romero", (roles.VOLUNTEER,)),
    ("tom@example.org", "Tom Nguyen", (roles.VOLUNTEER,)),
    ("kevin@example.org", "Kevin Thompson", (roles.VOLUNTEER,)),
    ("bayside@example.org", "Bayside Plumbing", (roles.CONTRACTOR,)),
    ("grace@example.org", "Grace Kim", (roles.SOCIAL_MEDIA_SPECIALIST,)),
)


class Command(BaseCommand):
    help = (
        "Create fictional example.org personas for local development and Playwright smoke "
        "tests (foundation.md §2.11). Refuses to run when HAM_ENV=production."
    )

    def handle(self, *args, **options):
        refuse_in_production("seed_dev")

        with transaction.atomic():
            for email, full_name, role_list in PERSONAS:
                user, created = User.objects.get_or_create(email=email)
                if created:
                    user.set_unusable_password()
                    # Dev personas sign in immediately in local smoke tests; mark them Active,
                    # not stuck Invited (real invitations go through `services.invite_user`).
                    user.first_sign_in_at = clock_now()
                    user.save()
                SharedIdentityProfile.objects.get_or_create(
                    user=user, defaults={"full_name": full_name}
                )
                for role in role_list:
                    RoleAssignment.objects.get_or_create(
                        user=user,
                        role=role,
                        scope_type=None,
                        scope_id=None,
                        revoked_at=None,
                        defaults={
                            "granted_by_id": None,
                            "granted_at": clock_now(),
                            "grant_reason": "seed_dev",
                        },
                    )
                secret = DEV_TOTP_SECRETS.get(email)
                if secret is not None:
                    now = clock_now()
                    TOTPDevice.objects.update_or_create(
                        user=user,
                        defaults={
                            "secret_encrypted": encrypt(secret),
                            "created_at": now,
                            "confirmed_at": now,
                        },
                    )
                    if not user.recovery_codes.exists():
                        mfa.regenerate_recovery_codes(user)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(PERSONAS)} example.org personas."))
        self.stdout.write(
            "Dev-only TOTP secrets (get a current code with `manage.py dev_totp <email>`):"
        )
        for email in DEV_TOTP_SECRETS:
            self.stdout.write(f"  {email}: {DEV_TOTP_SECRETS[email]}")
