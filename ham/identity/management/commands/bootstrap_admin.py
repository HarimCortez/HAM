"""manage.py bootstrap_admin --email <address>

Creates the first production Administrator (foundation.md §2.11), audited with actor
`system:bootstrap`; MFA enrollment is forced at first sign-in (§60.1). Runs in any
environment, including production — this is how the owner gets their first account.

Moved here from `ham.platform` (S1 stub) now that `ham.identity` exists (S3a): the command
belongs with the service it calls, and `ham.platform` must not import domain modules
(foundation.md §1 dependency rules — it is the bottom layer).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from ham.audit.services import record as audit_record
from ham.authz import roles
from ham.identity.models import RoleAssignment
from ham.identity.services import bootstrap_administrator


class Command(BaseCommand):
    help = "Create the first Administrator account (audited, actor=system:bootstrap)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email", required=True, help="Email address of the first Administrator."
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Security review L6: bootstrap_admin bypasses the ordinary role-grant "
                "guardrails (Q-041/Q-047: nobody self-grants; every grant is reviewed and "
                "emails all Administrators) because there is, by definition, no signed-in "
                "Administrator yet to do the granting. Once one exists, an operator running "
                "this again should go through the ordinary Users & roles screen instead — "
                "--force is the documented escape hatch for the rare case that's genuinely "
                "not possible (e.g. restoring access), and its use is audited."
            ),
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        if not email or "@" not in email:
            raise CommandError(f"{email!r} does not look like an email address.")

        existing_admins = RoleAssignment.objects.filter(
            role=roles.ADMINISTRATOR,
            revoked_at__isnull=True,
            user__is_active=True,
            user__disabled_at__isnull=True,
        ).exclude(user__email=email)
        if existing_admins.exists() and not options["force"]:
            raise CommandError(
                "An active Administrator already exists. Use the Users & roles screen to "
                "grant Administrator to a new person, or pass --force if that's genuinely not "
                "possible right now (this is audited)."
            )

        user = bootstrap_administrator(email=email)
        if existing_admins.exists():
            audit_record(
                ctx=None,
                actor_type="system",
                actor_user_id=None,
                action="user.bootstrap_admin_forced",
                target_type="user",
                target_id=str(user.id),
                context={"system_actor": "system:bootstrap", "forced": True},
            )
        self.stdout.write(self.style.SUCCESS(f"Administrator created: {user.id} <{email}>"))
