# HAM step 2 (Intake) — common brief for all wave-2/3 slices

## Setup
- Your worktree is a copy of HarimCortez/HAM. FIRST: `git fetch origin feature/step-2-intake && git checkout -B <your-branch> origin/feature/step-2-intake` (worktrees may start stale). Commit on your branch; do NOT push. Other slices run in parallel in other worktrees; the orchestrator merges.
- Postgres runs on localhost:5432 (trust auth). If not, `make dev-db` from /home/user/HAM. Use your OWN DB: `DATABASE_URL=postgres://postgres@localhost:5432/ham_<slice>`.
- Venv: `/home/user/HAM/.venv/bin/`. Run from your worktree root with `PYTHONPATH=.` and `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`. Build the frontend once (`cd frontend && npm ci && npm run build`). New Python deps: `uv pip install --python /home/user/HAM/.venv/bin/python ...` AND add them to pyproject.toml (CI installs from pyproject in a clean env — a dep that is only transitively installed will break CI).

## Read first
- `CLAUDE.md`.
- `docs/architecture/intake.md` — the **Owner decisions and reconciliation** box at the top overrides the body. Use Q numbers from `docs/prd-open-questions.md` (Q-025, Q-099–Q-142) in `PRD-GAP Q-NNN` markers, never the draft numbers inside intake.md's body.
- `docs/architecture/intake-contracts.md` — exact contracts from S2.0 (contexts, matrix actions, platform otp/net/storage, stubs you implement, import-linter notes).
- `docs/ux/intake.md` (final UX spec) and `design-system/screens/intake.md` (hi-fi specs) for anything user-facing.
- `.claude/agent-memory/*/` conventions of every agent (backend, integrations, rules, frontend, test).
- Existing code: `ham/rules` (step-2 rules already added, version 2026.09.28-4), `ham/requests/states.py`, `ham/requests/matching.py`, `ham/requester_portal/validity.py` (pure logic from S2.1 — use them, don't reimplement).

## Owner decisions (final)
- Verify before submit (Q-100): the request reaches leaders only after the emailed code; unfinished form kept encrypted server-side, erased after 24 h.
- Email or "I don't use email" (Q-025): no-email requests are saved in NEEDS_PHONE_CHECK; only Director/AD see them; they leave via "Verified by phone call" (audited, blocked while impersonating) → SUBMITTED → normal duplicate check → AWAITING_APPROVAL, or via close. Q-140: add a 4th pre-decision close reason "couldn't reach them" allowed only from NEEDS_PHONE_CHECK.
- Retention (Q-127): 7 years after close then erase name/email/phone/street; spam 90 days; unfinished forms 24 h.
- Administrator (Q-124): view-only requests, requester contact details masked, no reveal; photo count only (Q-138).
- Submitted → Awaiting Approval automatic after the duplicate check; all pastors + Board rep see every awaiting request; no routing.

## Non-negotiables
- Every consequential action goes through `@command` → audit event (actor + UTC) → outbox event (IDs only). Never put requester name/address/phone/email/circumstances in logs, audit before/after, outbox payloads, email subjects, list rows, or AI prompts.
- Fixed values only in `ham/rules` (use existing names; if you truly need a new one, add it with the `proposed("Q-NNN")`/provisional pattern, bump RULES_VERSION, changelog, pinned hash/values tests).
- New/changed matrix actions → update the independent oracle `tests/authz/generate_expected_matrix.py` from the PRD/decided Qs (not by copying the matrix) and regenerate `expected_matrix.csv`; regenerate `docs/architecture/permission-matrix.md`.
- New gaps: note them in your handback (don't edit docs/prd-open-questions.md — the orchestrator numbers them).

## Before committing — all must pass
`ruff check .` · `ruff format --check .` · `DJANGO_SETTINGS_MODULE=config.settings.test mypy .` · `lint-imports` · `manage.py makemigrations --check --dry-run` · `manage.py build_permission_matrix --check` · full `pytest`. Update your agent memory file.

## Hand back
Files, public functions/contracts others depend on, tests added + count, gaps, your branch + commit.
