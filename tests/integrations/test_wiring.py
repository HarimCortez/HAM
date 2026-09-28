"""Confirms `IntegrationsConfig.ready()` actually wired the step-1 subscribers into
`ham.outbox.registry` at Django startup, and that the dev-only logging subscriber is not
registered under test settings (DEBUG=False, config/settings/test.py)."""

from __future__ import annotations

from django.conf import settings

from ham.outbox import registry


def test_step1_subscribers_are_registered():
    for name in ("email", "calendar", "fitness", "drive"):
        assert registry.is_registered(name), f"{name} should be registered by IntegrationsConfig"


def test_dev_logging_subscriber_is_not_registered_under_test_settings():
    assert settings.DEBUG is False
    assert not registry.is_registered("dev_logging")
