"""Makes the app shell's nav available to every template (foundation.md §7 "S5 ... nav from
``nav_for``"). See `ham.web.nav` for where the items actually come from.
"""

from __future__ import annotations

from ham.web.nav import nav_items_for


def shell(request):
    """Context processor: ``nav_items`` for the shell templates, plus which one (if any) is
    the current page, so templates can set ``aria-current="page"`` (navigation.md §3.3)."""
    items = nav_items_for(request)
    current = getattr(request, "resolver_match", None)
    active_key = None
    if current is not None:
        for item in items:
            # url_name is namespaced ("web:home"); resolver_match.view_name is already
            # namespaced the same way.
            if item.url_name == current.view_name:
                active_key = item.key
                break
    return {"nav_items": items, "nav_active_key": active_key}
