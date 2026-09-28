"""Renders ``docs/architecture/permission-matrix.md`` from ``ham.authz.matrix.MATRIX``
(foundation.md §4 "generated ... checked in CI for staleness, like `build_tokens --check`").
"""

from __future__ import annotations

from .matrix import MATRIX, Scope
from .roles import ROLE_LABELS

_HEADER = """# HAM permission matrix

Generated from `ham/authz/matrix.py` — the single source of truth (PRD §67, §68, Q-038: fixed
in code, never Admin-editable). Do not hand-edit this file; run
`python manage.py build_permission_matrix` after changing the matrix, and
`python manage.py build_permission_matrix --check` fails CI if this file is stale.

SU = requires a fresh step-up (Q-010, Q-031, Q-046). IB = refused while impersonating (§59).

| Action | Allowed roles | Scope | SU | IB | PRD |
|---|---|---|---|---|---|
"""


def _role_cell(rule) -> str:
    if not rule.allowed_roles:
        return "_(none yet)_"
    return ", ".join(ROLE_LABELS.get(r, r) for r in sorted(rule.allowed_roles))


def render_matrix_markdown() -> str:
    rows = []
    for action in sorted(MATRIX):
        rule = MATRIX[action]
        scope = "self" if rule.scope is Scope.SELF else rule.scope.value
        su = "SU" if rule.step_up else ""
        ib = "IB" if rule.blocked_while_impersonating else ""
        prd = ", ".join(rule.prd)
        rows.append(f"| `{action}` | {_role_cell(rule)} | {scope} | {su} | {ib} | {prd} |")
    return _HEADER + "\n".join(rows) + "\n"
