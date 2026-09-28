# ham-backend-engineer — conventions from slices S1 (platform skeleton) + S3a (identity/authz/audit) + S3b (auth)

## Post-S3b security-review fixup (2026-09-28)
- **"Re-check session flags against the DB every request"**: a session boolean/flag (like
  `ham_mfa_satisfied`) only ever proves something was true *at the moment it was set*. If a
  privileged fact can change later (an Admin resets someone's MFA, a person clicks "sign out
  everywhere" from a different browser, an account gets disabled), the session flag alone goes
  stale and a still-open browser tab keeps acting on the old fact. The fix isn't to trust the
  flag less — it's to give it an **epoch**: store a `User.session_epoch`/`TOTPDevice.
  last_used_step`-style counter in the DB, snapshot the current value into the session at the
  moment the flag is set (`ham.identity.authn.complete_sign_in` does this for
  `ham_session_epoch`), and compare the snapshot to the *live* DB value on every request
  (`ham.identity.middleware.SessionLifetimeMiddleware._enforce_session_epoch`, which runs
  before the route guard). Any code path that must invalidate every existing session for a
  user bumps the counter — it never tries to delete Django sessions directly, since there's no
  server-side "list every session for this user" index without a custom session backend.
  `ActorContextMiddleware` already re-reads roles/`is_active` from the DB every request for the
  same reason (Q-045 mid-session downgrade); the epoch pattern is the same idea applied to "was
  MFA verified this session" instead of "which roles are active".
- **TOTP replay protection needs a per-device high-water mark, not just time-window
  tolerance**: accepting "current step ± 1" (clock drift) is not the same as accepting a code
  only once. `TOTPDevice.last_used_step`, checked and updated under `select_for_update()`
  inside `ham.identity.mfa.verify_totp`, is what actually prevents a captured/observed code
  from being replayed a second time within its valid window.
- **A "mid-sign-in" session (only the emailed code answered) must never be trusted to reach
  enrollment for an *already-enrolled* account.** This was the step-1 MFA-bypass-via-
  re-enrollment finding: `ham/web/auth_views.py::mfa_setup` now branches hard on `pending_user
  is not None and mfa.is_enrolled(pending_user)` → redirect to the real TOTP/recovery
  challenge, before anything else runs. A *replacement* of an existing authenticator (Q-093)
  is a completely different, much narrower path: only reachable by someone already fully
  signed in **with** two-step this session (`ctx.mfa_satisfied`, never merely "has a trusted
  device cookie"), never while impersonating, and only after a fresh step-up
  (`ctx.has_fresh_step_up(...)` checked directly in the view — no need to add a new action to
  `ham/authz/matrix.py` for this; the generic `/step-up?kind=` screen accepts any kind string
  and just stamps `session[SESSION_KEY_STEP_UP][kind]`, so a view-local freshness check against
  an ad hoc kind name works without touching the matrix). `mfa.confirm_enrollment` itself has a
  second, defense-in-depth guard: it refuses to overwrite a confirmed device unless the caller
  explicitly passes `replace=True`.
- **Prefer pyotp/qrcode over a hand-rolled RFC 6238 loop, even though the algorithm is "just
  HMAC over a counter"**: CLAUDE.md's "safety/legal/privacy over convenience" and PRD §3.4-3.5
  read on *code*, not just data handling — a security review correctly flagged unaudited
  hand-written crypto-adjacent logic even though it composed only stdlib `hmac`/`hashlib`. If
  `allauth.mfa` can't be wired in as a Django app (see the S3b note below for why), reach for a
  small, independently maintained library (`pyotp`) instead of writing the construction again.
  See `docs/adr/0001-stack.md`'s "Amendment 2026-09-28" for the full writeup.
- **Encrypting background-job payloads to keep PII out of `procrastinate_jobs.args`**: when a
  job's kwargs are themselves sensitive (an email address, a sign-in code, a TOTP-reset
  notice), don't rely only on log scrubbing — Procrastinate persists `args` as a jsonb column
  regardless of logging config, and a DB dump/backup would still have it in plaintext. Encrypt
  the whole payload into one opaque string (`ham.integrations.email.service` does this with
  `ham.platform.crypto`, the same Fernet/MultiFernet helper `ham.identity.crypto` re-exports)
  and pass only that ciphertext (plus genuinely non-sensitive fields like a `category` label)
  as job kwargs; decrypt only inside the job function, right before handing data to the real
  adapter. This is also why the shared cipher helper lives in `ham.platform` (the bottom
  layer) rather than `ham.identity`: `ham.integrations` must never import `ham.identity`
  (import-linter contract "domain modules never import ham.integrations directly" is the
  mirror image of this — either direction would be a layering violation), but both can import
  `ham.platform`.
- **`JSONFormatter` must recursively scrub *and* selectively drop `extra` values, not just
  `record.msg`**: `ScrubPIIFilter` only ever rewrites the top-level message string. A
  third-party logger (Procrastinate's own "Starting job ...(kwargs)" line) can attach a whole
  nested structure as an `extra` (e.g. `record.job = {"task_kwargs": {...}}`) that never passes
  through `scrub()` at all. Fix at the formatter, not the filter: drop known-risky whole keys
  outright (`_DROPPED_EXTRA_KEYS = {"job"}`) and recursively scrub every string inside whatever
  survives (`_scrub_value`). Also set noisy third-party loggers to WARNING in `LOGGING`
  (`config/settings/base.py`) so routine per-job start/finish lines never reach a handler at
  all — the scrubber is defense in depth, not a substitute for not logging the args in the
  first place.
- **A Postgres `BEFORE TRUNCATE` trigger on an append-only table breaks Django's
  `TransactionTestCase`/`transaction=True` flush globally** (it issues one multi-table
  `TRUNCATE ... CASCADE` statement; any one table's trigger raising rolls back the whole
  statement, so *every* `transaction=True` test in the suite fails at teardown, not just tests
  touching that table). There is no clean way to give Django's `flush` command the same
  `SET LOCAL ham.audit_purge = 'on'` escape hatch the retention job uses, because `flush` runs
  its own SQL directly. The real fix (a separate, lower-privilege DB role for the app that has
  TRUNCATE revoked, distinct from a migrations/ops role) needs role separation this sandbox's
  shared single-superuser Postgres setup doesn't have — don't add this trigger without that
  separation in place; it will look fine in isolation and then break the whole test suite.
- **`redirect_to_step_up`/`handle_command_errors` grew a stash-and-replay pattern for step-up
  continuation** (UX finding "Confirm it's you sends people to POST-only URLs and loses what
  they typed"): a view whose POST hits `StepUpRequired` stashes its own POST data (minus the
  CSRF token) keyed by path in the session; the GET that comes back from a successful step-up
  is replayed as if it were the original POST (`request.POST = QueryDict(...)`;
  `request.method = "POST"` — both are plain instance attributes on `HttpRequest`, safe to
  reassign) before calling the view again. This fixed MFA reset/impersonation-start/recovery-
  code-regenerate "for free" since they already used `ham.identity.web.handle_command_errors`;
  audit export needed its own version in `ham/web/views_audit.py` because it isn't
  command-wrapped the same way (a GET `audit_export_download` view replays stashed *filters*,
  not a full POST body, then streams the CSV directly rather than trying to redirect after
  already writing a response body). `/step-up` also grew a real `cancel_url` (`?cancel=`,
  falling back to a validated `HTTP_REFERER`, then Home) instead of blindly linking back to
  `next` (which is the *protected* URL, not "where the person came from").

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
