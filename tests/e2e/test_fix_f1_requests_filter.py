"""FIX-F1 N1 regression: the leadership Requests filter bar (`requests_list.html`) must be
visible and usable at >=768, not just on mobile. Chromium 131+ hides a *closed* `<details>`'s
content through its `::details-content` slot in a way plain CSS `display` can't override, so
relying on `.filter-bar-sheet:not([open]) .filter-bar { display: flex }` silently breaks tablet
and desktop. The fix renders the `<details>` server-side `open`, and only a small inline
script collapses it back down on mobile.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def _session_cookie(live_server, django_user):
    from django.conf import settings
    from django.test import Client

    client = Client()
    client.force_login(django_user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return {
        "name": settings.SESSION_COOKIE_NAME,
        "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
        "url": live_server.url,
    }


def _make_director():
    from ham.authz import roles
    from ham.identity.models import RoleAssignment, SharedIdentityProfile, User
    from ham.platform.clock import now as clock_now

    user = User.objects.create_user(email="marcus-fixf1@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=user, role=roles.HAM_DIRECTOR, granted_at=clock_now())
    return user


def test_filter_bar_visibility_by_width(live_server):
    from playwright.sync_api import sync_playwright

    director = _make_director()
    cookie = _session_cookie(live_server, director)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for width, height, expect_visible in [
                (768, 900, True),
                (1280, 900, True),
                (390, 844, False),
            ]:
                context = browser.new_context(viewport={"width": width, "height": height})
                context.add_cookies(
                    [{"name": cookie["name"], "value": cookie["value"], "url": cookie["url"]}]
                )
                page = context.new_page()
                page.goto(f"{live_server.url}/requests")
                page.wait_for_load_state("networkidle")

                visible = page.eval_on_selector("#id_q", "el => el.checkVisibility()")
                assert visible is expect_visible, (
                    f"width={width}: search input checkVisibility()={visible}, "
                    f"expected {expect_visible}"
                )

                if not expect_visible:
                    # N1: still reachable at 390 -- opening the disclosure reveals it.
                    page.click(".filter-bar-sheet__trigger")
                    reachable = page.eval_on_selector("#id_q", "el => el.checkVisibility()")
                    assert reachable, "search input isn't reachable at 390 after opening Filters"

                context.close()
        finally:
            browser.close()
