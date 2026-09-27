"""Data provider for the read-only Admin "Rules" screen (action ``rules.view``, foundation §7).

Returns plain, immutable, human-labelled rows. No values are editable (PRD §34, §76).
Authorization is the caller's job (``authz`` guards ``GET /admin/rules``); this module
contains no personal data, only fixed rule values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .fingerprint import content_hash
from .types import CalendarYears, Pending, contains_pending, pending_questions
from .v1 import RULES, RULES_VERSION, Rules, iter_rules

ROLE_LABELS = {
    "ADMINISTRATOR": "Administrator",
    "HAM_DIRECTOR": "HAM Director",
    "ASSISTANT_DIRECTOR": "Assistant Director",
    "PASTOR": "Pastor",
    "BOARD_REPRESENTATIVE": "Board representative",
}

STEP_UP_ACTION_LABELS = {
    "role.grant_global": "Give someone a role",
    "role.revoke_global": "Remove someone's role",
    "audit.export": "Export the audit log",
    "user.mfa_reset": "Reset someone's two-step sign-in",
    "impersonation.start": "Start troubleshooting as another user",
    "me.recovery_codes.regenerate": "Make new recovery codes",
    "me.sign_in_email.change": "Change sign-in email",
}


@dataclass(frozen=True, slots=True)
class RuleRow:
    group: str  # human group heading, e.g. "Reliability score"
    key: str  # stable code, e.g. "staffing.INVITATION_RESPONSE_WINDOW"
    label: str  # plain-language description
    value: str  # human-readable value, e.g. "48 hours"
    sources: tuple[str, ...]  # e.g. ("PRD §28", "Q-002")
    decided: bool
    pending_questions: tuple[str, ...]  # Q-ids still open for this row
    note: str


@dataclass(frozen=True, slots=True)
class RulesView:
    version: str
    content_hash: str
    rows: tuple[RuleRow, ...]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def format_duration(td: timedelta) -> str:
    """Whole days from 7 days up ("30 days"); shorter spans in hours ("48 hours", as the PRD
    words them), then minutes, then seconds."""
    total = int(td.total_seconds())
    if td != timedelta(seconds=total):
        raise ValueError("sub-second durations are not used by HAM rules")
    if total >= 7 * 86_400 and total % 86_400 == 0:
        return _plural(total // 86_400, "day")
    for size, word in ((3_600, "hour"), (60, "minute")):
        if total and total % size == 0:
            return _plural(total // size, word)
    return _plural(total, "second")


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def format_value(value: object, unit: str = "", key: str = "", unit_one: str = "") -> str:
    if isinstance(value, Pending):
        return f"Not decided yet: waiting for the product owner ({value.question})"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, timedelta):
        return format_duration(value)
    if isinstance(value, CalendarYears):
        return _plural(value.years, "year")
    if key.endswith("MFA_REQUIRED_ROLES") and isinstance(value, tuple):
        return _join([ROLE_LABELS.get(str(v), str(v)) for v in value])
    if key.endswith("STEP_UP_ACTIONS") and isinstance(value, tuple):
        return _join([STEP_UP_ACTION_LABELS.get(a, a) for a, _kind in value])
    if isinstance(value, tuple):
        text = _join([str(v) for v in value])
        return f"{text} {unit}".strip()
    if isinstance(value, int):
        if value == 1 and unit_one:
            unit = unit_one
        return f"{value} {unit}".strip()
    return str(value)


def rules_view(rules: Rules = RULES, version: str = RULES_VERSION) -> RulesView:
    """Every rule as a read-only, human-labelled row, in declaration order."""
    rows: list[RuleRow] = []
    for gf, rf, value in iter_rules(rules):
        meta = rf.metadata
        key = f"{gf.name}.{rf.name}"
        rows.append(
            RuleRow(
                group=gf.metadata["label"],
                key=key,
                label=meta["label"],
                value=format_value(value, meta.get("unit", ""), key, meta.get("unit_one", "")),
                sources=tuple(meta["sources"]),
                decided=not contains_pending(value),
                pending_questions=pending_questions(value),
                note=meta.get("note", ""),
            )
        )
    return RulesView(version=version, content_hash=content_hash(rules), rows=tuple(rows))
