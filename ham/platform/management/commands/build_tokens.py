"""manage.py build_tokens [--brand <id>] [--check]

Thin wrapper around `design-system/tools/build_tokens.py` (design-system/README.md), so the
token build is one command whether it is run by a developer, CI, or a Render build hook.
Defaults `--brand` to `settings.HAM_BRAND` so a deployment never has to remember which brand
it is (Q-026).
"""

from __future__ import annotations

import subprocess
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Build design-system/tokens.css for the active (or given) brand."

    def add_arguments(self, parser):
        parser.add_argument("--brand", default=None, help="Defaults to settings.HAM_BRAND.")
        parser.add_argument(
            "--check", action="store_true", help="Fail if any required contrast pair fails AA."
        )

    def handle(self, *args, **options):
        brand = options["brand"] or settings.HAM_BRAND
        script = settings.BASE_DIR / "design-system" / "tools" / "build_tokens.py"
        cmd = [sys.executable, str(script), "--brand", brand]
        if options["check"]:
            cmd.append("--check")
        result = subprocess.run(cmd, cwd=settings.BASE_DIR)
        if result.returncode != 0:
            raise CommandError(
                f"Token build failed for brand {brand!r} (exit {result.returncode})."
            )
        self.stdout.write(self.style.SUCCESS(f"tokens.css built for brand {brand!r}."))
