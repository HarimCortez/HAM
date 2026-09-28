"""Home/Inbox attention cards for requests (intake.md §6 "Attention providers"; navigation.md
§8.3 group 4).

`ham.notifications` owns the attention-provider *registry* (intake.md §2), but is still an
empty seam in this slice (S2.5 runs in parallel and may not have landed the registry yet in
any given worktree) -- `ham.requests.apps.RequestsConfig.ready()` registers these functions
with it **if it's there** (the same "guarded, since it may still be a stub" pattern
wave2-common.md uses for `issue_link`). The functions themselves have no dependency on the
registry existing, so `ham.requests`' own tests can call them directly.

Attention rows never carry P or C fields (intake.md §7 "ID + category only", Q-132) -- these
are exactly `RequestListRow`, not the detail row.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from ham.authz import roles
from ham.platform.clock import now as clock_now

from .queries import (
    RequestListRow,
    can_see_needs_phone_check,
    list_requests,
    needs_phone_check_list,
)
from .states import RequestStatus

if TYPE_CHECKING:
    from ham.authz.context import ActorContext

_PAS_BRD = frozenset({roles.PASTOR, roles.BOARD_REPRESENTATIVE})
_DIR_AD = frozenset({roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR})


@dataclasses.dataclass(frozen=True, slots=True)
class AttentionCard:
    key: str
    title: str
    count: int
    urgent: bool
    actionable: bool  # False = "owner: pastors/Board" muted row (navigation.md §8.3 group 4)
    href: str
    oldest_waiting_hours: float | None = None


def _oldest_waiting_hours(rows: list[RequestListRow]) -> float | None:
    if not rows:
        return None
    oldest = min(r.submitted_at for r in rows)
    return (clock_now() - oldest).total_seconds() / 3600


def awaiting_approval_card(ctx: ActorContext) -> AttentionCard | None:
    """ "Waiting for a decision (n)", urgent first -- actionable for Pastor/Board rep,
    awareness-only ("owner: pastors/Board") for Director/AD (intake.md §6)."""
    if not (ctx.effective_roles & (_PAS_BRD | _DIR_AD)):
        return None
    rows = [r for r in list_requests(ctx, status=RequestStatus.AWAITING_APPROVAL.value)]
    if not rows:
        return None
    return AttentionCard(
        key="requests.awaiting_approval",
        title=f"Waiting for a decision ({len(rows)})",
        count=len(rows),
        urgent=any(r.urgent_requested for r in rows),
        actionable=bool(ctx.effective_roles & _PAS_BRD),
        href="/requests?status=AWAITING_APPROVAL",
    )


def needs_phone_check_card(ctx: ActorContext) -> AttentionCard | None:
    """Q-025: "{n} requests need a phone check · oldest waiting {age}", Director/AD only."""
    if not can_see_needs_phone_check(ctx):
        return None
    rows = needs_phone_check_list(ctx)
    if not rows:
        return None
    return AttentionCard(
        key="requests.needs_phone_check",
        title=f"{len(rows)} request(s) need a phone check",
        count=len(rows),
        urgent=any(r.urgent_requested for r in rows),
        actionable=True,
        href="/requests/new-by-phone",
        oldest_waiting_hours=_oldest_waiting_hours(rows),
    )


def attention_cards(ctx: ActorContext) -> list[AttentionCard]:
    """Everything `ham.requests` contributes to Home/Inbox "Needs your attention" -- computed
    live (navigation.md: "resolving an item anywhere clears it everywhere"), never stored."""
    cards = [awaiting_approval_card(ctx), needs_phone_check_card(ctx)]
    return [c for c in cards if c is not None]


def register(register_attention_provider) -> None:
    """Called by `RequestsConfig.ready()` with `ham.notifications`'s registration function,
    if that module has actually landed one yet."""
    register_attention_provider("requests", attention_cards)
