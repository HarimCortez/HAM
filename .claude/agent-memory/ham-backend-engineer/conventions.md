# ham-backend-engineer — conventions from slice S1 (platform skeleton)

## Environment gotcha
This sandbox has **no network egress** to PyPI, apt, or Docker Hub (all return 403 from a
host allowlist, even though pypi.org/files.pythonhosted.org are nominally in `no_proxy`).
`uv`/`pip`/`apt-get` cannot install anything here. Write code carefully, `python -m py_compile`
everything, run `ruff`/`ruff format` (their binaries happen to be preinstalled at
`/root/.local/bin/ruff` and `/root/.local/bin/mypy` even though their Python deps aren't), and
let GitHub Actions CI (which has real internet) do the actual install + pytest + mypy run.
Don't claim tests passed if you never got Django to import — say so plainly in the handback.

## Repo layout (S1)
- `config/settings/{base,dev,test,prod}.py` — 12-factor, django-environ. `HAM_ENV` (not just
  `DEBUG`) gates prod-only guardrails (admin mount, seed refusal) so a staging box with
  `DEBUG=False` doesn't accidentally get treated as prod.
- `ham/platform/` — Clock (`clock.py`), UUIDv7 (`ids.py`, `UUID7Field`), PII log scrubber
  (`logging.py`), brand loader (`brand.py`), church profile model+service (`models.py`,
  `church.py`), context processor, env guard (`env.py::refuse_in_production`).
- `ham/jobs/` — the ONLY module that imports `procrastinate` directly (`job()`, `defer()`,
  `defer_later()`, `queue_lag_seconds()`). Domain code must import `ham.jobs`, never
  `procrastinate` itself.
- `ham/web/` — app shell placeholder; currently just `/healthz`.
- `ham/rules/` — owned by ham-rules-engineer. Never create/edit files there; only an empty
  `__init__.py` placeholder if it doesn't exist yet.
- Management commands live under `ham/platform/management/commands/`: `build_tokens` (wraps
  `design-system/tools/build_tokens.py`), `bootstrap_admin` (see gap below).

## Known extension points / gaps for later slices
- **`bootstrap_admin` is a stub.** It validates `--email` and then imports
  `ham.identity.services.bootstrap_administrator(email)`, which doesn't exist until S3a builds
  `ham.identity`. It fails loudly with a clear message until then. S3a should just add that one
  function; the command wiring is done.
- **No `seed_dev` yet** (that's S3a's, per foundation.md §2.11) — but the reusable guard
  `ham.platform.env.refuse_in_production(name)` already exists for it to call.
- **django-allauth is a pyproject dependency but NOT wired into `INSTALLED_APPS`/urls yet** —
  deliberately left to S3b so its models/migrations don't collide with identity work landing in
  parallel. Same for `django-anymail`: `EMAIL_BACKEND` setting exists (console/locmem
  defaults) but no anymail-specific config until S4 builds the adapter.
- **Route guard / `PUBLIC_ROUTES` / `nav_for` don't exist yet** (S3a). `/healthz` is public by
  virtue of not requiring auth today; once the guard middleware lands, register it explicitly.
- **`ham/rules/`, `docs/rules-changelog.md`, `tests/rules/`** are ham-rules-engineer's — do not
  touch; they landed in the same tree concurrently with S1.

## Lint/format setup
- `pyproject.toml` `[tool.ruff]` has `extend-exclude = ["design-system", "frontend", "docs"]`
  because `design-system/tools/build_tokens.py` is UI-designer-owned and uses a different style
  (long lines, etc.) — don't lint it as application code.
- Line length 100. `ruff format` matches `ruff check` expectations; run both.
- mypy uses `django-stubs`; `[tool.django-stubs] django_settings_module = "config.settings.test"`.

## Testing
- `pytest-django`, `DJANGO_SETTINGS_MODULE=config.settings.test` (set in `pyproject.toml`
  `[tool.pytest.ini_options]`).
- `tests/conftest.py` has an autouse fixture that resets `ham.platform.clock` to `SystemClock`
  before/after every test — don't forget to restore the clock in any new time-travel test.
- Postgres for tests: `make dev-db` (via `scripts/dev_db.sh`, initdb+pg_ctl under `./pgdata`,
  trust auth, no Docker) or CI's `postgres:16` service container.

## CI
`.github/workflows/ci.yml`: ruff check, ruff format --check, mypy, `makemigrations --check
--dry-run`, `lint-imports` (import-linter, contract in `pyproject.toml`
`[[tool.importlinter.contracts]]` — currently just `ham.web` → `ham.platform` layering; extend
per foundation.md §1 dependency rules as modules land), pytest against a Postgres 16 service,
`build_tokens --check`, pip-audit (non-blocking).

## Misc
- `.env.example` **cannot be created**: `.claude/settings.json` denies Read/Write on any
  `.env*` path (including `.env.example`) as a secrets guardrail, even via Bash heredoc.
  Document required env vars in a regular doc instead (see `docs/dev-environment.md`).
