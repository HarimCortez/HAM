"""ham.notifications.attention: the attention-provider registry (intake.md §3 "'Needs
response' is not stored... computed live by attention providers")."""

from __future__ import annotations

from ham.notifications.attention import (
    AttentionItem,
    attention_items_for,
    register_attention_provider,
    unregister_attention_provider,
)


def test_no_providers_registered_returns_empty():
    assert attention_items_for(object()) == []


def test_registered_provider_contributes_items():
    def provider(ctx):
        return [AttentionItem(kind="test", title="Waiting for a decision (2)", url="/requests")]

    register_attention_provider(provider)
    try:
        items = attention_items_for(object())
        assert len(items) == 1
        assert items[0].title == "Waiting for a decision (2)"
    finally:
        unregister_attention_provider(provider)


def test_multiple_providers_all_contribute():
    def provider_a(ctx):
        return [AttentionItem(kind="a", title="A", url="/a")]

    def provider_b(ctx):
        return [AttentionItem(kind="b", title="B", url="/b")]

    register_attention_provider(provider_a)
    register_attention_provider(provider_b)
    try:
        kinds = {item.kind for item in attention_items_for(object())}
        assert kinds == {"a", "b"}
    finally:
        unregister_attention_provider(provider_a)
        unregister_attention_provider(provider_b)


def test_registering_the_same_provider_twice_does_not_duplicate():
    def provider(ctx):
        return [AttentionItem(kind="test", title="X", url="/x")]

    register_attention_provider(provider)
    register_attention_provider(provider)
    try:
        assert len(attention_items_for(object())) == 1
    finally:
        unregister_attention_provider(provider)
