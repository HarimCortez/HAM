"""Nav items for the app shell (foundation.md §7 route table; navigation.md §3).

The real source of navigation is ``ham.authz.nav.nav_for(request.actor)`` (foundation.md
Slices table, S3a): it returns items filtered by what the signed-in person may actually use,
in the order navigation.md §3.3 lists them, each carrying the ``authz`` action that route
requires. That module is being built in a parallel worktree (S3a) and does not exist in this
slice yet, so :func:`nav_items_for` calls it if importable and otherwise falls back to a
**clearly temporary stub** so the shell has something to render and test against.

Later screens should render nav from this module's :class:`NavItem` shape only — never
hard-code destinations in a template — so wiring in the real ``nav_for`` at merge time is a
one-line change here, not a template rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavItem:
    """One nav destination (foundation.md §7: "Each destination declares its action and a
    ``built`` flag; step 1 renders only built destinations")."""

    key: str
    label: str
    url_name: str
    icon: str  # Lucide icon name (design-system/components.md "Icons are Lucide")
    built: bool
    action: str  # the authz action this route requires, e.g. "shell.use"


# --- TEMPORARY STUB (S5, pending ham.authz.nav from S3a) ---------------------------------
# Mirrors navigation.md §3.1's mobile set and §3.3's sidebar groups, reduced to what step 1
# actually ships (foundation.md §2.10 "step 1 renders only built destinations": Home, Inbox
# placeholder). Me, Admin and Audit log routes don't exist yet (foundation.md §10 "Out of
# scope for step 1" lists their screens; only their nav slot is reserved here), so they are
# marked ``built=False`` and are hidden by :func:`nav_items_for`.
_STUB_NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem(
        key="home", label="Home", url_name="web:home", icon="home", built=True, action="shell.use"
    ),
    NavItem(
        key="inbox",
        label="Inbox",
        url_name="web:inbox",
        icon="mail",
        built=True,
        action="shell.use",
    ),
    NavItem(
        key="me", label="Me", url_name="web:me", icon="circle-user", built=False, action="me.view"
    ),
    NavItem(
        key="admin",
        label="Admin",
        url_name="web:admin",
        icon="shield",
        built=False,
        action="user.list",
    ),
    NavItem(
        key="audit",
        label="Audit log",
        url_name="web:audit",
        icon="scroll-text",
        built=False,
        action="audit.view",
    ),
)


def nav_items_for(request) -> tuple[NavItem, ...]:
    """Return the nav items to render for this request, built destinations only.

    Tries the real ``ham.authz.nav.nav_for(request.actor)`` first (S3a); falls back to the
    stub list above when that module isn't available yet, e.g. in this slice's own tests.
    """
    try:
        from ham.authz.nav import nav_for  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError:
        return tuple(item for item in _STUB_NAV_ITEMS if item.built)

    actor = getattr(request, "actor", None)
    return tuple(item for item in nav_for(actor) if item.built)
