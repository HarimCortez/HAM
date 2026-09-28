"""Scope-provider registry (foundation.md §2.4, §4): lets later modules (requests, projects,
tasks) teach the policy engine ``ASSIGNED_PROJECT`` / ``INVITED_PROJECT`` scope checks and
``scope_queryset()`` list filtering, without ``ham.authz`` importing those modules.

Step 1 ships the registry and the stub only; no provider is registered until the requests/
projects modules land (build-order step 2+).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .matrix import Scope

# A provider answers "is `resource` in this scope for `ctx`?" for one Scope value.
ScopeProviderFn = Callable[[Any, Any], bool]

_PROVIDERS: dict[Scope, ScopeProviderFn] = {}

# S2.2 (intake.md §2, "which will register a provider here instead of overriding this
# function"): a *queryset*-shaped provider, keyed by action rather than Scope -- unlike
# `ScopeProviderFn` above (one resource at a time, for `authorize()`), listing a whole page
# needs to filter a queryset once (e.g. `request.list` hiding NEEDS_PHONE_CHECK rows from
# anyone but Director/Assistant Director, Q-025). A second, separate registry rather than
# reusing `_PROVIDERS` because `Scope.ANY` (what `request.list` uses) has no per-resource
# meaning to check.
QuerysetScopeProviderFn = Callable[[Any, Any], Any]
_QUERYSET_PROVIDERS: dict[str, QuerysetScopeProviderFn] = {}


def register_scope_provider(scope: Scope, provider: ScopeProviderFn) -> None:
    """Called once by a domain module's ``apps.py`` (e.g. ``ham.requests``) at startup."""
    _PROVIDERS[scope] = provider


def register_queryset_scope_provider(action: str, provider: QuerysetScopeProviderFn) -> None:
    """Called once by a domain module's ``apps.py`` to teach ``scope_queryset`` how to filter
    a list for one action (e.g. ``"request.list"``)."""
    _QUERYSET_PROVIDERS[action] = provider


def check_scope_provider(scope: Scope, ctx: Any, resource: Any) -> bool:
    provider = _PROVIDERS.get(scope)
    if provider is None:
        # No module has claimed this scope yet (step 1: requests/projects don't exist), so it
        # denies rather than raising — matching "deny by default" (foundation.md §4).
        return False
    return provider(ctx, resource)


def scope_queryset(ctx: Any, action: str, queryset: Any) -> Any:
    """Filter a queryset to what ``ctx`` may see for ``action`` (foundation.md §2.4).

    Step 1 had no list screens that needed this (Users & roles uses `user.list`/`user.view`,
    which are role-scoped, not queryset-scoped). S2.2 (`ham.requests`) registers the first
    real provider, for `request.list`.
    """
    provider = _QUERYSET_PROVIDERS.get(action)
    if provider is None:
        return queryset
    return provider(ctx, queryset)
