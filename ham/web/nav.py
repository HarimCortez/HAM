"""Nav items for the app shell (foundation.md §2.10; navigation.md §3).

The source of truth is ``ham.authz.nav.nav_for(ctx)``: it returns only destinations the
signed-in person may use. This module keeps just the built ones for rendering. Templates
must never hard-code destinations.
"""

from __future__ import annotations

from ham.authz.context import ActorContext
from ham.authz.nav import NavItem, nav_for

__all__ = ["NavItem", "nav_items_for"]


def nav_items_for(request) -> tuple[NavItem, ...]:
    """Built nav destinations for this request's actor (empty when signed out)."""
    actor = getattr(request, "actor", None) or ActorContext.anonymous()
    return tuple(item for item in nav_for(actor) if item.built)
