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
# collapse to just these built items in step 1). `built=False` until the screen exists; the
# S5 screens pass flips each one as its route lands.
_ITEMS: tuple[NavItem, ...] = (
    NavItem("home", "Home", "web:home", "home", True, "shell.use"),
    # S2.8: the leadership screens (L1-L11) land; flipped to `built=True` now that
    # `web:requests` exists.
    NavItem("requests", "Requests", "web:requests", "clipboard-list", True, "request.list"),
    NavItem("inbox", "Inbox", "web:inbox", "mail", True, "shell.use"),
    NavItem("admin_users", "Users & roles", "web:admin_users", "users", True, "user.list"),
    NavItem(
        "admin_church",
        "Church settings",
        "web:admin_church_settings",
        "settings",
        True,
        "church_profile.update",
    ),
    NavItem(
        "admin_integrations",
        "Integrations",
        "web:admin_integrations",
        "plug",
        True,
        "integrations.view_status",
    ),
    NavItem("admin_rules", "Rules", "web:admin_rules", "book", True, "rules.view"),
    NavItem("audit_log", "Audit log", "web:audit_log", "scroll-text", True, "audit.view"),
    NavItem("me", "Me", "web:me", "circle-user", True, "me.view"),
)


def nav_for(ctx) -> list[NavItem]:
    """Only destinations ``ctx`` may use, in a stable order (navigation.md §1 "Nav shows only
    what you can use"). A destination temporarily refused while impersonating still shows
    (its *contents* show the blocked reason, per I3); only role-based denial hides an item."""
    return [item for item in _ITEMS if authorize(ctx, item.action).allowed]


# --- Mobile bottom nav (navigation.md §3.1: "at most 5 items"; Q-091) ----------------------
#
# Only the Administrator's built destinations were ever wide enough to overflow the 390px
# bottom nav in step 1 (C2/Q-091), so these two synthetic destinations exist purely to cap it:
# ``admin`` groups the Users & roles / Church settings / Integrations / Rules / Audit log
# destinations behind one tab (the Admin index page), and ``more`` is the catch-all for
# whatever a role's built nav has left over once Home/Admin/Inbox have their tabs (holds Me
# and Sign out, per the C2 fix note).
ADMIN_GROUP_KEYS: frozenset[str] = frozenset(
    {"admin_users", "admin_church", "admin_integrations", "admin_rules", "audit_log"}
)

ADMIN_INDEX_ITEM = NavItem("admin", "Admin", "web:admin_index", "layout-grid", True, "shell.use")
MORE_ITEM = NavItem("more", "More", "web:more", "ellipsis", True, "shell.use")

# navigation.md §3.1: the Director/Assistant Director/Administrator rows end in **More**
# (they have more built-out leadership destinations than fit); every other row (Volunteer,
# Task Leader, Project Leader, Contractor, Social Media Specialist, Pastor, Board
# representative) ends in **Me** directly.
_MORE_TAB_ROLES: frozenset[str] = frozenset({"ADMINISTRATOR", "HAM_DIRECTOR", "ASSISTANT_DIRECTOR"})


def admin_group_items(ctx) -> list[NavItem]:
    """Destinations on the Admin index page (C2 fix note): every built nav item in the admin
    group this viewer may use, so Users & roles / Church settings / Integrations / Rules /
    Audit log share one hub instead of five separate tabs."""
    return [item for item in nav_for(ctx) if item.key in ADMIN_GROUP_KEYS]


def bottom_nav_for(ctx) -> list[NavItem]:
    """The mobile bottom nav for this actor, capped at 5 items (navigation.md §3.1)."""
    full = nav_for(ctx)
    by_key = {item.key: item for item in full}
    tabs: list[NavItem] = []
    if "home" in by_key:
        tabs.append(by_key["home"])
    # S2.8: a direct "Requests" tab for anyone who may see the list (Director, Assistant
    # Director, pastors, Board rep, and the view-only Administrator, Q-124) — the busiest
    # screen for these roles in step 2, so it doesn't hide behind More (navigation.md §3.1).
    if "requests" in by_key:
        tabs.append(by_key["requests"])
    is_administrator = "ADMINISTRATOR" in ctx.effective_roles
    if is_administrator and any(item.key in ADMIN_GROUP_KEYS for item in full):
        tabs.append(ADMIN_INDEX_ITEM)
    if "inbox" in by_key:
        tabs.append(by_key["inbox"])
    if ctx.effective_roles & _MORE_TAB_ROLES:
        tabs.append(MORE_ITEM)
    elif "me" in by_key:
        tabs.append(by_key["me"])
    return tabs[:5]


def more_items(ctx) -> list[NavItem]:
    """Destinations on the More page (navigation.md §3.1): admin-group items not already
    covered by a dedicated Admin tab, plus Me. Sign out is always offered alongside these by
    the template — it isn't a permission-gated `NavItem`."""
    full = nav_for(ctx)
    by_key = {item.key: item for item in full}
    is_administrator = "ADMINISTRATOR" in ctx.effective_roles
    items: list[NavItem] = []
    if not is_administrator:
        items.extend(item for item in full if item.key in ADMIN_GROUP_KEYS)
    if "me" in by_key:
        items.append(by_key["me"])
    return items
