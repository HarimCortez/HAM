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

from .presentation import need_category_label
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


def awaiting_approval_cards(ctx: ActorContext) -> list[AttentionCard]:
    """ "Waiting for a decision" -- actionable for Pastor/Board rep, awareness-only ("owner:
    pastors/Board") for Director/AD (intake.md §6).

    Visual QA M17: an aggregate card that says "Urgent" on the whole group is wrong when only
    some of the requests are urgent, so each urgent + actionable request gets its own card
    ("Urgent · HAM #048 · Plumbing or water", `Open` to that request directly); the rest stay
    one aggregate card ("N requests are waiting for a decision"). The muted Director/AD
    awareness row is never split and never carries the urgent flag/chip -- it's not
    actionable, so a danger chip on it would be a false alarm (visual QA M17 "mixed signal").
    Cards never carry more than HAM # + category (intake.md §7, Q-132)."""
    if not (ctx.effective_roles & (_PAS_BRD | _DIR_AD)):
        return []
    rows = list_requests(ctx, status=RequestStatus.AWAITING_APPROVAL.value)
    if not rows:
        return []

    actionable = bool(ctx.effective_roles & _PAS_BRD)
    if not actionable:
        # Director/AD: one muted awareness row, never urgent-flagged (M17).
        return [
            AttentionCard(
                key="requests.awaiting_approval",
                title=f"Waiting for a decision ({len(rows)})",
                count=len(rows),
                urgent=False,
                actionable=False,
                href="/requests?status=AWAITING_APPROVAL",
            )
        ]

    urgent_rows = [r for r in rows if r.urgent_requested]
    other_rows = [r for r in rows if not r.urgent_requested]
    # FIX-F1 minor 1: cap at MAX_URGENT_CARDS individual cards; any further urgent rows fold
    # into a single "N more urgent" card instead of a long column of primary buttons.
    shown_urgent, extra_urgent = (
        urgent_rows[:MAX_URGENT_CARDS],
        urgent_rows[MAX_URGENT_CARDS:],
    )
    cards = [
        AttentionCard(
            key=f"requests.awaiting_approval.{row.id}",
            title=(
                f"{row.display_number} · {need_category_label(row.need_category)} · "
                f"{_waiting_words((clock_now() - row.submitted_at).total_seconds() / 3600)}"
            ),
            count=1,
            urgent=True,
            actionable=True,
            href=f"/requests/{row.id}",
        )
        for row in shown_urgent
    ]
    if extra_urgent:
        cards.append(
            AttentionCard(
                key="requests.awaiting_approval.more_urgent",
                title=f"{len(extra_urgent)} more urgent",
                count=len(extra_urgent),
                urgent=True,
                actionable=True,
                href="/requests?status=AWAITING_APPROVAL",
            )
        )
    if other_rows:
        cards.append(
            AttentionCard(
                key="requests.awaiting_approval",
                title=f"{len(other_rows)} request{'s' if len(other_rows) != 1 else ''} "
                f"{'are' if len(other_rows) != 1 else 'is'} waiting for a decision",
                count=len(other_rows),
                urgent=False,
                actionable=True,
                href="/requests?status=AWAITING_APPROVAL",
            )
        )
    return cards


MAX_URGENT_CARDS = 3
"""FIX-F1 minor 1 (step2-ui-visual-qa.md): a UI display cap, not a business rule (nothing in
`ham.rules` governs how many attention cards render) -- with a lot of urgent awaiting-approval
requests at once, one card per request broke the "one primary action" pattern (a column of
solid-primary "Open" buttons). Past this many, the rest fold into one "N more urgent" card."""


def _waiting_words(hours: float | None) -> str:
    """Like `_oldest_waiting_words`, but for a single request's own age (no "oldest ").

    FIX-H polish: a non-breaking space between the number and its unit so "1 h"/"3 days"
    never splits across lines on the Pastor Home cards (a plain string, not a template, so the
    fix lives here rather than as CSS `white-space: nowrap`, which would also stop the rest of
    a longer title from wrapping)."""
    if hours is None:
        return ""
    if hours < 1:
        return "waiting under 1 h"
    if hours < 24:
        return f"waiting {round(hours)} h"
    days = round(hours / 24)
    return f"waiting {days} day" if days == 1 else f"waiting {days} days"


def _plural_verb_phrase(n: int) -> str:
    """M17: "1 request needs a phone check" / "7 requests need a phone check" -- not the
    grammatically-null "request(s)"."""
    return f"{n} request needs a phone check" if n == 1 else f"{n} requests need a phone check"


def _oldest_waiting_words(hours: float | None) -> str:
    """FIX-H polish: same non-breaking-space treatment as `_waiting_words`."""
    if hours is None:
        return ""
    if hours < 1:
        return "oldest waiting under 1 h"
    if hours < 24:
        return f"oldest waiting {round(hours)} h"
    days = round(hours / 24)
    return f"oldest waiting {days} day" if days == 1 else f"oldest waiting {days} days"


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
    cards = [*awaiting_approval_cards(ctx)]
    phone_check = needs_phone_check_card(ctx)
    if phone_check is not None:
        cards.append(phone_check)
    return cards


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
