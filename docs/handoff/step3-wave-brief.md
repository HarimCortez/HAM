# HAM step 3 (Approvals) — common brief for all slices

## Setup
- Your worktree is a copy of HarimCortez/HAM. FIRST: `git fetch origin feature/step-3-approvals && git checkout -B <your-branch> origin/feature/step-3-approvals` (worktrees may start stale). Commit on your branch; do NOT push. Other slices run in parallel in other worktrees; the orchestrator merges.
- Postgres runs on 127.0.0.1:5432 as user `ham` / password `ham` (NOT postgres@). If not, `make dev-db` from /home/user/HAM. Use your OWN DB: `DATABASE_URL=postgresql://ham:ham@127.0.0.1:5432/ham_<slice>`. If you run a dev server, use the port your brief names and set `HAM_BASE_URL` to it.
- Venv: `/home/user/HAM/.venv/bin/`. Run from your worktree root with `PYTHONPATH=.` and `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`. Build the frontend once (`cd frontend && npm ci && npm run build`). New Python deps: `uv pip install --python /home/user/HAM/.venv/bin/python ...` AND add them to pyproject.toml (CI installs from pyproject in a clean env — a dep that is only transitively installed will break CI).

## Read first
- `CLAUDE.md`.
- `docs/architecture/approvals.md` — the **Owner decisions and reconciliation** box at the top overrides the body (and overrides `docs/ux/approvals.md` too). Use Q numbers from `docs/prd-open-questions.md` (Q-153–Q-176 for step 3) in `PRD-GAP Q-NNN` markers.
- `docs/architecture/approvals-contracts.md` (written by S3.0) — exact contracts: models, service signatures, matrix actions, events.
- `docs/ux/approvals.md` (UX spec; screen codes A1–A13, R13–R19, E8–E15, L-E5–L-E12) and `design-system/screens/approvals.md` (hi-fi, from ham-ui-designer) for anything user-facing.
- Step-2 context you build on: `docs/architecture/intake.md`, `intake-contracts.md`, and the step-2 review lessons in `docs/ux/reviews/step2-*.md` (never treat a session as proof of identity; never reveal a decrypted token; PII-free lists/subjects; 200% text; prove every fix with a test that fails before and passes after).
- `.claude/agent-memory/*/` conventions of every agent.

## Owner decisions (final)
- Q-153: the first recorded decision (approve or reject) settles the request.
- Q-154: rejection = required reason code (family_or_others_can_help · owner_or_landlord_responsible · not_help_ham_offers · couldnt_confirm · another_reason) + required editable kind message pre-filled per reason; message in the email body, neutral subject.
- Q-155/Q-174: 14 days to ask for reconsideration, cutoff = end of the church-local day printed in the email; then HAM finalizes automatically.
- Q-156/Q-176: decider confirms on a preview; the same person may undo within 30 minutes; the requester email and the other held effects wait out the window and are cancelled on undo; undo is audited (record kept, marked undone); urgent-approval alert to Director/AD is NOT held (safety) and gets an in-app follow-up on undo.

## Non-negotiables
- Every consequential action goes through `@command` → audit event (actor + UTC) → outbox event (IDs only). Never put requester name/address/phone/email/circumstances in logs, audit before/after, outbox payloads, email subjects, list rows, or AI prompts.
- Fixed values only in `ham/rules` (use existing names; if you truly need a new one, add it with the `proposed("Q-NNN")`/provisional pattern, bump RULES_VERSION, changelog, pinned hash/values tests).
- New/changed matrix actions → update the independent oracle `tests/authz/generate_expected_matrix.py` from the PRD/decided Qs (not by copying the matrix) and regenerate `expected_matrix.csv`; regenerate `docs/architecture/permission-matrix.md`.
- New gaps: note them in your handback (don't edit docs/prd-open-questions.md — the orchestrator numbers them).

## Before committing — all must pass
`ruff check .` · `ruff format --check .` · `DJANGO_SETTINGS_MODULE=config.settings.test mypy .` · `lint-imports` · `manage.py makemigrations --check --dry-run` · `manage.py build_permission_matrix --check` · full `pytest`. Update your agent memory file.

## Hand back
Files, public functions/contracts others depend on, tests added + count, gaps, your branch + commit.
