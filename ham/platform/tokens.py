"""Read a literal hex value out of `design-system/tokens.css`, for the rare places that must
ship one instead of a CSS custom property — namely the PWA manifest, which the OS reads before
any CSS loads (S5 build note item 4). Never hand-copy a hex value into Python: read it here so
it can never drift out of sync with the design system (CLAUDE.md "Design": "tokens only, never
hard-coded colors").
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from django.conf import settings

_VAR_RE = re.compile(r"--([\w-]+):\s*(#[0-9a-fA-F]{3,8});")


@cache
def _root_hex_values() -> dict[str, str]:
    css = Path(settings.BASE_DIR, "design-system", "tokens.css").read_text(encoding="utf-8")
    # Only the light-theme `:root` block (before the first dark-theme override): V1 ships
    # light only (Q-016, design-system/README.md "Decided for V1").
    root_block = css.split('[data-theme="dark"]')[0]
    return dict(_VAR_RE.findall(root_block))


def token_hex(name: str) -> str:
    """Resolve a primitive color token (e.g. ``"ham-color-neutral-950"``) to its literal hex
    value. Raises ``KeyError`` for anything that isn't a plain hex primitive (most semantic
    tokens are ``var(...)`` aliases, which is the point: resolve to the primitive instead)."""
    return _root_hex_values()[name]
