# ham-backend-engineer — conventions from slices S1 (platform skeleton) + S3a (identity/authz/audit) + S3b (auth)

## S3b additions: passwordless sign-in, TOTP MFA, step-up, impersonation
- **Don't install `allauth`/`allauth.mfa` in `INSTALLED_APPS`** just to reuse their pure
  algorithm/model code. `allauth.mfa.totp.internal.auth` (and anything importing
  `allauth.mfa.models`) requires `"allauth.mfa" in INSTALLED_APPS`, and adding that (plus the
  bare `"allauth"` app it needs) drags the *separate*, legacy top-level `allauth` app's own
  `EmailAddress`/`EmailConfirmation` models into Django's unmigrated-app table sync — this
  broke test-database creation (a FK to `identity_user` created before HAM's migrations run).
  Fix: implement TOTP directly (RFC 6238 is HMAC-SHA1 over a time counter — a few lines of
  stdlib `hmac`/`hashlib`, not "hand-rolled crypto") in `ham/identity/totp.py`; use
  `cryptography.fernet` for at-rest encryption (`ham/identity/crypto.py`) and `qrcode`
  (transitive dep of the `django-allauth[mfa]` pyproject extra, importable without the app
  installed) for QR codes. Logged as `PRD-GAP Q-085` since the plan asked for the allauth
  spike first.
- **HAM's own passwordless sign-in module, not allauth's login-by-code**: allauth's
  login-by-code is built around its own `allauth.account` login pipeline (`Stage`/session
  keys/templates) that doesn't have a "one credential, two redemption paths (code OR
  scanner-safe POST link)" primitive — see `ham/identity/authn.py`'s docstring for the full
  spike note. `SignInChallenge` (`ham/identity/models.py`) stores only *hashes* of the code
  and the link token (never the raw values) so a leaked DB row can't be replayed; consuming
  either invalidates both (single `consumed_at`).
- **GET must never consume a sign-in link** (docs/ux/auth-and-access.md A "scanner-safe"):
  `authn.link_is_valid()` (GET, read-only) vs `authn.consume_link()` (POST only). The view for
  `GET /sign-in/link/<token>` renders a plain "Continue" button; only its POST calls
  `consume_link`.
- **`ham.jobs.run_due_jobs_now()`** (new, dev/test-only): `send_transactional_email` enqueues
  via Procrastinate (`jobs.defer`), which only inserts a `procrastinate_jobs` row — it does
  NOT run synchronously in tests. This helper runs every currently-due job in-process (no
  worker needed) so tests can assert on `django.core.mail.outbox` after triggering a
  sign-in/notification email. Two gotchas it had to route around: (1) `scheduled_at` is
  `NULL` for immediate (non-scheduled) jobs — `WHERE scheduled_at <= now()` silently matches
  nothing; use `scheduled_at IS NULL OR scheduled_at <= now()`. (2) `args` (jsonb) comes back
  from a raw `cursor.execute` as a Python `str`, not a dict — `json.loads()` it before
  `**kwargs`-splatting into the task function.
- **Session-key contract completed** (`ham/authz/context.py` documented the keys; S3b writes
  them): `ham_impersonation_id`, `ham_mfa_satisfied`, `ham_step_up_at` (dict of kind ->
  ISO8601), plus two more S3b added: `ham_session_started_at` (absolute-lifetime anchor) and
  `ham_last_activity` (idle-lifetime anchor), both read/written by
  `ham.identity.middleware.SessionLifetimeMiddleware` (runs right after
  `ActorContextMiddleware`, before the route guard). Mid-session role grants "just work" for
  the MFA-downgrade rule (Q-045) because `ActorContextMiddleware` rebuilds `ActorContext` from
  the DB on every request — no cache to invalidate; `ActorContext.effective_roles` already
  filters out unverified MFA roles using the *session's* `mfa_satisfied` flag, which stays
  `False` for a newly-granted MFA role until that session completes a fresh TOTP/recovery
  check.
- **Route guard now redirects unauthenticated hits to `/sign-in?next=`** instead of the
  neutral 404 (foundation.md §7); the 404 is reserved for a signed-in-but-unauthorized person
  (`ham/authz/guard.py`'s `RouteGuardMiddleware.process_view`). This changed one S3a test's
  expected status code (302, not 404) — check for that distinction before assuming "denied" is
  always a 404 in a new test.
- **`ActorContext` grew impersonation-banner fields** (`impersonation_reason`,
  `target_display_name`, `impersonation_last_activity_at`, plus an
  `impersonation_idle_minutes_left` property) so `ham.web`'s shell template never has to query
  identity tables directly (foundation.md §1 "only ham.identity reads auth tables") — these
  are populated only by `ham.identity.middleware.build_actor_context`, not by every caller.
- **`handle_command_errors` (`ham/identity/web.py`)**: a decorator for views that call
  `@command`-wrapped services, translating `StepUpRequired` into a `/step-up?next=&kind=`
  redirect, `ImpersonationBlocked` into a flash message + redirect back, `PermissionDenied`
  into the neutral 404. Some S5 views instead catch these exceptions inline (they were written
  before this helper existed) and only needed `ham.web.stepup.redirect_to_step_up` (a bare
  URL-builder, kept after trimming that module's placeholder `step_up_stub` view once the
  real `/step-up` screen landed) — both styles coexist; don't assume every view uses the
  decorator.
- **Merge reconciliation pattern for two engineers editing the same seam**: when a shell/S5
  slice stubs out a command S3b also owns (e.g. `ham.web.adapters.update_church_profile`), its
  docstring says exactly what to do at merge ("delete the duplicate, point the view import at
  the real one, keep the call signature"). Do that deletion yourself once you've merged their
  branch in — don't leave two `@command("same.action")` implementations around; only one is
  ever wired to a route, and the other is silent dead code that confuses the next reader.
- **URL-name coordination across parallel worktrees**: agree on exact `path(..., name=...)`
  values (e.g. `step_up`, `user_mfa_reset`, `impersonation_start`, `me_security`) before both
  sides build screens against them — `{% maybe_url %}` (S5's `web_extras.py` tag) lets a
  template reference a not-yet-merged URL name without crashing, but the *names* still have to
  match exactly once both sides land, including argument shape (e.g. `impersonation_start`
  takes a `user_id` kwarg, matching `admin/users/<uuid:user_id>/impersonate`).
- A form that merely posts a button with no fields (e.g. an S5 template's one-click "Reset
  two-step sign-in") can't satisfy a command that requires evidence (`verification_method`
  required by `user.mfa_reset`, `reason` required by `impersonation.start`) — if you land the
  real command after the screen already shipped a bare button, change that one control to a
  link into a GET+POST confirmation view/template that collects the missing field, rather than
  quietly making the requirement optional.

## Environment gotcha (UPDATED in S3a — the S1 note below is stale)
As of S3a, this sandbox **does** have a working Django/Postgres/pytest toolchain: a real
venv at `/home/user/HAM/.venv/bin/` (`python`, `mypy`, with django-stubs installed —
prefer this mypy over `/root/.local/bin/mypy`, which lacks `mypy_django_plugin`), and a local
Postgres 16 already running on 5432 with trust auth. `pip`/`uv` install *do* work now (network
egress is available) — don't assume the S1-era block still applies. Give each parallel slice
its own database (e.g. `ham_s3a`) so worktrees don't collide; `pytest-django` creates
`test_<dbname>` automatically. Run tests with, e.g.:
```
DATABASE_URL=postgres://postgres@localhost:5432/ham_s3a PYTHONPATH=. /home/user/HAM/.venv/bin/python -m pytest
```
`ruff`/`ruff format` still resolve fine from `/root/.local/bin/` (no django-stubs dependency).
Always verify a real green `pytest`/`mypy` run before claiming tests passed.

## S3a additions: identity, authz, audit
- **Dependency layering (import-linter, `pyproject.toml`):** `ham.web` -> `ham.identity` ->
  `ham.authz` -> `ham.audit` -> `ham.outbox` -> `ham.platform` -> `ham.rules`. Only
  `ham.identity` may read auth tables (`User`, `RoleAssignment`, `ImpersonationSession`);
  everything else takes an `ActorContext` (`ham/authz/context.py`).
- **Breaking the authz<->audit cycle:** `ham.authz.commands.command()` must call
  `ham.audit.services.record()` and `ham.outbox.api.emit()` (authz depends on audit/outbox),
  but `ham.audit`'s viewer/export need authorization checks too — which would import back
  into `ham.authz` and violate the layer. Resolution: `ham.audit.queries`/`ham.audit.export`
  are **pure, ctx-free** data/formatting functions with no authorization; the *authorized*
  entry point views must call is `ham.authz.audit_access` (imports both, sits above both).
  `ham.authz.commands` doesn't import `ham.audit`/`ham.outbox` at module scope either — it
  reads module-level globals (`_audit_record`, `_outbox_emit`) that `AuthzConfig.ready()`
  (`ham/authz/apps.py`) registers at Django startup. If you add a new cross-package call in
  this area, check `lint-imports` before assuming it'll work — the layering is easy to
  accidentally violate with an innocent-looking import.
- **The one write path** (`@command("action.code")`, `ham/authz/commands.py`): wraps a service
  fn that returns a `CommandResult` (value + audit fields + optional `OutboxSpec`). Order:
  authorize -> (audit `authz.denied` if in `_AUDITED_ON_DENIAL` and denied) -> impersonation
  block (audits `impersonation.action_blocked`) -> step-up freshness -> `transaction.atomic()`
  wrapping the fn call + `audit.record()` + `outbox.emit()`. An exception anywhere inside the
  atomic block rolls back the DB change, the audit event, and the outbox emit together —
  that's the actual mechanism the "atomic rollback" tests rely on, not anything bespoke.
- **`ham/outbox/` is an S4 stub** (`ham/outbox/api.py`): in-memory list, `emit()` /
  `events()` / `clear()`. Do not add models there; S4 replaces the whole file. Tests call
  `outbox_api.clear()` in an autouse-style fixture to avoid cross-test leakage of the
  module-level list.
- **RoleAssignment invariants** are enforced by Postgres CHECK + two partial unique
  `UniqueConstraint`s (see `ham/identity/models.py`), not just Python — test invariant
  violations with `pytest.raises(IntegrityError)` inside `with transaction.atomic():` (a
  failed statement poisons the outer transaction otherwise, breaking later assertions in the
  same test).
- **`AuditEvent` append-only** is enforced twice: Python-level (`save()`/`delete()` raise
  `AppendOnlyError`) as a friendly error for application code, and a Postgres trigger
  (`ham/audit/migrations/0002_append_only_triggers.py`) as the real control (blocks raw SQL
  too). The purge escape hatch is `SET LOCAL ham.audit_purge = 'on'` — note `SET LOCAL` is
  scoped to the enclosing *real* transaction, not a savepoint, so a test asserting "the flag
  doesn't leak to the next transaction" needs `@pytest.mark.django_db(transaction=True)` to get
  real transaction boundaries instead of pytest-django's default single wrapping transaction.
- **Citext email**: `User.email` uses a custom `CIEmailField` (`db_type` returns `"citext"`)
  plus `CREATE EXTENSION citext` as the first operation of `ham/identity/migrations/0001_initial.py`
  (needs `django.contrib.postgres` in `INSTALLED_APPS` for the `CreateExtension` operation).
- **Custom `AUTH_USER_MODEL = "identity.User"`**: no usable password
  (`set_unusable_password()` in the manager), no `PermissionsMixin` (HAM's own matrix is the
  only authority — don't mix in Django's groups/permissions). django-stubs is picky about
  `REQUIRED_FIELDS`/`USERNAME_FIELD` re-declarations on `AbstractBaseUser` subclasses — don't
  add a type annotation to `REQUIRED_FIELDS = []` (`mypy` treats an annotated Model-class
  assignment as a field and it conflicts with the base class's `ClassVar`).
- **Docs generation, `build_tokens`-style**: `ham/authz/docgen.py` renders
  `docs/architecture/permission-matrix.md` from `ham/authz/matrix.py`;
  `manage.py build_permission_matrix [--check]` mirrors `build_tokens`. Regenerate after any
  matrix change and commit the `.md` file — CI and a pytest test both check it's not stale.
- **Management command ownership**: a command belongs with the app whose service it calls, not
  wherever it happened to be scaffolded first. `bootstrap_admin` moved from
  `ham.platform.management.commands` (S1 stub) to `ham.identity.management.commands` in S3a
  once `ham.identity` existed, because `ham.platform` (bottom layer) must never import a
  domain module — even via a deferred/lazy import inside a function body. import-linter's
  static analysis flags an import statement regardless of nesting; "lazy import to dodge a
  circular import" only helps at runtime, never with the linter.

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
- Management commands live under `ham/platform/management/commands/` (`build_tokens`, wraps
  `design-system/tools/build_tokens.py`) and, since S3a, `ham/identity/management/commands/`
  (`bootstrap_admin`, `seed_dev`) and `ham/authz/management/commands/`
  (`build_permission_matrix`) — put a command with the app whose service it calls, not
  `ham.platform` (see the S3a note above on why `bootstrap_admin` moved there from `platform`).

## Known extension points / gaps for later slices
- **django-allauth is a pyproject dependency but NOT wired into `INSTALLED_APPS`/urls yet** —
  deliberately left to S3b so its models/migrations don't collide with identity work landing in
  parallel. Same for `django-anymail`: `EMAIL_BACKEND` setting exists (console/locmem
  defaults) but no anymail-specific config until S4 builds the adapter.
- **Route guard / `PUBLIC_ROUTES` / `nav_for` exist since S3a** (`ham/authz/guard.py`,
  `ham/authz/nav.py`) but there are almost no real routes yet — S5 builds the actual screens
  and must decorate every view with `@requires_action(...)` or list it in `PUBLIC_ROUTES`, or
  the route-guard middleware fails closed (404) by design.
- **S3b (auth) session-key contract**: `ham/identity/middleware.py` documents the exact
  session keys (`ham_impersonation_id`, `ham_mfa_satisfied`, `ham_step_up_at`) S3b's sign-in/
  MFA/step-up/impersonation flows must read and write so `ActorContext` reflects them.
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
`[[tool.importlinter.contracts]]` — now the full `ham.web -> ham.identity -> ham.authz ->
ham.audit -> ham.outbox -> ham.platform -> ham.rules` layering per foundation.md §1; extend
further as modules land), `build_permission_matrix --check`, pytest against a Postgres 16
service, `build_tokens --check`, pip-audit (non-blocking).

## Misc
- `.env.example` **cannot be created**: `.claude/settings.json` denies Read/Write on any
  `.env*` path (including `.env.example`) as a secrets guardrail, even via Bash heredoc.
  Document required env vars in a regular doc instead (see `docs/dev-environment.md`).
