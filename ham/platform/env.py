"""Environment guards shared by management commands.

Any command that creates fictional or dev-only data (the future `seed_dev`, and any fixture
loader) must call `refuse_in_production()` first (foundation.md §2.11: "It refuses to run when
`HAM_ENV=production`."). `bootstrap_admin` is the one production-safe exception — it does the
opposite check via `require_production_or_dev` where relevant.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import CommandError


def is_production() -> bool:
    return settings.HAM_ENV == "production"


def refuse_in_production(command_name: str) -> None:
    """Raise CommandError if running against a production environment.

    Use at the top of `handle()` in any seed/fixture command:
        from ham.platform.env import refuse_in_production
        def handle(self, *a, **o):
            refuse_in_production(self.__class__.__module__.rsplit(".", 1)[-1])
    """
    if is_production():
        raise CommandError(
            f"`{command_name}` refuses to run when HAM_ENV=production (foundation.md §2.11). "
            "This command creates fictional or dev-only data and must never touch a real "
            "congregation's database."
        )
