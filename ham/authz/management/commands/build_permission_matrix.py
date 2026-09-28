"""manage.py build_permission_matrix [--check]

Regenerates `docs/architecture/permission-matrix.md` from `ham.authz.matrix.MATRIX`
(foundation.md §4). `--check` (used in CI) fails if the checked-in file is stale, mirroring
`build_tokens --check`.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ham.authz.docgen import render_matrix_markdown


class Command(BaseCommand):
    help = "Generate docs/architecture/permission-matrix.md from ham.authz.matrix."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check", action="store_true", help="Fail if the checked-in file is stale."
        )

    def handle(self, *args, **options):
        content = render_matrix_markdown()
        path = settings.BASE_DIR / "docs" / "architecture" / "permission-matrix.md"
        if options["check"]:
            current = path.read_text() if path.exists() else None
            if current != content:
                raise CommandError(
                    "docs/architecture/permission-matrix.md is stale; run "
                    "`python manage.py build_permission_matrix`."
                )
            self.stdout.write(self.style.SUCCESS("permission-matrix.md is up to date."))
            return
        path.write_text(content)
        self.stdout.write(self.style.SUCCESS(f"Wrote {path}"))
