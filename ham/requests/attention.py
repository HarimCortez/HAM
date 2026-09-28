"""Home/Inbox attention cards for requests (intake.md §6 "Attention providers"; navigation.md
§8.3 group 4).

`ham.notifications.attention` owns the registry (S2.5, merged): `register_attention_provider`
takes one `Callable[[ctx], list[AttentionItem]]`, keyed only by identity (no string key).
`RequestsConfig.ready()` registers `provide_attention_items` below -- `ham.requests` sits
*above* `ham.notifications` in the layer order, so this is an ordinary downward import, not
the guarded pattern `issue_link` needed (that one pointed the wrong way; see this module's
sibling `services.py` docstring for the full explanation of that distinction).

`attention_cards`/`AttentionCard` are this module's own richer shape (kept for its own tests,
e.g. `oldest_waiting_hours`); `provide_attention_items` adapts each `AttentionCard` to
`ham.notifications.attention.AttentionItem` (`kind`/`title`/`url`/`count`/`urgent`/`muted`) at
the registry boundary.

Attention rows never carry P or C fields (intake.md §7 "ID + category only", Q-132) -- these
are exactly `RequestListRow`, not the detail row.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from ham.authz import roles
from ham.notifications.attention import AttentionItem
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


def _plural_verb_phrase(n: int) -> str:
    """M17: "1 request needs a phone check" / "7 requests need a phone check" -- not the
    grammatically-null "request(s)"."""
    return f"{n} request needs a phone check" if n == 1 else f"{n} requests need a phone check"


def _oldest_waiting_words(hours: float | None) -> str:
    if hours is None:
        return ""
    if hours < 1:
        return "oldest waiting under 1 h"
    if hours < 24:
        return f"oldest waiting {round(hours)} h"
    days = round(hours / 24)
    return f"oldest waiting {days} day" if days == 1 else f"oldest waiting {days} days"


def needs_phone_check_card(ctx: ActorContext) -> AttentionCard | None:
    """Q-025: "{n} requests need a phone check · oldest waiting {age}", Director/AD only."""
    if not can_see_needs_phone_check(ctx):
        return None
    rows = needs_phone_check_list(ctx)
    if not rows:
        return None
    oldest_hours = _oldest_waiting_hours(rows)
    context = _oldest_waiting_words(oldest_hours)
    title = _plural_verb_phrase(len(rows))
    if context:
        title = f"{title} · {context}"
    return AttentionCard(
        key="requests.needs_phone_check",
        title=title,
        count=len(rows),
        urgent=any(r.urgent_requested for r in rows),
        actionable=True,
        href="/requests/new-by-phone",
        oldest_waiting_hours=oldest_hours,
    )


def attention_cards(ctx: ActorContext) -> list[AttentionCard]:
    """Everything `ham.requests` contributes to Home/Inbox "Needs your attention" -- computed
    live (navigation.md: "resolving an item anywhere clears it everywhere"), never stored."""
    cards = [awaiting_approval_card(ctx), needs_phone_check_card(ctx)]
    return [c for c in cards if c is not None]


def provide_attention_items(ctx: ActorContext) -> list[AttentionItem]:
    """The `AttentionProvider` callable registered with `ham.notifications.attention`."""
    return [
        AttentionItem(
            kind=card.key,
            title=card.title,
            url=card.href,
            count=card.count,
            urgent=card.urgent,
            muted=not card.actionable,
        )
        for card in attention_cards(ctx)
    ]


def register() -> None:
    """Called once by `RequestsConfig.ready()`."""
    from ham.notifications.attention import register_attention_provider

    register_attention_provider(provide_attention_items)
