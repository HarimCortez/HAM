"""Two repo-wide invariants from CLAUDE.md ("Design") and design-system/README.md:

1. No literal church name anywhere in templates — everything comes from the church profile
   (`{{ church.* }}`) so another church can deploy HAM with only a config change (Q-026).
2. No hard-coded hex colors outside `design-system/` — components use CSS custom properties
   (tokens) only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Real church names that must never appear as a literal string in app code (brand-notes.md,
# navigation.md header). Deliberately specific rather than "any capitalised phrase", to avoid
# false positives on generic words.
FORBIDDEN_CHURCH_STRINGS = (
    "Miami Temple",
    "Seventh-day Adventist",
)

TEMPLATE_DIRS = (BASE_DIR / "ham" / "web" / "templates",)

HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{8}\b")

# Files/dirs allowed to contain real hex colors: the design-system itself (tokens/build tool),
# and anything generated (frontend/dist, node_modules, migrations, staticfiles).
ALLOWED_HEX_DIRS = (
    BASE_DIR / "design-system",
    BASE_DIR / "frontend" / "node_modules",
    BASE_DIR / "frontend" / "dist",
    BASE_DIR / "staticfiles",
)

SCANNED_GLOBS = (
    "ham/web/templates/**/*.html",
    "ham/web/static/**/*.css",
    "frontend/src/**/*.ts",
)


def _all_scanned_files() -> list[Path]:
    files: list[Path] = []
    for pattern in SCANNED_GLOBS:
        files.extend(BASE_DIR.glob(pattern))
    return files


@pytest.mark.parametrize("template_dir", TEMPLATE_DIRS)
def test_no_literal_church_name_in_templates(template_dir):
    offenders = []
    for path in template_dir.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_CHURCH_STRINGS:
            if needle in text:
                offenders.append(f"{path.relative_to(BASE_DIR)}: contains {needle!r}")
    assert not offenders, "Literal church name in templates:\n" + "\n".join(offenders)


def test_no_hex_colors_outside_design_system():
    offenders = []
    for path in _all_scanned_files():
        if any(str(path).startswith(str(d)) for d in ALLOWED_HEX_DIRS):
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if HEX_COLOR_RE.search(line):
                offenders.append(f"{path.relative_to(BASE_DIR)}:{i}: {line.strip()}")
    assert not offenders, "Hard-coded hex color outside design-system/:\n" + "\n".join(offenders)
