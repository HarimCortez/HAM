"""Static registry check (foundation.md §9.2): every `@command("action.code")` site in the
codebase (found by scanning source, not by importing `ham.authz.matrix`) names a real,
declared MATRIX action, and every mutating MATRIX action (i.e. not a read-only `.view`/`.list`
action, and not an explicitly-undeclared placeholder awaiting a later module) is wired to at
least one `@command`. Catches "added a matrix row, forgot to wire the command" and "renamed a
command's action string, forgot to update the matrix" without needing a live DB per command.
"""

from __future__ import annotations

import re
from pathlib import Path

from ham.authz.matrix import MATRIX

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCAN_DIRS = (BASE_DIR / "ham",)
# Anchored at column 0 (`^`) so a docstring *example* showing the decorator pattern (indented,
# e.g. ham/outbox/services.py's module docstring) isn't mistaken for a real usage site; every
# actual decorator in this codebase sits directly above a module-level `def` at column 0.
COMMAND_RE = re.compile(r'^@command\(\s*"([\w.]+)"', re.MULTILINE)
# The decorator's own definition module: `ham/authz/commands.py`'s docstring/signature uses
# the literal placeholder `"action.code"`, not a real action.
DEFINITION_MODULE = BASE_DIR / "ham" / "authz" / "commands.py"

# Read-only / query actions: never wrapped in `@command` (no state change, nothing to audit
# per foundation.md §1 "every *consequential* action"). foundation.md §4's own table only
# assigns audit `action` codes (§6) to state-changing rows.
READ_ONLY_ACTIONS = frozenset(
    {
        "shell.use",
        "me.view",
        "me.security.manage",  # a screen; its sub-actions (regenerate/forget) are commands
        "user.list",
        "user.view",
        "audit.view",
        "audit.view_deleted_comment",
        "integrations.view_status",
        "rules.view",
        # S2.0 (intake.md §5, §7): query-only leadership/requester screens.
        "request.list",
        "request.view",
        "request.history.view",
        "request_media.view",
        "requester.request.view",
        "request.needs_phone_check.list",
    }
)

# Declared ahead of their build (foundation.md pattern: "declared ... no route uses this
# action yet"), per docs/prd-open-questions.md.
PLACEHOLDER_ACTIONS = frozenset(
    {
        "me.sign_in_email.change",  # Q-083: matrix entry declared, flow not built this slice
        # S2.0 (intake.md §10 "S2.0 contents"): matrix rows declared ahead of their slice.
        # Now wired (moved out of this set by the ham-test-engineer step-2 gap-filling pass,
        # confirmed against real `@command(...)` sites): request.submit, request.cancel,
        # request.contact_verify_phone, system.request.complete_intake_checks,
        # system.intake.purge (ham/requests/services.py); requester.media.upload,
        # requester.media.remove, request_media.reopen (ham/media/services.py);
        # requester_link.regenerate (ham/requester_portal/services.py). Genuinely still
        # unbuilt this slice (no `@command(...)` site anywhere in `ham/` as of step 2):
        # (none left; request.create_assisted was removed from the matrix in the fix round)
        "intake_source.manage",
        # S3.0 (approvals.md §8.1): matrix rows + service *signatures* declared this slice as
        # `NotImplementedError` stubs (docs/architecture/approvals-contracts.md §2). S3.2
        # (decisions/reconsideration/category/undo/finalize, ham/requests/services_decisions.py)
        # and S3.3 (questions, ham/requests/services_questions.py) have both now wired their
        # real `@command(...)` sites -- nothing left in this set from step 3.
        # `system.media.process`/`system.media.purge`: SYSTEM-scoped background jobs
        # (`ham/media/jobs.py::process_item`/`_purge_item`) that write their own audit rows
        # by hand (`request_media.rejected`/`request_media.purged`/`request_media.purged`)
        # rather than through `@command` -- a routine automated transformation/cleanup, not
        # a human decision, so `@command`'s full authorize/audit/outbox pipeline was never
        # wired for these two MATRIX-declared action codes. Not the same shape as
        # `MANUALLY_WIRED_ACTIONS` below (those *do* authorize via the matrix by hand; these
        # two don't call `authorize()` for their declared action code at all).
        "system.media.process",
        "system.media.purge",
    }
)

# Mutating actions authorized/audited by hand instead of `@command(...)` (each has its own
# reasons documented at the call site; `ham/authz/audit_access.py`'s `export_csv` re-implements
# authorize -> step-up -> atomic -> record because it also needs to return export bytes rather
# than a `CommandResult`, and lives inside `ham.authz` itself, one layer above where `@command`
# is defined). Verified independently by tests/authz/test_audit_access.py, not skipped here.
# S2.2: `requester_pii.reveal` (`ham.requests.services.reveal_requester_pii`) is the same
# shape -- Q-024 needs a reveal that is sometimes *not* audited (a non-impersonating
# Director), which `@command`'s "always write one audit event" pipeline can't express.
MANUALLY_WIRED_ACTIONS = frozenset({"audit.export", "requester_pii.reveal"})


def _command_files() -> list[Path]:
    files: list[Path] = []
    for base in SCAN_DIRS:
        for path in base.rglob("*.py"):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            if path == DEFINITION_MODULE:
                continue
            files.append(path)
    return files


def _commands_in_source() -> set[str]:
    found: set[str] = set()
    for path in _command_files():
        found.update(COMMAND_RE.findall(path.read_text(encoding="utf-8")))
    return found


COMMANDS_FOUND = _commands_in_source()


def test_every_wired_command_names_a_declared_matrix_action():
    unknown = COMMANDS_FOUND - set(MATRIX)
    assert not unknown, f"@command(...) sites naming actions absent from MATRIX: {unknown}"


def test_every_mutating_matrix_action_is_wired_or_a_known_placeholder():
    mutating = set(MATRIX) - READ_ONLY_ACTIONS - PLACEHOLDER_ACTIONS - MANUALLY_WIRED_ACTIONS
    missing = mutating - COMMANDS_FOUND
    assert not missing, (
        f"MATRIX action(s) with no @command site and not a documented placeholder: {missing} "
        "-- either wire a @command, add to READ_ONLY_ACTIONS if it's query-only, or to "
        "PLACEHOLDER_ACTIONS with a PRD-GAP/Q reference if it's intentionally deferred."
    )


def test_no_command_action_is_defined_twice_with_different_wiring():
    # A duplicate @command("same.action") site (two implementations of one action) is the
    # exact "merge reconciliation" bug ham-backend-engineer's memory warns about (dead code
    # confusing readers, or worse, two competing write paths for one action).
    counts: dict[str, int] = {}
    for path in _command_files():
        for action in COMMAND_RE.findall(path.read_text(encoding="utf-8")):
            counts[action] = counts.get(action, 0) + 1
    duplicated = {action: n for action, n in counts.items() if n > 1}
    assert not duplicated, f"@command(...) action(s) declared more than once: {duplicated}"
