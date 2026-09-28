"""intake-contracts.md §8.3 / step-2 handoff "known loose end" #1: after Django startup,
`ham.requester_portal.apps.RequesterPortalConfig.ready()` must have registered real
implementations for all three portal lookups (`register_request_facts_lookup`,
`register_request_contact_lookup`, `register_email_to_request_ids_lookup`) -- otherwise
`issue_link`/`resolve_token`/`regenerate_link`/`find_my_request` raise `RuntimeError` at
runtime, not the ordinary "not found" result a caller expects.

Named to sort early (`test_app_ready_registration` < `test_links`/`test_regenerate_and_find`,
alphabetically, within this directory) so it runs *before* any other test file's fixture
`yield`-teardown resets these same module-level globals to `None` -- this test's whole point
is to observe genuine post-startup state, not a fixture's own re-registration.
"""

from __future__ import annotations

import uuid

import pytest

from ham.requester_portal import services

pytestmark = pytest.mark.django_db


def test_facts_lookup_registered_after_app_ready():
    with pytest.raises(ValueError):  # "unknown request", not RuntimeError
        services._facts(uuid.uuid4())  # noqa: SLF001 - exercising the registered callable


def test_contact_lookup_registered_after_app_ready():
    assert services._contact(uuid.uuid4()) is None  # noqa: SLF001


def test_email_lookup_registered_after_app_ready():
    assert services._requests_for_email("nobody@example.org") == []  # noqa: SLF001
