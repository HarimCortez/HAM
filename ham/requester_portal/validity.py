"""Requester access-link validity (PRD §7.3; Q-116, Q-117, Q-025). Rules-owned, pure.

Computed when a link is read, from the request's status and timestamps, so "auto-invalidate
old requester access links" (§76) needs no job: issuing a link revokes the previous one in
the same transaction (``revoked_at``), and expiry is arithmetic on the clock passed in.

- Normal access (the initial link) lasts while the request is open and ends
  ``REQUESTER_LINK_VALID_AFTER_COMPLETION`` (7 days) after project completion (§7.3), or
  ``REQUESTER_ACCESS_AFTER_CLOSE`` (7 days) after a close without completion: Cancelled,
  Not Executable or a final rejection (Q-116, proposed default in use).
- A link regenerated AFTER normal access ended lasts ``REGENERATED_REQUESTER_LINK_LIFETIME``
  (14 days) from issue (§7.3).
- A link regenerated BEFORE normal access ended (a lost link) follows the normal rule
  (Q-117, proposed default in use; ``EARLY_REGENERATED_LINK_FOLLOWS_NORMAL_ACCESS``).
- Requests in NEEDS_PHONE_CHECK ("I don't use email", Q-025) have no link access at all.

Boundaries: a link is valid while ``now < valid_until``; at exactly ``valid_until`` it has
expired. A link issued at exactly the moment normal access ends counts as issued after it.
All datetimes must be timezone-aware (UTC in storage, §70.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ham.requests.states import (
    PHONE_CHECK_STATUSES,
    PRE_DECISION_STATUSES,
    TERMINAL_STATUSES,
    RequestStatus,
)
from ham.rules import RULES, Rules


# PRD-GAP Q-116, Q-117: proposed defaults in use (values/switch in ham.rules); owner may change.
class LinkKind(StrEnum):
    INITIAL = "initial"
    REGENERATED = "regenerated"


class LinkState(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"  # real link, time ran out: offer "send me a new link"
    REVOKED = "revoked"  # superseded by a newer link, or the request was anonymized
    NO_ACCESS = "no_access"  # the request has no link access (Q-025 phone-check requests)


@dataclass(frozen=True, slots=True)
class LinkValidity:
    state: LinkState
    # When the link stops working; None = no end yet (the request is still open).
    valid_until: datetime | None

    @property
    def is_valid(self) -> bool:
        return self.state is LinkState.VALID


def _aware(name: str, value: datetime | None) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} must be timezone-aware (UTC)")


# Request statuses that can never carry a close. APPROVED may (its project later completes
# or closes; project id = request id) and REJECTED may (final after reconsideration).
_ALWAYS_OPEN = PRE_DECISION_STATUSES | {RequestStatus.RECONSIDERATION_PENDING}


def _known_status(status: str) -> RequestStatus | None:
    try:
        return RequestStatus(status)
    except ValueError:
        return None  # a later-step project status (e.g. COMPLETED, NOT_EXECUTABLE)


def normal_access_ends_at(
    *,
    status: RequestStatus | str,
    closed_at: datetime | None,
    completed_at: datetime | None = None,
    rules: Rules = RULES,
) -> datetime | None:
    """When the normal (initial) link stops working; None while the request is open.

    ``closed_at`` is set only when the request is finally closed (a rejection that can
    still be reconsidered is not closed, Q-116). ``completed_at`` is the project completion
    time (§7.3) and takes precedence. Raises ``ValueError`` if status and timestamps
    disagree, rather than guessing.
    """
    _aware("closed_at", closed_at)
    _aware("completed_at", completed_at)
    ra = rules.requester_access
    known = _known_status(str(status))
    if known in TERMINAL_STATUSES and closed_at is None:
        raise ValueError(f"a {known} request must have closed_at")
    if known in _ALWAYS_OPEN and (closed_at is not None or completed_at is not None):
        raise ValueError(f"an open {known} request cannot have closed_at/completed_at")
    if completed_at is not None:
        return completed_at + ra.REQUESTER_LINK_VALID_AFTER_COMPLETION
    if closed_at is not None:
        return closed_at + ra.REQUESTER_ACCESS_AFTER_CLOSE
    return None


def fixed_expiry(
    *,
    kind: LinkKind | str,
    issued_at: datetime,
    access_ends_at: datetime | None,
    rules: Rules = RULES,
) -> datetime | None:
    """The link's own fixed end (store it as ``RequesterAccessLink.expires_at``), or None
    when the link simply follows normal access."""
    _aware("issued_at", issued_at)
    _aware("access_ends_at", access_ends_at)
    if LinkKind(kind) is LinkKind.INITIAL:
        return None
    ra = rules.requester_access
    issued_after_end = access_ends_at is not None and issued_at >= access_ends_at
    if issued_after_end or not ra.EARLY_REGENERATED_LINK_FOLLOWS_NORMAL_ACCESS:
        return issued_at + ra.REGENERATED_REQUESTER_LINK_LIFETIME
    return None


def link_validity(
    *,
    kind: LinkKind | str,
    issued_at: datetime,
    revoked_at: datetime | None,
    status: RequestStatus | str,
    closed_at: datetime | None,
    completed_at: datetime | None = None,
    now: datetime,
    rules: Rules = RULES,
) -> LinkValidity:
    """Is this link usable at ``now``? Pure; pass the injected clock's ``now``."""
    _aware("issued_at", issued_at)
    _aware("revoked_at", revoked_at)
    _aware("now", now)
    known = _known_status(str(status))
    if known in PHONE_CHECK_STATUSES:
        return LinkValidity(LinkState.NO_ACCESS, None)

    ends = normal_access_ends_at(
        status=status, closed_at=closed_at, completed_at=completed_at, rules=rules
    )
    fixed = fixed_expiry(kind=kind, issued_at=issued_at, access_ends_at=ends, rules=rules)
    valid_until = fixed if fixed is not None else ends

    if revoked_at is not None:
        return LinkValidity(LinkState.REVOKED, valid_until)
    if valid_until is not None and now >= valid_until:
        return LinkValidity(LinkState.EXPIRED, valid_until)
    return LinkValidity(LinkState.VALID, valid_until)


def may_self_regenerate(status: RequestStatus | str) -> bool:
    """A requester may ask for a new link by email (§7.3, Q-117) unless the request has no
    email at all (Q-025 phone-check requests are updated by phone)."""
    return _known_status(str(status)) not in PHONE_CHECK_STATUSES
