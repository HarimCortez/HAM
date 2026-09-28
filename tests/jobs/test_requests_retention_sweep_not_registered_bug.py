"""BUG (found while writing the step-2 periodic-job registry enumeration test): the Q-127
retention sweep for `ham.requests` (7-year requester-PII erase after close; 90-day spam
purge) is defined but never actually scheduled with Procrastinate's periodic runner.

`ham/requests/jobs.py::retention_sweep` is decorated `@jobs.periodic_job(
name="requests.retention_sweep", cron="0 3 * * *")` (`ham/requests/jobs.py:71`). Procrastinate
only learns about a `@periodic_job`-decorated function once the module it lives in is
*imported* -- the decorator does the registration as an import-time side effect (this is
exactly the pattern the other two step-2 apps use correctly: `ham/media/apps.py::ready()`
imports `from . import jobs  # noqa: F401 - registers the procrastinate tasks` and
`ham/requester_portal/apps.py::ready()` does the same).

`ham/requests/apps.py::RequestsConfig.ready()` (`ham/requests/apps.py:16-26`) never imports
`ham.requests.jobs` at all -- it only imports `.queries` and `.attention`/`.notifications`.
The *only* other places `ham.requests.jobs` is imported are two lazy, function-body imports
inside `ham/requests/services.py` (`from ham.requests.jobs import
defer_complete_intake_checks`, at lines 215 and 378), which only run when `submit_request`/
`verify_by_phone` is actually called -- and even then, only in whatever process happens to
call them (typically a web request-handling process, not the `python manage.py procrastinate
worker` process that actually runs periodic tasks on its own `cron`-driven loop).

Net effect: in a real deployment, the worker process's Django app registry never imports
`ham.requests.jobs` during startup, so `requests.retention_sweep` never enters
Procrastinate's `PeriodicRegistry` and is **never scheduled** -- the 7-year PII erase and the
90-day spam purge (Q-127, decided by the owner) silently never run, no matter how long the
system is up, until *something* happens to import that module first.

This is checked **statically** here (regex over `ready()`'s source, via
`tests/jobs/test_periodic_registry.py`'s `_ready_imports_submodule` helper), not by
inspecting `ham.jobs.app.periodic_registry` at runtime: a runtime check is order-dependent
within one pytest session (once *any* test anywhere calls `submit_request`, the module gets
imported and the decorator fires for the rest of that process, hiding the bug depending on
file/test order -- confirmed empirically by an earlier runtime-based version of this file,
which passed when the suite ran in reverse file order). A worker process never running
`submit_request` at all doesn't get that accidental rescue.

Contrast: `media.retention_sweep` and both `requester_portal.*` jobs (also periodic) *do* get
registered, because their apps' `ready()` imports their `jobs` module.

(Also, separately: `ham/identity/apps.py::ready()` has the exact same gap for
`identity.purge_sign_in_challenges` -- step-1 scope, not fixed here, but caught by the same
static check and listed in `tests/jobs/test_periodic_registry.py`'s
`KNOWN_NOT_WIRED_DUE_TO_BUG` so it isn't silently missed either.)

Suggested fix: add `from . import jobs  # noqa: F401 - registers the procrastinate tasks` to
`RequestsConfig.ready()` in `ham/requests/apps.py`, mirroring `ham/media/apps.py` and
`ham/requester_portal/apps.py` exactly. Severity: High -- this is a decided, owner-approved
retention/privacy rule (Q-127, PRD §47/§68) with no other trigger in production; it is silent
(no error, no log) until fixed, and every day it stays unfixed is a day of PII that should
have been erased staying in the database.

Test-only change per this agent's remit: this file only proves and pins the bug (`xfail(
strict=True)`, the same pattern as `tests/web/test_audit_export_stepup_redirect_bug.py`); the
app-code fix itself is for `ham-backend-engineer`/`ham-rules-engineer` to apply.
"""

from __future__ import annotations

import pytest

from tests.jobs.test_periodic_registry import BASE_DIR, _ready_imports_submodule


@pytest.mark.xfail(
    strict=True,
    reason="BUG: RequestsConfig.ready() never imports ham.requests.jobs, so "
    "requests.retention_sweep (Q-127) never registers with Procrastinate's periodic "
    "runner in a real worker process -- see this file's module docstring.",
)
def test_requests_retention_sweep_is_wired_at_app_startup():
    assert _ready_imports_submodule(BASE_DIR / "ham/requests/apps.py", "jobs")
