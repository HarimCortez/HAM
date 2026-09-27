"""HAM's versioned business rules (PRD §34, §76; foundation.md §5).

Usage::

    from ham.rules import RULES, RULES_VERSION
    deadline = invited_at + RULES.staffing.INVITATION_RESPONSE_WINDOW

Record ``RULES_VERSION`` on audit events and reliability score changes.
Pure Python: never import Django here.
"""

from .fingerprint import content_hash
from .types import CalendarYears, Pending, RuleNotDecidedError
from .v1 import (
    CANCELLATION_BAND_CODES,
    RULES,
    RULES_VERSION,
    Rules,
    cancellation_band,
    check_invariants,
    check_reliability_penalties,
    iter_rules,
)
from .view import RuleRow, RulesView, rules_view

RULES_HASH = content_hash(RULES)

__all__ = [
    "CANCELLATION_BAND_CODES",
    "RULES",
    "RULES_HASH",
    "RULES_VERSION",
    "CalendarYears",
    "Pending",
    "RuleNotDecidedError",
    "RuleRow",
    "Rules",
    "RulesView",
    "cancellation_band",
    "check_invariants",
    "check_reliability_penalties",
    "content_hash",
    "iter_rules",
    "rules_view",
]
