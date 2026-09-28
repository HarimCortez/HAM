"""FIX-E N4 regression: the 7-year retention purge's `RequestContactVerification.value_key`
erasure lives in one named manager method
(`RequestContactVerificationManager.erase_value_keys_for_retention`), not a bare
`.filter(...).update(value_key=...)` scattered at the call site -- grep-style check that (a)
only `purge_expired_request` calls the manager method, and (b) no other code bypasses it with
its own raw `.update(value_key=`. New file per wave brief.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ham.requests.models import RequestContactVerification

pytestmark = pytest.mark.django_db

HAM_SRC = Path(__file__).resolve().parent.parent.parent / "ham"


def _grep(pattern: str) -> list[tuple[Path, int, str]]:
    regex = re.compile(pattern)
    hits: list[tuple[Path, int, str]] = []
    for path in HAM_SRC.rglob("*.py"):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if regex.search(line):
                hits.append((path, lineno, line.strip()))
    return hits


def test_only_purge_expired_request_calls_the_manager_method():
    hits = _grep(r"erase_value_keys_for_retention\(")
    call_sites = [h for h in hits if "def erase_value_keys_for_retention" not in h[2]]
    assert len(call_sites) == 1, call_sites
    path, _, line = call_sites[0]
    assert path.name == "services.py" and path.parent.name == "requests", call_sites
    assert "RequestContactVerification.objects.erase_value_keys_for_retention" in line


def test_no_other_code_bulk_updates_value_key_directly():
    """A raw `.update(value_key=...)` anywhere outside the manager method itself would be a
    second, undiscoverable way to bypass the append-only guard."""
    hits = _grep(r"\.update\(\s*value_key=")
    outside_manager = [
        h for h in hits if h[0].name != "models.py" or h[0].parent.name != "requests"
    ]
    assert outside_manager == []


def test_erase_value_keys_for_retention_actually_blanks_every_row(requester_ctx):
    import uuid

    from ham.requests.services import submit_request
    from tests.requests.conftest import make_payload

    req = submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(),
    )
    assert RequestContactVerification.objects.filter(request=req).exclude(value_key="").exists()
    RequestContactVerification.objects.erase_value_keys_for_retention(req)
    assert not RequestContactVerification.objects.filter(request=req).exclude(value_key="").exists()
