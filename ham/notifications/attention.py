"""The attention-provider registry (intake.md §3 "Notification": "'Needs response' is not
stored. It is computed live by attention providers, so resolving an item anywhere clears it
everywhere", navigation.md §4).

A domain module (e.g. `ham.requests` for "Waiting for a decision") registers a provider
function here, from its own `AppConfig.ready()`. Home renders every actionable item across all
providers as a card; the Inbox's "Needs response" section renders the same items as a list —
both call `attention_items_for(ctx)` so there is exactly one place that decides what still needs
someone's action.

No provider is registered by this slice (S2.5 owns only the mechanism; S2.2 registers the first
real one for requests awaiting approval, intake.md §6 "Attention providers").
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

AttentionProvider = Callable[..., "list[AttentionItem]"]


@dataclass(frozen=True, slots=True)
class AttentionItem:
    """One row for Home's attention cards / the Inbox "Needs response" section.

    `title` must be PII-free (§68) — the same rule as `Notification.title` and outbox
    payloads: a provider resolves counts/labels only ("Waiting for a decision (3)"), never a
    requester/volunteer name or contact detail.

    `muted`: intake.md §6 "DIR, AD: the same rows, muted as 'owner: pastors/Board', excluded
    from counts" (navigation.md §8.3 group 4) — still shown, but the badge count and primary
    styling belong to whichever role actually owns resolving it.
    """

    kind: str
    title: str
    url: str
    count: int = 1
    urgent: bool = False
    muted: bool = False


_providers: list[AttentionProvider] = []


def register_attention_provider(provider: AttentionProvider) -> None:
    """A later module calls this once, from its own `AppConfig.ready()`. Registering the same
    callable twice is a caller bug, not guarded against here (mirrors `ham.outbox.registry`
    keying by identity — providers are simple functions, not keyed by event type)."""
    if provider not in _providers:
        _providers.append(provider)


def unregister_attention_provider(provider: AttentionProvider) -> None:
    """Test-only: undo a single `register_attention_provider` call."""
    if provider in _providers:
        _providers.remove(provider)


def attention_items_for(ctx: object) -> list[AttentionItem]:
    """Every actionable item across every registered provider, for `ctx` (an `ActorContext`).
    A provider that has nothing for this actor returns an empty list; a provider raising is a
    bug in that provider, not swallowed here, so it surfaces during development/tests rather
    than silently hiding a card."""
    items: list[AttentionItem] = []
    for provider in _providers:
        items.extend(provider(ctx))
    return items
