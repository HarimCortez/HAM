"""`ham.web.nav` stub (foundation.md S5, pending `ham.authz.nav` from S3a)."""

from __future__ import annotations

from ham.web.nav import nav_items_for


class _FakeRequest:
    """`nav_items_for` only reads `request.actor`, which doesn't exist until S3a; a plain
    stand-in is enough to exercise the stub path."""


def test_stub_nav_only_returns_built_destinations():
    items = nav_items_for(_FakeRequest())
    assert [item.key for item in items] == ["home", "inbox"]
    assert all(item.built for item in items)


def test_stub_nav_items_declare_the_shell_use_action():
    items = nav_items_for(_FakeRequest())
    assert all(item.action == "shell.use" for item in items)
