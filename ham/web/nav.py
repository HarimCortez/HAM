"""Nav items for the app shell (foundation.md §2.10; navigation.md §3).

The source of truth is ``ham.authz.nav.nav_for(ctx)``: it returns only destinations the
signed-in person may use. This module keeps just the built ones for rendering. Templates
must never hard-code destinations.
"""

from __future__ import annotations

from ham.authz.context import ActorContext
from ham.authz.nav import NavItem, admin_group_items, bottom_nav_for, more_items, nav_for

__all__ = [
    "NavItem",
    "nav_items_for",
    "bottom_nav_items_for",
    "admin_group_items_for",
    "more_items_for",
]


def nav_items_for(request) -> tuple[NavItem, ...]:
    """Built nav destinations for this request's actor (empty when signed out). Used by the
    sidebar and tablet rail, which show the full set (navigation.md §3.2, §3.3)."""
    actor = getattr(request, "actor", None) or ActorContext.anonymous()
    return tuple(item for item in nav_for(actor) if item.built)


def bottom_nav_items_for(request) -> tuple[NavItem, ...]:
    """The mobile bottom nav, capped at 5 items (navigation.md §3.1, Q-091)."""
    actor = getattr(request, "actor", None) or ActorContext.anonymous()
    return tuple(item for item in bottom_nav_for(actor) if item.built)


def admin_group_items_for(request) -> tuple[NavItem, ...]:
    """The Admin index page's destinations (C2 fix note)."""
    actor = getattr(request, "actor", None) or ActorContext.anonymous()
    return tuple(item for item in admin_group_items(actor) if item.built)


def more_items_for(request) -> tuple[NavItem, ...]:
    """The More page's destinations, not counting Sign out (navigation.md §3.1)."""
    actor = getattr(request, "actor", None) or ActorContext.anonymous()
    return tuple(item for item in more_items(actor) if item.built)
