from __future__ import annotations

from django.conf import settings

from ham.authz.docgen import render_matrix_markdown


def test_permission_matrix_doc_is_up_to_date():
    path = settings.BASE_DIR / "docs" / "architecture" / "permission-matrix.md"
    assert path.exists(), "run `python manage.py build_permission_matrix`"
    assert path.read_text() == render_matrix_markdown(), (
        "docs/architecture/permission-matrix.md is stale; run "
        "`python manage.py build_permission_matrix`"
    )
