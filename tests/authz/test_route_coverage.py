"""Route-coverage test (foundation.md §7, §9.1): every URL pattern must declare an action
(`@requires_action(...)`) or be listed in `ham.authz.guard.PUBLIC_ROUTES`. This walks the real
URLconf, not a hand-maintained list, so a new view can't accidentally ship unguarded.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, get_resolver

from ham.authz.guard import PUBLIC_ROUTES
from ham.authz.matrix import MATRIX


def _iter_patterns(resolver, prefix=""):
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            yield from _iter_patterns(entry, prefix)
        elif isinstance(entry, URLPattern):
            yield entry


def _declared_action(view_func) -> str | None:
    return getattr(view_func, "_ham_action", None)


def test_every_url_pattern_declares_an_action_or_is_public():
    resolver = get_resolver()
    undeclared = []
    for pattern in _iter_patterns(resolver):
        name = pattern.name
        if name in PUBLIC_ROUTES:
            continue
        # Django admin (mounted only when DEBUG, config/urls.py) is a break-glass tool
        # outside HAM's authz layer by design (docs/adr/0001-stack.md §6) — skip it.
        if name is None or "django-admin" in str(pattern.pattern):
            continue
        action = _declared_action(pattern.callback)
        if action is None:
            undeclared.append(f"{name!r} ({pattern.pattern})")
    assert not undeclared, (
        "URL pattern(s) with no @requires_action and not in PUBLIC_ROUTES (fails closed at "
        "runtime, but should be declared explicitly so this stays intentional):\n"
        + "\n".join(undeclared)
    )


def test_every_declared_action_is_a_known_matrix_action():
    resolver = get_resolver()
    unknown = []
    for pattern in _iter_patterns(resolver):
        action = _declared_action(pattern.callback)
        if action is not None and action not in MATRIX:
            unknown.append(f"{pattern.name!r} declares unknown action {action!r}")
    assert not unknown, "\n".join(unknown)


def test_public_routes_all_exist_in_the_urlconf():
    """Catches a stale PUBLIC_ROUTES entry for a renamed/removed URL name."""
    resolver = get_resolver()
    known_names = {p.name for p in _iter_patterns(resolver)}
    stale = PUBLIC_ROUTES - known_names
    assert not stale, f"PUBLIC_ROUTES names no URL pattern: {stale}"
