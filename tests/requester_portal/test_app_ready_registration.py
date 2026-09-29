"""intake-contracts.md §8.3 / step-2 handoff "known loose end" #1: after Django startup,
`ham.requester_portal.apps.RequesterPortalConfig.ready()` must have registered real
implementations for all three portal lookups (`register_request_facts_lookup`,
`register_request_contact_lookup`, `register_email_to_request_ids_lookup`) -- otherwise
`issue_link`/`resolve_token`/`regenerate_link`/`find_my_request` raise `RuntimeError` at
runtime, not the ordinary "not found" result a caller expects.

Order-dependence fix (test-engineer pass, step 3): this file used to rely purely on sorting
early (`test_app_ready_registration` < `test_links`/`test_regenerate_and_find`, alphabetically,
within this directory) so it would run *before* any other test file's fixture `yield`-teardown
reset these same module-level globals to `None`. That only holds in forward, alphabetical file
order -- running the whole suite in reverse file order puts this file *last* within
`tests/requester_portal/`, after files that leave the globals in whatever state their own
fixtures left them, and this file's own tests then fail with `RuntimeError` instead of
exercising the real callables at all. Depending on the shared `real_portal_lookups` fixture
(`tests/conftest.py`) makes the "genuine post-startup behaviour" this file wants to observe
independent of file order: that fixture registers the exact same real callables
`RequesterPortalConfig.ready()` registers (confirmed identical in `tests/conftest.py`'s own
docstring), without re-running `ready()` itself (which would also re-register the periodic
purge jobs) -- so this test still exercises production code, just no longer by ordering luck.
"""

from __future__ import annotations

import uuid

import pytest

from ham.requester_portal import services

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _use_real_portal_lookups(real_portal_lookups):
    pass


def test_facts_lookup_registered_after_app_ready():
    with pytest.raises(ValueError):  # "unknown request", not RuntimeError
        services._facts(uuid.uuid4())  # noqa: SLF001 - exercising the registered callable


def test_contact_lookup_registered_after_app_ready():
    assert services._contact(uuid.uuid4()) is None  # noqa: SLF001


def test_email_lookup_registered_after_app_ready():
    assert services._requests_for_email("nobody@example.org") == []  # noqa: SLF001
