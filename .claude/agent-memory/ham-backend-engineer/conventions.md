# ham-backend-engineer — conventions from slices S1 (platform skeleton) + S3a (identity/authz/audit) + S3b (auth) + Fix B (parallel security/PRD fixes) + round-3 re-review fixes

## Round-3 security re-review fixup (2026-09-28)
- **A denial audit written inside a `@command`'s own `transaction.atomic()` is lost if a
  *caller* wraps several `@command` calls in one more outer `transaction.atomic()`** (only one
  call site does this today: `ham.web.views_admin_users._apply_role_changes`, batching
  multiple `grant_global_role`/`revoke_global_role` calls). The inner atomic is a savepoint,
  so `ham.authz.commands`'s own `except PermissionDenied: audit_record(...); raise` writes the
  row *inside* the still-open outer transaction — then the exception propagates out through
  the outer `with`, rolling the whole thing back, audit row included. Don't try to detect
  "nested atomic" via `connection.in_atomic_block` (pytest-django's default per-test wrapping
  transaction makes that True in literally every test, so it can't distinguish "a caller
  intentionally nested me" from "pytest wrapped the whole test"). Instead: at the *one*
  call site that batches commands in an outer atomic, catch the denial **inside** the `with`
  block, call `transaction.set_rollback(True)` and let the block exit *without* raising (a
  clean rollback, not an exception-triggered one), then record the missed audit event
  yourself once you're safely outside the `with` — see `_apply_role_changes`'s
  `step_up_exc`/`denial_exc` pattern.
- **Every session-ending path must end any active impersonation *before* `django_logout`**,
  not just the manual "Stop" button and idle timeout: `ham.identity.impersonation.
  end_impersonation_for_session(request, reason=...)` (new) reads/pops
  `SESSION_KEY_IMPERSONATION_ID` from `request.session` itself and calls the existing
  `end_impersonation`, so callers that only have a bare `HttpRequest` (not an
  `ImpersonationSession` row already in hand) don't have to duplicate that lookup.
  `SessionLifetimeMiddleware._enforce_session_epoch`/`_enforce_session_lifetime` and
  `ham.web.auth_views._end_session_fully` (shared by `sign_out` and `sign_in_cancel`, itself
  new) all call it. Added `ImpersonationSession.END_REASON_SESSION_EXPIRED` for the
  epoch/lifetime paths (needs a migration for the `choices=` metadata change, even though
  it's "just" adding a choice value to an existing `CharField`).
- **`ham.jobs.periodic_job(name=..., cron=...)`** (new): combines `job()` with Procrastinate's
  `Application.periodic(cron=...)` so the worker defers a task on schedule itself — no
  separate scheduler process. The decorated function's first parameter must be
  `timestamp: int` (Procrastinate's periodic-task contract; conventionally unused). Use for
  "purge/sweep on a schedule" jobs that were previously defined but never actually wired to
  run (`ham.identity.authn.purge_expired_sign_in_challenges` is now hourly; a new
  `ham.identity.impersonation.sweep_idle_impersonation_sessions` runs every 5 minutes as the
  backstop for an impersonation session whose owner's browser never sends another request at
  all — the per-request idle check in the middleware only ever fires *if* a request comes in).
- **A step-up (or similar) attempt-lockout budget must be ONE counter for the whole session,
  never one per free-text "kind"** — a per-kind dict lets an attacker reset their guess budget
  just by making up a new kind string each time. Also reject any `kind` that isn't in the
  fixed, known set (`ham.web.auth_views._STEP_UP_ACTION_LABELS`'s keys) before doing anything
  else with it. Reaching the lockout should fully sign the person out (ending any active
  impersonation via the helper above), not just refuse that one confirmation and let the
  session carry on — mirrors `_restart_sign_in`'s existing "too many sign-in MFA guesses"
  behavior.
- **A stash-and-replay session key needs an explicit `created_at` + a freshness check against
  `RULES.auth.STEP_UP_WINDOW`**, same as `admin_user_roles_resume`'s pending-role-change
  stash — `ham.web.views_audit.audit_export`'s `_EXPORT_STASH_SESSION_KEY` didn't have one and
  could be replayed hours later. When a view's Cancel handler clears session keys by literal
  string, double-check it's clearing the *actual* key that screen uses, not a similarly-named
  key from a different mechanism (`ham.identity.web._STEP_UP_STASH_SESSION_KEY` =
  `"ham_step_up_stash"` is the *generic* command-error stash; `views_audit.py`'s own
  `"ham_audit_export_stash"` is a separate, page-specific mechanism — `step_up`'s Cancel
  handler needs to clear both, not assume clearing one covers the other).
- **Never fall back to an email address as a display name** — `ham.identity.models.
  neutral_display_name(user_id)` (`f"Member {short id}"`) is the one fallback every such call
  site (`display_names_for`, `UserRow`/`UserDetail.display_name`, the impersonation banner's
  `target_display_name`, `ham.identity.notifications._display_name`) must use instead of
  `profile.user.email`/`user.email` when there's no `SharedIdentityProfile.full_name` yet —
  §68 forbids showing contact info to a viewer who isn't otherwise authorized to see it, and
  a bare email-address fallback bypassed that everywhere it appeared.
- **A client-supplied `X-Forwarded-For` is not trustworthy input for anything security-
  relevant** (a rate-limit throttle counts as one) **unless you know exactly how many hops a
  proxy *you* control actually added.** `settings.HAM_TRUSTED_PROXY_COUNT` (new, default `0` =
  "ignore the header, use `REMOTE_ADDR`") is that number; `ham.web.auth_views._client_ip` reads
  the right-most `N` comma-separated hops, never the left-most (client-controlled) one.
  `render.yaml` sets it to `1` for Render's single edge proxy.
- **Fernet's own `ttl=` parameter on `decrypt()`** (already built into the library, no extra
  bookkeeping needed) bounds how long a ciphertext stays decryptable, on top of key rotation —
  `ham.platform.crypto.decrypt(token, ttl_seconds=...)` is opt-in (`None` default preserves
  "no natural expiry" for TOTP secrets at rest); `ham.integrations.email.service`'s job-payload
  decrypt passes `RULES.outbox.JOB_PAYLOAD_ENCRYPTION_TTL`. Gotcha for tests: Fernet's TTL
  check is against the **real** wall clock (`time.time()`), not `ham.platform.clock` — use a
  real `time.sleep()`, not `tick()`/`FixedClock`, to age a token in a test.
- **`config/settings/prod.py` should validate *every* comma-separated
  `HAM_FIELD_ENCRYPTION_KEY`**, not just the first (a bad key later in a rotation list should
  fail at deploy time, not the first time some old record needs it to decrypt) — and should
  refuse to boot at all without a non-localhost `HAM_BASE_URL` (emailed links otherwise
  silently point at `localhost` in production). `render.yaml`'s worker service needs its own
  `HAM_BASE_URL` too (it builds emails) and should get `HAM_FIELD_ENCRYPTION_KEY` via
  `fromService` pointing at `ham-web`, not a second independently-typed `sync: false` secret
  that can drift out of sync with the web service's.
- **An emailed link's query string can end up in a mail scanner's/proxy's/browser's own logs
  or history** — don't put a person's email address in one just to prefill a form
  (`ham.identity.notifications._sign_in_url()` no longer takes an `email=` param for the
  invitation email's sign-in link).
- **A one-time secret shown once (recovery codes, an enrollment QR/secret) should leave the
  session the moment it's rendered**, not wait for a "Continue"/"Finish" button that might
  never get pressed — pop it from `request.session` on the GET that renders it, but keep a
  separate boolean "already shown" flag so the same page's own POST can still complete the
  flow afterward (`ham.web.auth_views.mfa_setup_codes`'s
  `_RECOVERY_CODES_SHOWN_SESSION_KEY`).

## Fix B additions (parallel with Fix A on auth/security)
- **`ham.authz.commands.command()`'s atomic block now catches `PermissionDenied` raised from
  *inside* the wrapped service body** (not just the pre-check `authorize()` denial) and records
  `authz.denied` *after* the `with transaction.atomic()` block has already rolled back — so a
  finer-grained refusal like `_check_can_grant` (a Director trying to grant Administrator) is
  audited exactly like a matrix-level denial. If you add a new "no held role may do X to Y"
  check inside a service function's body, it's covered automatically; no per-call audit code
  needed.
- **Route-guard and `audit_access` denials are now audited too**: `ham.authz.guard`'s
  `RouteGuardMiddleware` and `ham.authz.audit_access.export_csv` both call
  `ham.audit.services.record` directly for denied/blocked privileged actions, reusing
  `ham.authz.commands._AUDITED_ON_DENIAL` as the single "which actions are noisy vs.
  consequential" list — don't duplicate that set elsewhere; import it.
- **New `ham.identity.impersonation`** (`end_impersonation(session_id, reason)`,
  `end_impersonations_for_target(user_id, reason)`): the one place a session-ending path should
  call to get an audited `impersonation.ended` + an `ImpersonationEnded` outbox event (Q-049).
  `stop_impersonation` (manual "Stop", `@command`-wrapped) emits the same event through its own
  `CommandResult` instead of calling this module (avoids a duplicate audit row from both the
  wrapper's and the helper's own `audit_record` calls) — `disable_user` calls
  `end_impersonations_for_target` directly since Q-052 needs it inline with the disable
  transaction. Auth/session paths outside the command pipeline (idle timeout, sign-out) should
  call `end_impersonation` instead of duplicating the session-ending logic inline.
- **`ham.identity.notifications`** (new): identity's own outbox-email builders (invitation,
  role-change-notifies-all-Admins Q-055, impersonation-ended Q-049), registered from
  `IdentityConfig.ready()`. This required one new `ignore_imports` entry in `pyproject.toml`'s
  import-linter contract (`ham.identity.notifications -> ham.integrations.email.notifications`)
  — the established exception pattern for "a domain module resolves its own notification
  content" (mirrors `ham.identity.authn`/`mfa` -> `email.service`). **Outbox payloads must stay
  ids/codes only** (`ham.outbox.validation`): an ISO timestamp string in a payload trips the
  phone-number-looking-string heuristic — pass a record id instead and have the builder re-query
  the row for any timestamp/reason it needs to render.
- **`ham.integrations.email.notifications.Builder` can now return a `list[NotificationEmail]`**
  (not just one-or-`None`) — `handle_email_event` fans out to every item. Use this when one
  outbox event should notify multiple people (Q-055's "email every active Administrator");
  existing single-`NotificationEmail`/`None` builders are unaffected.
- **`ham.platform.church`** grew `is_valid_time_zone(name)` (validate against
  `zoneinfo.available_timezones()`) and `format_church_time(moment)` (renders with the zone
  abbreviation, e.g. "3:45 PM EST") — Q-030/§70.5. **`ham.platform.timezone_middleware.
  ChurchTimeZoneMiddleware`** (new, in `MIDDLEWARE` right after `SessionLifetimeMiddleware`,
  before the route guard) activates `django.utils.timezone` to the church's zone for every
  request so `timezone.localtime()` in templates/views is correct without per-caller
  boilerplate; it does not depend on `request.actor` (one church zone for everyone in V1, not
  per-user). `update_church_profile` (`ham.identity.services`) now validates the incoming zone
  name with `is_valid_time_zone` and raises `ValueError` (caught in the view, shown as a field
  error) rather than saving an unparseable zone.
- **Audit date filters are church-local, not UTC**: `ham.web.views_audit._parse_church_date`
  treats a plain `"YYYY-MM-DD"` H1 filter value as a whole calendar day in the church time zone
  (converted to UTC for the actual query); a value that already carries a time/offset is trusted
  as-is. Don't assume `dt.datetime.fromisoformat(...).replace(tzinfo=dt.UTC)` is correct for a
  bare date from an HTML `<input type=date>` — that silently uses UTC midnight instead of
  church-local midnight.
- **Q-095 (free-text `reason` excluded from CSV export)**: implemented in
  `ham.authz.audit_access._drop_excluded_columns`, a post-processing step over
  `ham.audit.export.build_csv`'s output (re-parses the CSV, drops the `reason` column by name),
  **not** inside `ham/audit/export.py` itself — that file is Fix A's. If another export-only
  exclusion is needed later, extend `_EXCLUDED_EXPORT_COLUMNS` there rather than editing
  `export.py`, unless Fix A's owner agrees column selection belongs in `export.py` instead.
- **Invitation email + expiry (Q-037/Q-071/Q-084)**: `ham.identity.services.invite_user` now
  sets `created_by_id`, pre-checks for an existing email and raises a friendly `ValueError`
  (PRD-guardian B7) instead of letting `IntegrityError` 500, and its `UserCreated` outbox event
  (when it carries `invited_by`) drives an invitation email via `ham.identity.notifications`.
  **`invitation_is_valid(user) -> bool`** is the seam Fix A's sign-in flow must call before
  completing an Invited person's sign-in (checks `ACCOUNT_INVITATION_LIFETIME` from
  `created_at`/`invitation_resent_at`, and that the account isn't disabled/cancelled).
  `resend_invitation`/`cancel_invitation` (new `@command`s, `user.invitation_resend`/
  `user.invitation_cancel` in the matrix) reset that window or disable the account; a new
  `User.invitation_resent_at` field (migration `0003_user_invitation_resent_at`) is the resend
  baseline. `bootstrap_administrator`'s `UserCreated` event has no `invited_by`, so it never
  triggers an invitation email — don't assume every `UserCreated` event came from `invite_user`.
- **Q-079/Q-052 (Director may disable/enable non-Administrator accounts)**: the matrix now
  allows both Administrator and Director for `user.disable`/`user.enable`, but the finer "not
  another Administrator's account" rule lives in the service body (`disable_user`/`enable_user`
  raise `PermissionDenied` if the actor isn't an Administrator and the target holds
  Administrator) — same pattern as `_check_can_grant` for role grants. The view's
  `can_disable`/`can_enable` context flags mirror this so the button doesn't even render for a
  Director looking at an Administrator's page.
- **Q-047/Q-094 (last active HAM Director, mirroring the last Administrator rule)**:
  `_count_active_directors` (mirrors `_count_active_administrators`); `disable_user` and
  `revoke_global_role` both refuse to reach zero active Directors, same shape as the existing
  Administrator guard.
- **Leader reassignment records the replaced user**: `_assign_leader` now returns
  `(assignment, previous_user_id)`; `assign_project_leader`/`assign_task_leader` put
  `before={"previous_user_id": ...}` on the audit event when there was one.
- **Multiple role changes in one confirm apply atomically**: `views_admin_users.
  _apply_role_changes` wraps its `grant_global_role`/`revoke_global_role` loop in one more
  `transaction.atomic()` — each call is already its own `@command` atomic block/savepoint, but
  the outer wrapper makes a `StepUpRequired` partway through roll back every change in the
  batch, not just the one that triggered it, before re-stashing the *original* full diff for the
  step-up resume.
- **Me page identity mix-up while impersonating (item 6)**: `me.update` is now
  `blocked_while_impersonating=True` in the matrix; `views_me.py` reads/displays
  `SharedIdentityProfile.objects.filter(user_id=ctx.user_id)` (the *effective* identity) instead
  of `request.user.profile` (the real signed-in person), so display and save always agree.
- **New routes**: `GET /api/v1/me` (`views.api_me`; id/display_name/roles/nav/impersonation
  state/rules_version — never email/phone), `GET,POST /admin/users/<id>/identity`
  (`admin_user_identity_update`, wraps the already-existing `update_identity` command),
  `GET,POST /admin/users/<id>/disable` (confirmation-first, was POST-only), `POST
  /admin/users/<id>/invitation/{resend,cancel}`, `GET /admin/users/new/sent` (invite
  confirmation reachable without `user.view`, for an Assistant Director who can invite but can't
  list users — Q-082).
- **Scope trim**: the Admin Integrations page (and Home's new integrations summary) filter
  `subscriber_status_counts()`/`recent_failures()` down to `_VISIBLE_SUBSCRIBERS` (`{"email"}`
  today) in the *view* layer, not by unregistering the calendar/drive/fitness stub subscribers
  from `ham.outbox.registry` — those stubs must stay registered so the outbox dispatcher always
  has a deliverable target (their own docstrings say so); hiding them is a display-only filter.
- **Testing outbox-triggered emails end-to-end** (not just calling the builder function
  directly): `ham.outbox.api.emit`'s dispatch is deferred via `transaction.on_commit`, which
  never fires under pytest-django's default rolled-back wrapping transaction. Either (a) test
  the builder directly against a hand-built `OutboxEvent` (see
  `tests/integrations/test_notifications_subscriber.py`, `tests/identity/test_notifications.py`)
  — preferred, fast, no job plumbing — or (b) mark the specific test
  `@pytest.mark.django_db(transaction=True)` and call `ham.jobs.run_due_jobs_now()` once (it
  runs the queued `outbox.dispatch_delivery` job, which calls the subscriber synchronously) for
  a true end-to-end assertion. Don't expect `run_due_jobs_now()` alone to work without
  `transaction=True` for anything that goes through `ham.outbox.emit()`.
- **`conftest.py`'s `make_user` fixture does not create a `SharedIdentityProfile`** — a test
  asserting on a display name (e.g. an email builder's "so-and-so invited you") needs to create
  one explicitly (`SharedIdentityProfile.objects.create(user=..., full_name=...)`); otherwise
  `_display_name()`-style lookups fall back to "" (and thence to whatever the caller's fallback
  copy says, e.g. "A HAM leader").
- **`SharedIdentityProfile.display_name` abbreviates to first-name + last-initial** ("Kevin
  T.", not "Kevin Thompson") — this is deliberate (§68 "Kevin T." style everywhere a display
  name is shown), not a bug; don't write a test asserting the full name appears verbatim in a
  screen/email/API response driven by `display_name`.



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

## S2.0 additions: step 2 (Intake) seams and contracts
- **Full contract reference**: `docs/architecture/intake-contracts.md` — exact signatures,
  matrix actions, session/context shapes for S2.1-S2.5 to build against in parallel. Read it
  (and `docs/architecture/intake.md`'s owner-decisions box, which overrides the plan body)
  before touching any `ham.requests`/`ham.requester_portal`/`ham.media`/`ham.notifications`
  code.
- **Pseudo-principals are duck-typed siblings of `ActorContext`, not subclasses**:
  `ham.authz.context.RequesterContext`/`SystemContext` implement the same attribute/property
  surface (`user_id`, `roles`, `effective_roles`, `is_authenticated`, `is_impersonating`,
  `has_fresh_step_up`, ...) so `ham.authz.matrix.authorize()` and `ham.audit.services.record()`
  work on them unmodified. `ham.audit` must never import `ham.authz` (layering), so
  `record()` branches on `"REQUESTER"`/`"SYSTEM"` being *in* `ctx.roles` rather than
  `isinstance` — if you add a third pseudo-principal, follow the same duck-type pattern, don't
  add an import to break the cycle.
- **`Scope.OWN_REQUEST`** compares `resource.request_id` to `ctx.request_id` (never a
  `user_id` — a requester has no `User` row). Any action using it needs a `resource_from`
  returning something with a `.request_id` attribute (usually the `AssistanceRequest` row
  itself, or a 1:1 row exposing that attribute).
- **`ham.platform.otp`/`ham.platform.net`**: moved out of `ham.identity.authn`/
  `ham.web.auth_views` respectively so `ham.requester_portal`'s own code (own-code
  verification, public-form rate limiting) can reuse the exact reviewed logic without one
  domain module importing another. Both old call sites kept as thin re-exports (`_hash`/
  `_generate_code` in `authn.py`; `_client_ip = net.client_ip` in `auth_views.py`) because an
  existing test imports the old name directly — check for that pattern before renaming a
  "moved" helper's call sites away entirely.
- **`ham.platform.storage`**: a `Protocol`, not an ABC — `get_object_store()` does
  `import_string(settings.HAM_OBJECT_STORE_BACKEND)` and instantiates with no args, uncached
  (so `override_settings` swaps backends per-test cleanly once S2.4a lands a real
  implementation). Raises `RuntimeError` naming the setting if unconfigured, not an import
  error — there is no default backend in S2.0, this is a seam only.
- **import-linter `ignore_imports` entries must name an import that already exists somewhere
  in the tree**, or `lint-imports` fails with "No matches for ignored import ..." (exit 1, not
  a warning). Don't pre-declare an `ignore_imports` line for a file a *later* slice will
  create — add the exact entry in the same commit that adds the importing file. (The
  `pyproject.toml` layers/forbidden-modules contracts themselves are fine to extend early,
  since they key off packages that already exist once the empty `AppConfig` lands.)
- **A new `NavItem` with `built=False` still shows up in `ham.authz.nav.nav_for()`** (and
  therefore in every test that calls it directly, e.g. `tests/authz/test_nav_personas.py`'s
  exact-set assertions and `tests/authz/test_nav_mobile.py`'s "every full-nav item is
  reachable on mobile" check) — only `ham.web.nav`'s template-facing wrappers filter on
  `.built`. Update those tests' expected sets in the same change (add the new key to the
  personas that get the action; for the mobile reachability test, intersect `nav_for()`'s
  result with the *built* keys before asserting reachability, don't just add the new key to
  every mobile grouping — it isn't actually reachable yet, on purpose).
- **`tests/audit/test_command_registry.py`'s `READ_ONLY_ACTIONS`/`PLACEHOLDER_ACTIONS`
  frozensets need a new matrix row added to one of them the same time the row lands**, if the
  real `@command`-wrapped service isn't written yet in this slice — otherwise the static
  registry-coverage test fails immediately. Pure `.view`/`.list` actions go in
  `READ_ONLY_ACTIONS`; a mutating action whose service is a `NotImplementedError` stub goes in
  `PLACEHOLDER_ACTIONS` with a comment naming which later slice wires it.
- **`tests/authz/generate_expected_matrix.py`'s existing `_rows()` machinery (MFA gating,
  role-union, SELF scope in/out-of-bounds) assumes a human, multi-role-capable actor** — it
  doesn't fit `RequesterContext`/`SystemContext` (never more than one pseudo-role, no MFA, no
  impersonation). Added a **separate** `PSEUDO_ORACLE` dict + `_pseudo_rows()` generator
  instead of forcing pseudo-actions through `_rows()`; new CSV `scope_case` values
  `"own_request"`/`"other_request"`. `tests/authz/test_expected_matrix.py`'s `_ctx_for` builds
  a real `RequesterContext`/`SystemContext` (not a plain `ActorContext` with a made-up role
  string) whenever `row["role"]` is `"REQUESTER"`/`"SYSTEM"`, checked *before* the
  zero-role/disabled/mfa branches (those don't apply to pseudo-roles).
- **`ham.integrations.email.notifications.register_notification` now appends to a
  `dict[str, list[Builder]]`**, not a single-slot `dict[str, Builder]` — multiple modules can
  register a builder for the same `event_type` (e.g. one `RequestSubmitted` event eventually
  drives both a requester-facing email, from `ham.requester_portal.notifications`, and a
  leadership one, from a different module) and `handle_email_event` runs all of them.
  `unregister_notification(event_type)` still clears the whole list for that type (test-only
  helper; existing tests using it were unaffected by the shape change).
## S2.3 additions: requester portal (draft, verification, links, anti-abuse)
- **Parallel-worktree cross-app data without a model class to import**: when your slice's app
  sits above a sibling app that's being built concurrently in a different worktree (no models
  in your checkout yet), don't hand-import the not-yet-existing model or hit the DB table by
  name. Register a plain callable at the *other* app's `AppConfig.ready()` time, mirroring
  `ham.authz.commands`'s own `_register_audit_recorder`/`_register_outbox_emitter` pattern:
  `ham.requester_portal.services.register_request_facts_lookup(fn)` /
  `register_request_contact_lookup(fn)` / `register_email_to_request_ids_lookup(fn)` are the
  three seams S2.2 (`ham.requests`) must wire from `RequestsConfig.ready()` once merged. Each
  raises a loud `RuntimeError` if used before registration; tests register a fake directly.
  Document the exact callable shape in the module docstring AND in `intake-contracts.md` so
  the other slice's engineer doesn't have to read your source to find the seam.
- **A stub service signature committed by a parallel slice can be wrong for an edge case your
  slice needs** (S2.2's `submit_request(ctx, *, draft_id, verification_id: UUID)` has no way
  to express Q-025's "no email at all, no challenge exists" path, which needs
  `verification_id=None`). Don't silently paper over it by inventing a different call shape —
  call it as close to the documented contract as possible with a `# type: ignore[arg-type]` +
  a comment naming the mismatch, and flag it explicitly in both the contracts doc and your
  handback as a coordination item for the other slice's owner / the merge, rather than
  guessing which side should change.
- **A per-address resend cooldown and "send N emails to N different requests for the same
  address in one request" are different rules that can collide**: `find_my_request` (Q-117
  "one email per matching request") calling the same code-sending helper once per request id
  for one email address will immediately hit that helper's own per-address cooldown on the
  second call. Give the helper an explicit `bypass_cooldown=` escape hatch for exactly this
  internal fan-out, while leaving the hourly per-address cap in place — don't weaken the
  cooldown itself, since it still needs to block a person mashing "resend" for one request.
- **Building a route's confirm/redemption URL before the route exists**: `ham.identity.authn`
  gets away with `django.urls.reverse()` for its sign-in link because that URL already exists.
  A parallel/later slice's not-yet-built public route (here, S2.7's `/request-help/verify/
  link/<token>`) can't be `reverse()`d yet (`NoReverseMatch` would break every test touching
  the emailing code). Hard-code the literal path string instead (matching the architecture
  plan's route table exactly), in one small `dict`/constant, with a comment pointing at who
  owns building the real route and where the contract doc says so — swap to `reverse()` once
  the URL exists, in whichever slice lands second.
- **A resume/continue cookie only needs to be a signed cookie holding an opaque id** — Q-139
  "resume in the same browser only, no details shown" doesn't need any device-fingerprinting
  or session-binding logic: a cookie is inherently sent only by the browser that received it,
  and never decrypting/echoing the draft's payload back into any response is what actually
  keeps "no details shown" true. `django.core.signing.dumps/loads(..., max_age=...)` (not a
  bespoke HMAC scheme) is enough; mirror the draft's own `expires_at` as the cookie's `max_age`
  so a stale cookie and an actually-expired draft go stale at the same time.
- **A multi-step public wizard's field validation doesn't fit one `django.forms.Form`
  cleanly** when answers accumulate into one encrypted draft across several requests/pages:
  validate the *whole* merged payload once, in a plain function over a dict
  (`ham.requester_portal.forms.validate_intake_payload(data, *, church) -> (cleaned | None,
  errors)`), called right before the verification code is sent — not per-step. Keep per-field
  fixed vocabularies (category/property-type/hazard/relationship enums) in a sibling
  `choices.py`, not inline in the validator, so a later screen-building slice can import the
  exact same value strings for its `<select>`/radio options.
- **`ham.platform.otp` needed one more primitive for token-based *lookup* (not just
  verify-against-a-known-hash)**: `hash_candidates(value) -> list[str]` (HMAC under every
  configured `HAM_TOKEN_HMAC_KEYS`, not just the first) lets a caller do
  `Model.objects.filter(token_hash__in=hash_candidates(token))` when it doesn't yet know which
  key originally hashed a given stored row — `hash_matches` alone can't do this since it takes
  the expected hash as an input, not a thing to search for.
- **A church-profile "days served" setting used only by a public form** (`ChurchProfile.
  serves_days`, Q-112, ISO weekday ints 1=Mon..7=Sun, default Sun-Fri = `[1,2,3,4,5,7]`) is a
  content/config field, not a `ham.rules` value (no timedelta/limit/weight) — it lives on the
  existing `platform_church_profile` row/migration like `time_zone`, exposed via
  `ChurchProfileView.serves_days`. When extending an existing admin settings POST handler
  (`views_admin_settings.admin_church_settings`) with a new field a screen doesn't render yet,
  make the handler treat the key's *absence* from `request.POST` as "leave unchanged" (not
  "clear it to empty and fail validation") — otherwise every existing caller/test of that
  endpoint breaks the moment you add a required-when-present field.
- **Two engineers both owning a model the architecture plan assigned to one specific app**:
  intake.md's data-model section put `IntakeSource` under `ham.requests` (a sibling app being
  built in a different worktree, in parallel, with no such model yet in this checkout). Rather
  than block on that slice landing first, define it locally in the app that actually needs the
  lookup now (`ham.requester_portal.models.IntakeSource`, distinct `db_table`), with a loud
  comment on the model **and** in the contracts doc naming the collision and saying "keep
  exactly one of these at merge." Silently working around a plan's file-ownership assignment
  without flagging it is worse than flagging it and building the pragmatic version.

- **App label collisions**: the new step-2 apps use short Django `label=`s
  (`requests`, `requester_portal`, `ham_media`, `ham_notifications`) distinct from their
  `name=` (`ham.requests`, etc.) — `ham.media`'s default label would've been `media`, which is
  fine, but `ham_media`/`ham_notifications` were chosen defensively since `media`/
  `notifications` are common third-party app names elsewhere; keep an eye out if a future
  dependency wants the plain name.
