"""`ham.web.nav` renders only built destinations from `ham.authz.nav.nav_for`."""

from __future__ import annotations

import pytest

from ham.authz.context import ActorContext
from ham.web.nav import nav_items_for


class _Req:
    def __init__(self, actor: ActorContext | None) -> None:
        self.actor = actor


def test_signed_out_has_no_nav():
    assert nav_items_for(_Req(None)) == ()


@pytest.mark.django_db
def test_volunteer_sees_home_and_inbox_only(make_user):
    user = make_user("luis@example.org")
    ctx = ActorContext(
        user_id=user.id, real_user_id=None, roles=frozenset({"VOLUNTEER"}), is_active=True
    )
    keys = [item.key for item in nav_items_for(_Req(ctx))]
    assert keys[:2] == ["home", "inbox"]
    assert all(item.built for item in nav_items_for(_Req(ctx)))
