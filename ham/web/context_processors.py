"""Makes the app shell's nav available to every template (foundation.md §7 "S5 ... nav from
``nav_for``"). See `ham.web.nav` for where the items actually come from.
"""

from __future__ import annotations

import uuid

from ham.web.nav import bottom_nav_items_for, nav_items_for


def shell(request):
    """Context processor: ``nav_items`` (full sidebar/rail set) and ``bottom_nav_items`` (the
    5-item-max mobile set, navigation.md §3.1, Q-091) for the shell templates, plus which one
    (if any) is the current page, so templates can set ``aria-current="page"`` (§3.3).

    Also resolves ``impersonation_target_full_name``: `ActorContext.target_display_name` is
    the short "Kevin T." form used elsewhere (`SharedIdentityProfile.display_name`), but the
    banner (auth-and-access.md I2) specifically wants the full name (visual QA M9). Looking
    this up here — instead of changing what `ActorContext` carries — keeps the fix inside
    `ham.web`, since `ham/identity/*` is owned by the parallel auth work in this slice."""
    actor = getattr(request, "actor", None)
    impersonation_target_full_name = ""
    if actor is not None and actor.is_impersonating and actor.user_id is not None:
        # `display_names_for` gives the short "Kevin T." form (used everywhere else, e.g. the
        # audit log); `get_user_detail(...).display_name` is the one existing read that
        # returns the *full* name, which is what the banner specifically wants (visual QA M9).
        from ham.identity.services import get_user_detail

        detail = get_user_detail(actor.user_id)
        if detail is not None:
            impersonation_target_full_name = detail.display_name
    # S2.8 (PRD §10/§35, Q-123): the app-wide urgent banner — an unacknowledged, ack-required
    # notification for this person — needs to show on every signed-in page, not only Home/
    # Inbox, so it lives here rather than being threaded through every view's context.
    urgent_banner = None
    urgent_banner_count = 0
    if (
        actor is not None
        and actor.is_authenticated
        # A handful of unit tests build a bare `ActorContext` with a placeholder string
        # `user_id` (e.g. "u1") to exercise the route guard in isolation, never through a real
        # request/render cycle; guard against that shape here too, not only a real UUID.
        and isinstance(getattr(actor, "user_id", None), uuid.UUID)
    ):
        from ham.notifications.services import urgent_banner_count_for, urgent_banner_for

        urgent_banner = urgent_banner_for(actor)
        if urgent_banner is not None:
            urgent_banner_count = urgent_banner_count_for(actor)
    items = nav_items_for(request)
    bottom_items = bottom_nav_items_for(request)
    current = getattr(request, "resolver_match", None)
    active_key = None
    bottom_active_key = None
    if current is not None:
        for item in items:
            # url_name is namespaced ("web:home"); resolver_match.view_name is already
            # namespaced the same way.
            if item.url_name == current.view_name:
                active_key = item.key
                break
        for item in bottom_items:
            if item.url_name == current.view_name:
                bottom_active_key = item.key
                break
        # The Admin index / More tabs aren't themselves a nav_items entry, but their contents
        # are; highlight the tab when the current page is one of its destinations.
        if bottom_active_key is None and current.view_name == "web:admin_index":
            bottom_active_key = "admin"
        if bottom_active_key is None and current.view_name == "web:more":
            bottom_active_key = "more"
    return {
        "nav_items": items,
        "nav_active_key": active_key,
        "bottom_nav_items": bottom_items,
        "bottom_nav_active_key": bottom_active_key,
        "impersonation_target_full_name": impersonation_target_full_name,
        "urgent_banner": urgent_banner,
        "urgent_banner_count": urgent_banner_count,
    }
