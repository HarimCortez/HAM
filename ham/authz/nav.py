"""``nav_for(ctx)``: server-computed navigation (docs/ux/navigation.md §3, foundation.md §2.10).

Step 1 renders only *built* destinations (Home, Inbox placeholder, Me, Admin group, Audit
log); everything else in the eventual sitemap is declared later with ``built=False`` as those
modules land, so this list is the one place nav destinations get added.
"""

from __future__ import annotations

from dataclasses import dataclass

from .matrix import authorize


@dataclass(frozen=True, slots=True)
class NavItem:
    key: str
    label: str
    url_name: str
    icon: str
    built: bool
    action: str


# Order matches docs/ux/navigation.md §3.3 desktop sidebar grouping (WORK/ADMIN groups
# collapse to just these built items in step 1).
_ITEMS: tuple[NavItem, ...] = (
    NavItem("home", "Home", "home", "home", True, "shell.use"),
    NavItem("inbox", "Inbox", "inbox", "inbox", True, "shell.use"),
    NavItem("admin_users", "Users & roles", "admin_users", "users", True, "user.list"),
    NavItem(
        "admin_church",
        "Church settings",
        "admin_church_settings",
        "settings",
        True,
        "church_profile.update",
    ),
    NavItem(
        "admin_integrations",
        "Integrations",
        "admin_integrations",
        "plug",
        True,
        "integrations.view_status",
    ),
    NavItem("admin_rules", "Rules", "admin_rules", "book", True, "rules.view"),
    NavItem("audit_log", "Audit log", "audit_log", "list", True, "audit.view"),
    NavItem("me", "Me", "me", "user", True, "me.view"),
)


def nav_for(ctx) -> list[NavItem]:
    """Only destinations ``ctx`` may use, in a stable order (navigation.md §1 "Nav shows only
    what you can use"). A destination temporarily refused while impersonating still shows
    (its *contents* show the blocked reason, per I3); only role-based denial hides an item."""
    return [item for item in _ITEMS if authorize(ctx, item.action).allowed]
