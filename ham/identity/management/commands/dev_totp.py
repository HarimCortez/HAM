"""manage.py dev_totp <email>

Prints a current, valid 6-digit TOTP code for a seeded dev persona's enrolled authenticator
(foundation.md §2.11 "a way to get a current code"). Refuses to run in production, same as
`seed_dev`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from ham.identity import totp
from ham.identity.crypto import decrypt
from ham.identity.models import TOTPDevice, User
from ham.platform.env import refuse_in_production


class Command(BaseCommand):
    help = "Print a current TOTP code for a seeded dev persona (development only)."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        refuse_in_production("dev_totp")
        email = options["email"].strip().lower()
        try:
            user = User.objects.get(email=email)
            device = TOTPDevice.objects.get(user=user, confirmed_at__isnull=False)
        except (User.DoesNotExist, TOTPDevice.DoesNotExist) as exc:
            raise CommandError(f"No enrolled two-step sign-in device for {email!r}.") from exc

        self.stdout.write(totp.current_code(decrypt(device.secret_encrypted)))
