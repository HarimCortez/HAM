"""Value types used by the rules module.

Pure Python, no Django. Everything here is immutable.

Units, so nobody has to guess:
- ``datetime.timedelta``: elapsed time measured on the UTC clock (e.g. "48 hours before start").
- ``CalendarYears``: calendar-year retention periods (e.g. "seven years"). A timedelta of
  7 * 365 days would drop leap days and delete legal records up to two days early, so
  years are added on the calendar instead.
- plain ``int`` fields carry their unit in the rule's metadata (``unit=``).
- ``Pending``: a value the product owner has not decided yet. Any attempt to *use* it raises
  ``RuleNotDecidedError`` so undecided behaviour can never ship silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, NoReturn, TypeVar

_D = TypeVar("_D", date, datetime)


class RuleNotDecidedError(RuntimeError):
    """Raised when code tries to use a rule value that is still an open PRD question."""


@dataclass(frozen=True, slots=True)
class CalendarYears:
    """A retention period of whole calendar years.

    ``after(start)`` returns the first instant/date on which the period has fully elapsed.
    A start on 29 February rolls forward to 1 March, so a record is never purged early.
    """

    years: int

    def __post_init__(self) -> None:
        if isinstance(self.years, bool) or not isinstance(self.years, int) or self.years < 0:
            raise ValueError(f"CalendarYears needs a non-negative int, got {self.years!r}")

    def after(self, start: _D) -> _D:
        target_year = start.year + self.years
        try:
            return start.replace(year=target_year)
        except ValueError:
            # 29 Feb -> target year has no 29 Feb. Round UP to 1 March (never under-retain).
            return start.replace(year=target_year, month=3, day=1)


class Pending:
    """Placeholder for an undecided rule value (``PRD-GAP``).

    It can be displayed (``str``/``repr``) and hashed, but any arithmetic, comparison with a
    real value, truth test or numeric conversion raises ``RuleNotDecidedError``.
    """

    __slots__ = ("question", "proposal")

    question: str
    proposal: str

    def __init__(self, question: str, proposal: str) -> None:
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "proposal", proposal)

    def __setattr__(self, name: str, value: Any) -> NoReturn:
        raise AttributeError("Pending is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError("Pending is immutable")

    def _refuse(self, *_args: Any, **_kwargs: Any) -> NoReturn:
        raise RuleNotDecidedError(
            f"This rule value is not decided yet (PRD-GAP {self.question}). "
            f"Proposed: {self.proposal}. The product owner must decide it and the rules "
            "version must be bumped before it can be used."
        )

    # Truth tests and conversions.
    __bool__ = _refuse
    __int__ = _refuse
    __float__ = _refuse
    __index__ = _refuse
    __round__ = _refuse
    __abs__ = _refuse
    __neg__ = _refuse
    __pos__ = _refuse
    # Arithmetic (both sides, so ``timedelta + Pending`` and ``5 - Pending`` also raise).
    __add__ = __radd__ = _refuse
    __sub__ = __rsub__ = _refuse
    __mul__ = __rmul__ = _refuse
    __truediv__ = __rtruediv__ = _refuse
    __floordiv__ = __rfloordiv__ = _refuse
    __mod__ = __rmod__ = _refuse
    # Ordering.
    __lt__ = __le__ = __gt__ = __ge__ = _refuse
    # Container-style use.
    __iter__ = _refuse
    __len__ = _refuse
    __getitem__ = _refuse
    __contains__ = _refuse

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Pending):
            return self.question == other.question
        self._refuse()

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(("Pending", self.question))

    def __repr__(self) -> str:
        return f"Pending({self.question!r})"

    def __str__(self) -> str:
        return f"Not decided yet ({self.question})"


def contains_pending(value: object) -> bool:
    """True if ``value`` is, or (in a tuple) contains, a ``Pending`` placeholder."""
    if isinstance(value, Pending):
        return True
    if isinstance(value, tuple):
        return any(contains_pending(v) for v in value)
    return False


def pending_questions(value: object) -> tuple[str, ...]:
    """The Q-ids of all ``Pending`` placeholders inside ``value``."""
    if isinstance(value, Pending):
        return (value.question,)
    if isinstance(value, tuple):
        out: list[str] = []
        for v in value:
            out.extend(pending_questions(v))
        return tuple(out)
    return ()
