"""Enumerates every periodic job step 1+2 expects Procrastinate's worker to actually know
about (PRD §78 "background jobs for reminders, retention, waitlists, calendar sync"), derived
from the PRD/decided Qs -- not by importing each domain module's own list of what it *thinks*
it registered, which would just tautologically pass. Registration is an import-time side
effect of `ham.jobs.periodic_job` (see its docstring: "this is the one place a
'purge/sweep on a schedule' job should be registered, instead of leaving a job defined but
never actually scheduled") -- a job can be fully coded and unit-tested and still never run in
production if the app that owns it never imports the module at `ready()` time.

Deliberately **static** (regex-scans `apps.py::ready()` source), not a runtime inspection of
`ham.jobs.app.periodic_registry`: a runtime check is inherently order-dependent within one
pytest session, because `@periodic_job`'s registration is a one-time *module import* side
effect that, once triggered by *any* test (e.g. one that calls `submit_request`, which lazily
imports `ham.requests.jobs` mid-function -- see `ham/requests/services.py`), stays registered
for every test that runs afterward in the same process, masking the exact bug this module
exists to catch depending on file/test order. (This was caught empirically: an earlier
runtime-registry version of this test only failed the way it should when `tests/jobs/` ran
early enough, alphabetically, that no other test had yet imported the buggy module -- reverse
file order made two of these tests spuriously pass. Static source-scanning has no such
ordering dependency: it reads the same `ready()` source no matter what ran before it.)
"""

from __future__ import annotations

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _ready_method_source(app_config_path: Path) -> str:
    text = app_config_path.read_text(encoding="utf-8")
    match = re.search(r"def ready\(self\)[^\n]*:\n(.*?)(?=\n    def |\Z)", text, re.DOTALL)
    assert match, f"no `def ready(self):` method found in {app_config_path}"
    return match.group(1)


def _strip_comments(source: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in source.splitlines())


def _ready_imports_submodule(app_config_path: Path, submodule: str) -> bool:
    """True if `ready()`'s source imports `submodule` as a name, either
    `from . import submodule` / a parenthesized multi-line `from . import (a, submodule, b)`
    or a fully-qualified `from ham.<app> import submodule`. Two passes rather than one
    collapsed-whitespace regex: a parenthesized import's `)` naturally bounds a `re.DOTALL`
    search across its own lines, but treating the *whole* method body as one collapsed line
    breaks as soon as there's more than one `from ... import` statement (an earlier
    non-parenthesized import's search can't tell where its own logical line ends without the
    next statement also starting with `from`, which isn't guaranteed)."""
    body = _strip_comments(_ready_method_source(app_config_path))

    def _names(names_blob: str) -> list[str]:
        return [n.strip().split(" as ")[0].strip() for n in names_blob.split(",") if n.strip()]

    for m in re.finditer(r"from\s+[\w.]+\s+import\s*\(([^)]*)\)", body, re.DOTALL):
        if submodule in _names(m.group(1)):
            return True

    for line in body.splitlines():
        stripped = line.strip()
        line_match = re.match(r"from\s+[\w.]+\s+import\s+(.+)$", stripped)
        if (
            line_match
            and "(" not in line_match.group(1)
            and submodule in _names(line_match.group(1))
        ):
            return True

    return False


# One entry per periodic job the PRD/decided Qs require as of step 2, with:
#   - the section/Q that requires it running unattended on a schedule;
#   - the file whose `@jobs.periodic_job(...)` decorator defines it (confirmed against the
#     real source, not assumed);
#   - the file whose `AppConfig.ready()` must import that defining module's containing
#     submodule for the decorator to ever actually run at process (worker) startup.
# (module_path, submodule_name, defining_file, decorator_name_in_source, ready_file)
EXPECTED_PERIODIC_JOBS: list[tuple[str, str, Path, str, Path]] = [
    # `identity.sweep_idle_impersonation_sessions` (PRD §59) is deliberately NOT listed here:
    # it genuinely *is* registered at real startup (confirmed against the live
    # `app.periodic_registry` at process start), but not via `IdentityConfig.ready()` --
    # `ham/identity/apps.py::ready()` only imports `.notifications`, which doesn't reach
    # `.impersonation` either. It works today only because `ham/requests/apps.py::ready()`
    # (step 2) imports `.notifications`, which imports `ham.identity.services`, which imports
    # `.impersonation` at module level -- an indirect, fragile chain this table's
    # one-job-one-ready-file model can't express cleanly, and not this slice's app code to
    # restructure. `identity.purge_sign_in_challenges` right below has no such rescue.
    (
        # Step 1, same shape as the step-2 bug below -- not this agent's slice to fix, but
        # caught by the same static check, so listed here rather than silently ignored.
        "identity.purge_sign_in_challenges",  # sign-in code hygiene retention
        "authn",
        BASE_DIR / "ham/identity/authn.py",
        "identity.purge_sign_in_challenges",
        BASE_DIR / "ham/identity/apps.py",
    ),
    (
        "requester_portal.purge_expired_drafts",  # Q-100/Q-139: unfinished draft, 24h
        "jobs",
        BASE_DIR / "ham/requester_portal/jobs.py",
        "requester_portal.purge_expired_drafts",
        BASE_DIR / "ham/requester_portal/apps.py",
    ),
    (
        "requester_portal.purge_expired_challenges",  # verification-code hygiene
        "jobs",
        BASE_DIR / "ham/requester_portal/jobs.py",
        "requester_portal.purge_expired_challenges",
        BASE_DIR / "ham/requester_portal/apps.py",
    ),
    (
        "media.retention_sweep",  # PRD §47, Q-128: media retention
        "jobs",
        BASE_DIR / "ham/media/jobs.py",
        "media.retention_sweep",
        BASE_DIR / "ham/media/apps.py",
    ),
    (
        # Q-127, decided: 7-year requester-PII erase after close; 90-day spam purge.
        # BUG (tests/jobs/test_requests_retention_sweep_not_registered_bug.py): as of this
        # slice, `ham/requests/apps.py::ready()` does NOT import `jobs` -- expect this one
        # entry to fail below until that's fixed.
        "requests.retention_sweep",
        "jobs",
        BASE_DIR / "ham/requests/jobs.py",
        "requests.retention_sweep",
        BASE_DIR / "ham/requests/apps.py",
    ),
]

# Carved out here (rather than silently passing) so this enumeration test still catches any
# *other* job going missing without needing to be updated again once these app-code bugs are
# fixed -- at that point these sets become empty and the corresponding xfail bug-pin
# tests/comments should be deleted along with the entries here.
KNOWN_NOT_WIRED_DUE_TO_BUG: set[str] = set()


class TestPeriodicJobRegistry:
    def test_every_expected_job_decorator_exists_in_its_defining_file(self):
        """Sanity check on `EXPECTED_PERIODIC_JOBS` itself: the decorator name really is
        where this table claims it is (catches this table going stale, e.g. after a rename),
        independent of whether `ready()` actually imports it."""
        for (
            job_name,
            _submodule,
            defining_file,
            decorator_name,
            _ready_file,
        ) in EXPECTED_PERIODIC_JOBS:
            source = defining_file.read_text(encoding="utf-8")
            pattern = re.compile(rf'@\w*\.?periodic_job\(\s*name="{re.escape(decorator_name)}"')
            assert pattern.search(source), (
                f"{job_name}: no @jobs.periodic_job(name={decorator_name!r}) found in "
                f"{defining_file} -- EXPECTED_PERIODIC_JOBS is stale"
            )

    def test_every_expected_periodic_job_is_registered_at_app_startup(self):
        not_wired = set()
        for (
            job_name,
            submodule,
            _defining_file,
            _decorator_name,
            ready_file,
        ) in EXPECTED_PERIODIC_JOBS:
            if not _ready_imports_submodule(ready_file, submodule):
                not_wired.add(job_name)

        assert not_wired == KNOWN_NOT_WIRED_DUE_TO_BUG, (
            f"periodic job(s) {not_wired - KNOWN_NOT_WIRED_DUE_TO_BUG} are expected "
            "(PRD/Q-derived) but their owning AppConfig.ready() never imports the module "
            "that defines them, so they never register with Procrastinate's periodic "
            "runner in a real worker process -- check ready() imports its jobs module (see "
            "ham/media/apps.py or ham/requester_portal/apps.py for the correct pattern). "
            f"(If this set is now smaller than {KNOWN_NOT_WIRED_DUE_TO_BUG}, a listed bug "
            "got fixed -- update KNOWN_NOT_WIRED_DUE_TO_BUG and the matching xfail bug-pin "
            "test/comment accordingly.)"
        )
