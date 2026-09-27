"""manage.py bootstrap_admin --email <address>

Creates the first production Administrator (foundation.md §2.11), audited with actor
`system:bootstrap`; MFA enrollment is forced at first sign-in (§60.1). Runs in any
environment, including production — this is how the owner gets their first account.

Extension point for slice S3a (Identity): this command validates its input and stays thin on
purpose, deferring the actual creation to `ham.identity.services.bootstrap_administrator`,
which does not exist until User/RoleAssignment/AuditEvent land. Until then it fails with a
clear message instead of silently creating an unaudited row.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the first Administrator account (audited, actor=system:bootstrap)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email", required=True, help="Email address of the first Administrator."
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        if not email or "@" not in email:
            raise CommandError(f"{email!r} does not look like an email address.")

        try:
            from ham.identity.services import bootstrap_administrator
        except ImportError as exc:
            raise CommandError(
                "ham.identity is not installed yet (it lands in slice S3a — see "
                "docs/architecture/foundation.md §8, 'Identity, roles, policy, audit'). "
                "`bootstrap_admin` will work as soon as "
                "ham.identity.services.bootstrap_administrator(email) exists; this command "
                "already validates input and is wired into manage.py so S3a only needs to add "
                "that one function."
            ) from exc

        user = bootstrap_administrator(email=email)
        self.stdout.write(self.style.SUCCESS(f"Administrator created: {user.id} <{email}>"))
