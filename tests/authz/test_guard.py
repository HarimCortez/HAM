from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from ham.authz import roles
from ham.authz.context import ActorContext
from ham.authz.guard import RouteGuardMiddleware, requires_action

# The neutral 404 renders the shell template, whose context processors read the church profile.
pytestmark = pytest.mark.django_db


def _middleware():
    return RouteGuardMiddleware(get_response=lambda request: HttpResponse("ok"))


class _FakeResolverMatch:
    def __init__(self, url_name):
        self.url_name = url_name
        self.view_name = url_name
        self.app_names: list[str] = []
        self.namespaces: list[str] = []


def _request_for(url_name: str, path: str = "/x"):
    request = RequestFactory().get(path)
    request.resolver_match = _FakeResolverMatch(url_name)  # type: ignore[assignment]
    return request


def test_public_route_bypasses_guard():
    mw = _middleware()
    request = _request_for("healthz", "/healthz")
    request.actor = ActorContext.anonymous()

    def undeclared_view(req):
        return HttpResponse("ok")

    assert mw.process_view(request, undeclared_view, (), {}) is None


def test_undeclared_view_fails_closed():
    mw = _middleware()
    request = _request_for("mystery")
    request.actor = ActorContext.anonymous()

    def undeclared_view(req):  # no @requires_action
        return HttpResponse("ok")

    response = mw.process_view(request, undeclared_view, (), {})
    assert response is not None
    assert response.status_code == 404


def test_declared_view_denies_without_permission():
    mw = _middleware()
    request = _request_for("admin_users")
    request.actor = ActorContext(
        user_id="u1", real_user_id=None, roles=frozenset({roles.VOLUNTEER}), is_active=True
    )

    @requires_action("user.list")
    def admin_users(req):
        return HttpResponse("ok")

    response = mw.process_view(request, admin_users, (), {})
    assert response.status_code == 404


def test_declared_view_allows_with_permission():
    mw = _middleware()
    request = _request_for("admin_users")
    request.actor = ActorContext(
        user_id="u1",
        real_user_id=None,
        roles=frozenset({roles.ADMINISTRATOR}),
        is_active=True,
        mfa_satisfied=True,
    )

    @requires_action("user.list")
    def admin_users(req):
        return HttpResponse("ok")

    assert mw.process_view(request, admin_users, (), {}) is None


def test_missing_actor_defaults_to_anonymous_and_redirects_to_sign_in():
    # foundation.md §7: an unauthenticated request to a protected route redirects to
    # /sign-in?next=, distinct from the neutral 404 a signed-in-but-unauthorized person gets
    # (navigation.md §6) — this also covers "no request.actor set at all" (a bug in middleware
    # ordering degrades to anonymous, not a crash).
    mw = _middleware()
    request = _request_for("me", path="/me")

    @requires_action("me.view")
    def me_view(req):
        return HttpResponse("ok")

    response = mw.process_view(request, me_view, (), {})
    assert response.status_code == 302
    assert response.url.startswith("/sign-in")
    assert "next=%2Fme" in response.url
