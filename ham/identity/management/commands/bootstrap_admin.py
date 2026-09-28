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

from ham.identity.services import bootstrap_administrator


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

        user = bootstrap_administrator(email=email)
        self.stdout.write(self.style.SUCCESS(f"Administrator created: {user.id} <{email}>"))
