# ham-backend-engineer — conventions from slices S1 (platform skeleton) + S3a (identity/authz/audit) + S3b (auth) + Fix B (parallel security/PRD fixes) + round-3 re-review fixes + Fix A (step-2 intake fix round)

## Fix A (step-2 intake fix round, parallel with Fix B/Fix C)
- **A verified-code/link "challenge" must be bound to the exact draft AND the exact email it
  will submit, at the moment of submission, not just at code-request time.** H1's exploit:
  send a code to address A, edit the *same draft* to address V before entering the code,
  submit with A's code — the draft's *current* email (V) got created with "email confirmed"
  recorded, never actually verified. Fix, all three parts required together: (1) re-fetch the
  challenge by id inside `submit_and_issue_link`'s own `transaction.atomic()` with
  `select_for_update()` and check `purpose`, `consumed_at is not None`, `draft_id == this
  draft`, `email_key == hash(the email actually being submitted)`, and `request_id is None`
  (a one-time-use marker — set it to the new request's id right after creating it, since a
  purpose="intake" challenge never otherwise gets `request_id`); (2) `ham.web.views_requester.
  _after_verified` must use `challenge.draft_id`, never the browser's resume cookie, to pick
  which draft to submit; (3) `ham.requester_portal.drafts.save_step` must expire (not just
  leave unconsumed) any not-yet-consumed intake challenge for a draft the moment its email
  changes — set `expires_at` strictly *before* "now" (`now - timedelta(seconds=1)`, not
  `now`), since a `FixedClock`-driven test (and a fast enough real request) can hit `now ==
  challenge.expires_at` and the existing `if now > challenge.expires_at` check treats equal
  as still-valid.
- **"Identical UI for every outcome" (sent/cooldown/rate-limited) must be true at the
  *message* layer, not just the returned status enum.** H2: a distinct "too many codes"
  flash message on the *sender's own* screen is still an oracle when the sender is
  intentionally probing an arbitrary target address (find-my-request N times, then try
  intake with the same address — the message differs only when a request already existed).
  Fix at both ends: (a) the rate-limit *counters themselves* must be scoped per purpose
  (`RequesterVerificationChallenge.objects.filter(..., purpose=purpose, ...)` — a missing
  `purpose=` filter on the hourly-cap count, while the cooldown check right above it already
  had one, silently shared the budget across "intake" and "link_regeneration"); (b) the
  *caller* must render the exact same thing (redirect, no message, or one fixed message)
  regardless of `ChallengeRequestResult.status` — don't even destructure/branch on it.
- **A per-address abuse counter is itself abusable as a denial-of-service against a real
  person's address, unless it's scoped to something the abuser can't freely fabricate.** L6:
  anyone can type any email into their own draft (no proof of ownership until the code is
  entered) and then guess wrong codes against it, and the old daily wrong-attempt cap summed
  `failed_attempts` across every challenge sharing that `email_key`, regardless of whose
  draft/request it belonged to — locking the real owner out for a day. Rescoped to
  `draft_id` (or `request_id` for link-regeneration) **plus** `ip_address`, both threaded
  through `verification.verify_code(..., draft_id=..., request_id=..., ip_address=...)` from
  the view (session already has `pending["draft_id"]` for intake, `_pending_link_regen_
  request_id` for regeneration) — an attacker can never guess someone else's `draft_id`
  (UUID7), so this closes the hole without weakening the legitimate 5-tries-then-locked
  behavior for one's own attempt.
- **A "was this locked out?" audit event (`requester_verification.locked`, M6/N13) had been
  declared in `ham/audit/labels.py` since S2.0 but nothing ever called `audit_record` for
  it** — a label existing is not evidence the event fires; grep the actual call site, not
  just the labels table, when a review says "X is never audited". Written with `ctx=None,
  actor_type=ACTOR_TYPE_SYSTEM` (no signed-in actor exists on this public path) and
  `target_id` = the draft/request UUID (never `email_key`, even though that's already an
  HMAC digest and not literally "the address" — the review wanted something more useful to
  investigate, and a draft/request id is exactly as address-free).
- **New `ham.rules.intake` values need the full four-step protocol even for a "closes an
  enforcement gap" fix, not just a "new feature" one**: `REQUESTER_CODE_EMAILS_PER_IP_PER_HOUR`
  (Q-121 provisional, mirrors the existing per-address cap) and
  `NO_EMAIL_SUBMISSIONS_PER_PHONE_PER_DAY` (Q-146, decided — "3 per phone per rolling 24h")
  both needed `RULES_VERSION` bumped, a `docs/rules-changelog.md` entry, a new `PINNED_HASHES`
  line (compute via `python -c "from ham.rules import RULES, content_hash;
  print(content_hash(RULES))"` after editing `v1.py`), and new expected entries in BOTH
  `tests/rules/test_rules_values.py`'s `EXPECTED` dict AND `tests/rules/test_rules_module.py`'s
  `test_exactly_these_rules_run_on_a_proposed_default` dict (the latter is easy to miss —
  it's a second, independent oracle for exactly which rules are marked `provisional=`).
- **A submission-time rate limit belongs in the caller that's about to create the row, not
  at code-send time** — `INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY`/`NO_EMAIL_SUBMISSIONS_PER_
  PHONE_PER_DAY` (Q-146) are enforced inside `submit_and_issue_link`, right before calling
  `submit_request`, using two new counting queries in `ham.requests.queries`
  (`recent_submission_count_for_email`/`recent_no_email_submission_count_for_phone`, both
  `otp.hash_candidates()`-based so key rotation doesn't break them) — a person can hold
  several still-valid, already-verified codes from earlier in the day, so gating only at
  code-request time would miss a burst of submissions from codes requested well before the
  cap was reached. Raises `ham.requester_portal.services.IntakeSubmissionRateLimited` (not a
  bare `ValueError`, so the view can special-case it: the no-email path shows the exact same
  "saved" confirmation as its honeypot trip, never revealing a cap exists; the email path
  folds it into the same "answers expired, start again" `ValueError` handling for the same
  H2 reason).
- **A per-IP counter needs its own dedicated log table when the thing it counts doesn't
  otherwise create a row on every attempt.** `FIND_REQUEST_TRIES_PER_IP_PER_HOUR`
  (M1) — `find_my_request` only ever creates a `RequesterVerificationChallenge` row when the
  address happens to match a real request; an unmatched try leaves no trace to count. New
  minimal model `ham.requester_portal.models.FindRequestAttempt` (`ip_address`,
  `created_at`, nothing else) logs every try regardless of match; purged hourly on the same
  `REQUESTER_CHALLENGE_RETENTION` window as the other rate-limit-only rows
  (`ham.requester_portal.jobs.purge_expired_find_attempts`, new).
- **Three independently-invented copies of the "same" fixed vocabulary is a recurring failure
  mode across this codebase's parallel-worktree history, not a one-off** — B1 found a third
  copy of the certification tick-box wording (a template literal, in addition to the two
  Python modules `ham.requests.certifications` and `ham.requester_portal.attestation` already
  flagged in an earlier slice's memory note) and M1/UX-M2 found a second copy of need-category/
  property-type (`ham.requester_portal.choices.NeedCategory`/`PropertyType`, translated into
  `ham.requests.models`' different codes only at submission time via a manually-maintained
  dict). **Fix pattern, both times: pick the LOWER-layer module as canonical (`ham.requests`,
  since `ham.requester_portal` may import it downward but not the reverse), delete the
  duplicate(s) entirely (not just stop using them — a leftover unused copy is exactly how the
  drift happens again), and have the upper layer re-export/import the canonical names so
  existing call sites don't all need touching.** For certifications specifically: also stop
  *re-deriving* "the statements this relationship requires" at submission time
  (`certifications.required_statements(relationship)`) and instead store exactly
  `cleaned["attested_statements"]` (what was actually ticked, already validated by
  `certifications.statements_satisfied` upstream) — re-deriving silently discards the
  distinction between "ticked" and "required", which matters for an eventual audit trail even
  though the two sets are equal by construction today. `ham.web.views_requester`'s R6 context
  now gets `statement_text` (from `certifications.statement_text_for(relationship)`) instead
  of the template hard-coding its own wording, so "stored text == rendered text" is provable
  in one test (`tests/requests/test_fix_a_certifications.py`) rather than trusted by
  inspection.
- **The lower-layer module (`ham.requests`) is where a field-max-length bump belongs when
  unifying two vocabularies picks the longer of two code sets** — `NeedCategory` codes went
  from the old ≤16-char set to the portal's own (up to 22 chars, `ramps_rails_grab_bars`);
  `AssistanceRequest.need_category`'s `max_length` needed bumping to 32 in the same migration,
  or the choice values would silently truncate on `.create()` (Django doesn't validate
  `choices=` OR `max_length=` together at write time — this would NOT raise, it would just
  store truncated garbage).
- **`Requester.phone_key`/`email_key` are HMAC digests of the *normalized* value
  (`ham.requests.matching.normalize_phone`/`normalize_email`), never the raw input** — a new
  counting query keyed on phone (`recent_no_email_submission_count_for_phone`) must receive
  an already-normalized phone string (`cleaned["phone"]` from `ham.requester_portal.forms`,
  which already ran it through `normalize_phone`), not the raw form field, or
  `otp.hash_candidates()` will never match anything.
- **L7/Q-151 (an Administrator must never see unmasked requester contact details, even by
  impersonating someone who normally could): `ActorContext.roles`/`.effective_roles` reflect
  the impersonation *target's* roles while impersonating, and there is no field anywhere
  carrying the real actor's own roles** — `ham.identity.middleware.build_actor_context` never
  populates one (by design: PRD-guardian review Major 6(b) already established "while
  impersonating, `ActorContext.roles` reflects [the target]"). New
  `ham.identity.services.user_holds_global_role(user_id, role) -> bool` is the one seam a
  caller *outside* `ham.identity` should use to ask "does the real signed-in person (`ctx.
  real_user_id`) hold this role", rather than querying `RoleAssignment` directly (forbidden
  by "only ham.identity reads auth tables") or trying to smuggle it through `ActorContext`
  (would need touching every context-building site). `ham.requests.services.
  reveal_requester_pii` calls it only when `ctx.is_impersonating`, and only to *downgrade* an
  otherwise-`allowed` `Decision` to denied via `dataclasses.replace(decision, allowed=False,
  reason=...)` — this is a service-layer check, same shape as the existing Q-024
  non-impersonating-Director exemption right next to it, not a matrix change (the matrix has
  no notion of "the real actor while impersonating"), so `tests/authz/generate_expected_
  matrix.py`'s oracle needed no update for it.
- **A `select_for_update()` used only for "read the row I'm about to validate, before
  mutating something derived from it" (not itself the row being updated) still needs to sit
  *inside* the same `transaction.atomic()` block as the eventual write** — H1's challenge
  validation originally sat *before* `submit_and_issue_link`'s `with transaction.atomic():`,
  which raises `TransactionManagementError` under Postgres/psycopg (Django wraps it oddly:
  the visible exception ends up being `Model.DoesNotExist` from deep inside `QuerySet.get()`,
  not the `TransactionManagementError` itself — don't trust the surface exception type when
  debugging a "matching query does not exist" that shouldn't be possible; check whether a
  `select_for_update()` a few frames up is the real culprit first).
- **A queryset `.update()` legitimately bypasses a model's own append-only `save()` guard for
  a genuine system-level erasure, and this is the intended escape hatch, not a bug to fix** —
  `RequestContactVerification.save()` refuses any update (Python-level append-only guard,
  S2.2), but L8/Q-145's 7-year purge sweep needs to blank its `value_key` too. Django's bulk
  `.update()` never calls `Model.save()`, so
  `RequestContactVerification.objects.filter(request=request).update(value_key="")` inside
  `purge_expired_request` is correct and deliberate: it's retiring a hashed value system-wide
  during a scheduled erasure, not editing any individual row's own history the append-only
  guard exists to protect.
- **A model with a plain `UUIDField` reference (not a real FK) to a row a *sibling* app can
  delete needs its own outbox-subscriber cleanup, mirroring `ham.media`'s existing
  `RequestCancelled` handler exactly** — L4: `ham.requester_portal.RequesterAccessLink`/
  `RequesterVerificationChallenge.request_id` don't cascade when `ham.requests.services.
  purge_expired_request`'s spam branch calls `request.delete()` (can't be a real FK across
  these two apps' parallel-worktree history, intake.md §2 layering). Added a `RequestPurged`
  outbox event to that `CommandResult` and a new `ham.requester_portal.subscribers.
  handle_requester_portal_event` (registered `"requester_portal"` from `RequesterPortalConfig.
  ready()`, same `ham.outbox.registry.register(name, handler)` call every other subscriber
  uses) that deletes both tables' orphan-to-be rows. Also added a defense-in-depth fallback at
  the read side regardless: `ham.requester_portal.services.resolve_token` now catches the
  `ValueError` a stale/orphaned `request_id` raises from the registered facts-lookup and
  treats it as an invalid token (same page as unknown/expired), instead of letting it 500 —
  covers the window before the subscriber runs, or any other future orphaning path.
- **L2: scope a lookup *before* touching `authorize()`/audit at all, not just before deciding
  what to return** — `reveal_requester_pii`'s old `AssistanceRequest.objects.get(pk=
  request_id)` both 500'd on an unknown id (unhandled `DoesNotExist`) and let a Pastor/Board
  rep "reveal" a still-`NEEDS_PHONE_CHECK` request (Q-025: Director/AD-only) by guessing its
  UUID directly, since the matrix rule for `requester_pii.reveal` has no status-awareness of
  its own. Fixed by reusing the exact scoping every list screen already applies
  (`ham.requests.queries.get_request_by_id`, itself built on `scope_queryset_for_requests`) as
  the *first* thing this function does — an unknown id and an out-of-scope id now produce the
  identical `PermissionDenied` outcome (audited the same way as any other denial), never a 500.
- **N8 (history timeline losing entries after a later status change): don't derive "did this
  request ever reach status X" from `request.status == X` (the *current* status) when the
  point is to show it happened at some point in the past** — `request.awaiting_approval_at`
  (new, set once by `complete_intake_checks`, never cleared) replaces the old `if request.
  status in (AWAITING_APPROVAL,)` check in `ham.requests.queries.request_history`, which
  silently dropped the "Awaiting Approval (automatic)" entry the moment a request was later
  cancelled. Same slice added `AssistanceRequest.closed_by_user_id` (set by `cancel_request`
  from `ctx.user_id`) so the close entry finally has an actor — `display_names_for` in
  `ham.web.views_requests` already resolves any `HistoryEntry.actor_user_id`, no view change
  needed beyond the query.
- **`ham.requests.certifications`/`ham.requests.models` PRD-guardian N1 Q-reference
  fixes**: cite the actual decided/open question number, not a nearby one that happens to be
  about a related topic (`Q-102`→`Q-103` for the certification wording, `Q-107`→`Q-109` for
  need category, `Q-124`→`Q-111` for contact method — and Q-111 doesn't offer `text_message`
  at all, so the model's `PreferredContactMethod.TEXT_MESSAGE` choice was removed, not just
  re-cited). Cross-check the *specific* Q number's own row in `docs/prd-open-questions.md`,
  don't assume a docstring's existing citation is right just because it's in the right
  neighborhood.
- **N2: an unwired matrix action is worse than a missing one, not a convenience for later** —
  `request.create_assisted` had a full `ActionRule` (Director/AD/Pastor, blocked-while-
  impersonating) and appeared in every audit-registry/oracle bookkeeping list, but no
  `@command`-wrapped service ever implemented it — an unused permission grant with no
  corresponding audited action behind it. Removed outright (matrix row, `_AUDITED_ON_DENIAL`
  entry, the oracle's row in `generate_expected_matrix.py`, `PLACEHOLDER_ACTIONS` entry in
  `test_command_registry.py`) rather than left "for a later slice to implement" — regenerate
  `expected_matrix.csv` (`python tests/authz/generate_expected_matrix.py`) and
  `permission-matrix.md` (`manage.py build_permission_matrix`) in the same commit as any
  matrix.py row removal, not just an addition; `build_permission_matrix --check` catches a
  stale doc either direction.
- **Q-147 (state prefill): a fixed reference vocabulary that a *different* model
  (`ChurchProfile`, `ham.platform`) also needs to validate belongs in `ham.platform`, not
  the app that happens to need it first** — `US_STATE_CODES`/`is_valid_us_state` live in
  `ham.platform.church` (next to `is_valid_time_zone`, same shape) even though the immediate
  trigger was the public intake form's R3 state field, because `ham.identity.services.
  update_church_profile` (Admin church settings) needed the identical validation for the new
  `ChurchProfile.state` field. `ham.requester_portal.forms` imports it downward, same as
  every other cross-app fixed-vocabulary reuse in this codebase.
- **A per-request field the admin settings screen's template doesn't render yet must not be
  silently cleared by every *other* field's save** — `views_admin_settings.admin_church_
  settings`'s POST handler rebuilds its whole `values` dict from `request.POST.get(key, "")`
  for most fields (unlike `serves_days`, which already has an explicit "key absent = leave
  unchanged" branch, per an earlier slice's memory note). Adding `state` the same naive way
  would reset it to `""` on every unrelated save until a template renders the field. Fixed
  with `request.POST.get("state", church.state)` (default to the *current* value, not `""`)
  — the same pattern any future field added ahead of its own template landing should follow.

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

## S2.5 additions: notifications module (Notification, inapp subscriber, attention registry)
- **`ham.notifications.inapp.register_inapp`/`handle_inapp_event`** is an exact mirror of
  `ham.integrations.email.notifications.register_notification`/`handle_email_event` (list of
  builders per event type, builder returns `None`/one/`list[InAppNotice]`), but it is
  registered as the `"inapp"` outbox subscriber from **`NotificationsConfig.ready()` itself**,
  not from `IntegrationsConfig` — intake.md §2 calls this "internal, not a third party": since
  `ham.notifications` sits at the bottom of the domain-module stack (just above
  `ham.identity`), it can own its own outbox integration without triggering the "domain
  modules never import `ham.integrations` directly" contract at all (no `ignore_imports` entry
  needed, unlike every other domain module's `.notifications.py`).
- **`Notification.title` gets its own PII guard** (`ham.notifications.validation.check_title`,
  reusing `ham.platform.logging.EMAIL_RE`/`PHONE_RE`), called from `handle_inapp_event` before
  every `Notification.objects.create(...)` — mirrors `ham.outbox.validation.validate_payload`
  but is a separate, smaller check (title is one free-text field, not an arbitrary payload
  dict) rather than reusing the outbox validator directly.
- **"Needs response" has no table.** `ham.notifications.attention` is a second, independent
  registry (`register_attention_provider(fn)`, `fn(ctx) -> list[AttentionItem]`,
  `attention_items_for(ctx)` concatenates every provider) — completely separate from
  `register_inapp`. A provider returns already-aggregated, PII-free rows (e.g. "Waiting for a
  decision (3)"); nothing is stored, so resolving the underlying thing (e.g. a request leaving
  Awaiting Approval) clears the card everywhere for free. `AttentionItem.muted` (Director/AD
  see pastors'/Board's rows, de-emphasized, **not hidden**, and **excluded from the badge
  count** — intake.md §6) is a per-item flag the *provider* sets based on the actor's role, not
  something the registry computes; `needs_response_count(ctx)` sums `count` for non-muted items
  only, `needs_response_for(ctx)` returns everything (view renders muted differently).
- **Read vs. acknowledge, two very different authorization shapes for the same table.** Marking
  an Update read is scoped by plain ownership-filter-in-the-query
  (`Notification.objects.filter(pk=..., recipient_user_id=ctx.user_id)`), gated only by the
  route's `shell.use`, and is **not** a `@command`/not audited — same rationale as "page views
  ... are not audited" (intake.md §9.8): it changes nothing another party can observe.
  Acknowledging (`notification.acknowledge`, `Scope.SELF`, `blocked_while_impersonating=True`,
  already declared in the matrix by S2.0) *is* a `@command`, because it is what makes the
  urgent banner (§10/§35) disappear. Wiring pattern for a `Scope.SELF` action keyed by a
  specific row (not "always yourself" like `me.update`'s `_resource_self` returning `ctx`
  outright): `resource_from` loads the row and returns `SimpleNamespace(user_id=row.
  recipient_user_id)` if found, or `None` if not — `Scope._self_scope_ok` treats a `None`
  resource as "nothing to check yet, let the service body raise" (same escape hatch role-grant
  finer-grained checks use), so a bad id gets a plain `ValueError` from inside the service
  rather than a scope denial that would otherwise require a second DB read just to build the
  `Decision`.
- **`identity.services.notification_recipients(roles: Iterable[str]) ->
  list[tuple[UUID, str, bool]]`** (user_id, email, notify_email) is the one function this slice
  added to `ham.identity` (intake-contracts.md §7's "only ham.identity reads auth tables"
  rule) — filters `role_assignments__role__in=role_set, revoked_at__isnull=True,
  is_active=True, disabled_at__isnull=True`, de-dupes with a manual `seen: set[UUID]` (not
  `.distinct()`) because a JOIN against `role_assignments__role__in={A, B}` returns one row per
  matching assignment, so a user holding *both* roles in the set would otherwise appear twice;
  `user.profile.notify_email` is wrapped in `except ObjectDoesNotExist: notify_email = True`
  since `SharedIdentityProfile` is only reliably created via `get_or_create` at bootstrap/
  invite time, not guaranteed for every row a test or edge case might create.
- **New `tests/notifications/` package** (`__init__.py`, `test_inapp.py`, `test_attention.py`,
  `test_services.py`) — first backend slice to add a whole new top-level `tests/<app>/`
  directory outside the ones S1/S2.0 already scaffolded; nothing extra was needed (pytest
  picks it up via `testpaths = ["tests", "ham"]`, no per-directory conftest required beyond the
  shared `tests/conftest.py`'s `make_user`/`_reset_clock`).
- **Retention for `Notification` rows is an explicit, intentional gap** (task brief: "note the
  gap; don't invent a value") — intake.md's D4/Q-116 retention decision covers
  `AssistanceRequest`/`Requester`/`Property`, not this table; no `ham.rules` constant exists or
  was added for it. Don't backfill one without an owner decision.
## S2.2 additions: requests core (models, submit/cancel/reveal/duplicate-check, retention)
- **A "guarded, best-effort" call into a *higher* layer's stub does NOT satisfy import-linter,
  even wrapped in try/except.** wave2-common.md's cross-slice coordination note said S2.2
  should call `ham.requester_portal.services.issue_link` from inside `submit_request`,
  "guarded, since it may still be a stub" (mirroring how S2.2 was told to fake its own
  inputs). But `ham.requests` sits *below* `ham.requester_portal` in intake.md §2's layer
  order, and `lint-imports`'s `layers` contract statically flags the import statement itself
  — a lazy `from ham.requester_portal.services import issue_link` inside a function body,
  guarded by `try/except ImportError`/`NotImplementedError`, still breaks the contract exactly
  like a top-level import (import-linter does static analysis, not runtime tracing). Don't
  trust a coordination doc's shortcut instruction over the architecture doc's own module
  boundary rule when the two conflict — intake.md §2 itself already says the correct owner
  ("The portal orchestrates submission: it verifies the draft, calls
  `requests.services.submit_request`, then issues the link, all in one transaction"), i.e.
  the *caller* (the higher layer) does both calls, never the callee reaching back up. Resolve
  by keeping the lower-layer function self-contained and documenting the deviation loudly in
  the module docstring (don't silently drop the instruction) rather than adding a same-slice
  `ignore_imports` exception for something the plan already assigns to the other side.
- **Two-way audit split for one duplicate-check run**: intake.md §4 wants both
  `request.status_changed` *and* `request.duplicates_flagged` when the duplicate scan finds a
  match, but `@command`'s wrapper only ever writes the ONE audit event named by the returned
  `CommandResult`. Write the second event by hand with `ham.audit.services.record(...)`
  directly from inside the wrapped function body — it's safe because the wrapper's own
  `with transaction.atomic()` is already open while that body runs, so both rows land in the
  same transaction as everything else.
- **One `@command("action")` site, even for two different real-world outcomes**:
  `tests/audit/test_command_registry.py::test_no_command_action_is_defined_twice_with_
  different_wiring` fails if the SAME matrix action string appears in two separate
  `@command(...)` decorator sites (e.g. "purge PII" vs "purge a spam request" both being
  `system.intake.purge`). Write one function that branches internally
  (`ham.requests.services.purge_expired_request`) and have the periodic job call that one
  function for every eligible id from either eligibility list, instead of two decorated
  functions.
- **A reveal that is *sometimes not audited* (Q-024's non-impersonating-Director exemption)
  can't be a plain `@command`** — the wrapper always writes exactly one audit event per call.
  `ham.requests.services.reveal_requester_pii` is manually wired instead, same shape as
  `ham.authz.audit_access.export_csv` (call `ham.authz.matrix.authorize` directly, hand-write
  the `authz.denied` audit on denial, `ham.audit.services.record` only when not exempt). Add
  the action to `tests/audit/test_command_registry.py`'s `MANUALLY_WIRED_ACTIONS`, not
  `PLACEHOLDER_ACTIONS` — it *is* wired, just not through the decorator.
- **A field whose NULL has a distinct business meaning needs `# noqa: DJ001`, not `blank=True,
  default=""`**: ruff's Django plugin (DJ001) flags any nullable string field, but
  `Requester.email` (Q-025: NULL means "chose 'I don't use email'", not "typed nothing") and
  the HMAC match-key columns (NULL means "no reliable key could be computed" —
  `ham.requests.matching.match_keys`/`find_matches` never treat `""` as a key, so an empty
  string would wrongly equal every other un-keyable row) both need real NULL. Silence the
  linter per-field with a comment explaining *why*, don't cave to the "no null on CharField"
  default just to quiet ruff.
- **`ham.requests.models.next_reference_number()`**: a raw `SELECT nextval('requests_
  reference_number_seq')` via `django.db.connection.cursor()`, called once inside the
  `@command`'s transaction, is how "HAM #047" (intake.md §3: "int, unique, from a Postgres
  sequence") is generated — Django has no clean built-in for "a second, non-PK auto-increment
  column"; a hand-created `migrations.RunSQL("CREATE SEQUENCE ...")` ahead of the
  `CreateModel` operation, with a matching `PositiveIntegerField(unique=True, editable=False)`
  and no DB-side `DEFAULT`, is the pattern (the app always supplies the value explicitly, so a
  server default isn't needed and isn't fought by Django's migration autodetector on the next
  `makemigrations`).
- **`ham/authz/scopes.py` grew a second, action-keyed registry** (`register_queryset_scope_
  provider(action, fn)` / used by `scope_queryset(ctx, action, queryset)`) alongside the
  existing per-`Scope`-enum `register_scope_provider` — the existing one answers "is this ONE
  resource in scope" for `authorize()`; list screens like `request.list` need to filter a
  whole queryset (e.g. hiding NEEDS_PHONE_CHECK rows from everyone but Director/AD, Q-025) and
  `Scope.ANY` (what `request.list` uses) has no per-resource meaning to check against. This
  was anticipated but not built in S2.0's `scope_queryset` stub ("which will register a
  provider here instead of overriding this function") — S2.2 is the first slice to actually
  register one, from `RequestsConfig.ready()`.
- **A registry a parallel slice might not have landed yet gets a guarded, try/except-ImportError
  registration call from `ready()`, never a hard import at module scope** — this IS safe with
  import-linter as long as the registry being reached into is in a LOWER or SIBLING layer
  never imported statically elsewhere first; `ham.notifications` (attention-provider registry,
  S2.5) sits below `ham.requests` in the layer order, so `ham.requests.apps.RequestsConfig.
  ready()` importing `ham.notifications.registry` — even guarded — is fine (unlike the
  `issue_link` case above, which was the *wrong direction*). Check which way the arrow points
  before assuming "guarded import" is always a safe escape hatch.
- **Retention (Q-127) needs the request row to *survive* an ordinary PII purge but be fully
  *deleted* for a spam close** — `purge_expired_request` branches on
  `cancel_reason_code == CancelReason.SPAM`: spam calls `request.delete()` (cascades to
  `Requester`/`Property`/etc.); anything else blanks only the P fields on `Requester`/
  `Property` and sets `Requester.anonymized_at`, leaving the `AssistanceRequest` row (status,
  category, ZIP... it's on `Property`, so actually ZIP survives too since only
  line1/line2/city/owner_name are blanked) intact for "families served"-style reporting.
- **`SubmittedRequestPayload` (`ham.requests.services`)**: the concrete shape S2.3
  (`ham.requester_portal`)'s orchestration must build from its decrypted `IntakeDraft` and
  pass to `submit_request` as a new required `payload=` kwarg, on top of the S2.0 stub's
  `draft_id`/`verification_id` (kept for traceability only, not dereferenced by this module —
  see the layering note above for why). Check this dataclass's field list before S2.3 builds
  its draft-to-payload mapping; it's additive, not a replacement contract.
## S2.4a/S2.4b additions: object storage adapters + media domain
- **`ObjectStore` protocol grew two methods beyond S2.0's original four** (`get_object`/
  `put_object`, plain byte-level read/write): browsers use presigned PUT/GET (no storage
  credentials client-side), but a **worker** re-encoding a file (Q-120) is trusted
  infrastructure with its own real credentials and has no reason to round-trip through a URL
  it would have to presign to itself. Safe to extend the protocol this way only because
  nothing else consumed it yet (`grep` first before adding to a "frozen" seam another slice
  defined — if callers already exist, coordinate instead of silently widening the interface).
- **Local dev "presigned URL" = a signed, time-limited, single-purpose Django URL, not a real
  presign.** `ham.integrations.storage.local.LocalObjectStore` builds a `django.core.signing.
  Signer.sign_object({"op": "put"/"get", "key", "exp", ...})` token (no `TimestampSigner`
  needed — the payload carries its own explicit `exp` ISO string so verification doesn't
  depend on wall-clock sync between issue and check being exactly right); `ham.integrations.
  storage.dev_views.local_storage_object` is the one view that verifies+serves it. It's listed
  in `ham.authz.guard.PUBLIC_ROUTES` (url name `local-storage-object`) — the token itself *is*
  the capability, same reasoning as the sign-in family, not an `ActorContext` check. Mounted
  unconditionally in `config/urls.py` (not gated by `DEBUG`) so `pytest` (which runs with
  `DEBUG=False`) can still exercise the real PUT/GET round trip end-to-end via Django's test
  `Client`, not just call adapter methods directly.
- **`R2ObjectStore` (boto3, S3-compatible) has no `moto` in this sandbox** — tests mock
  `boto3.client` directly (`unittest.mock.patch("ham.integrations.storage.s3.boto3.client")`)
  and assert on call args (bucket/key/ExpiresIn/etc.) plus the 404-vs-other-error branch in
  `head()`. Good enough to pin the contract; add `moto` later if a fuller integration test is
  wanted. R2 needs `signature_version="s3v4"` + `addressing_style="path"` in `botocore.client.
  Config` — AWS's default virtual-hosted-style addressing doesn't work against R2's endpoint.
- **`HAM_OBJECT_STORE_BACKEND` now defaults to the local adapter** (`config/settings/base.py`),
  not empty — S2.0 shipped no default on purpose ("no concrete backend exists yet"); S2.4a
  landing the local adapter is what makes a real default safe. Don't remove the default
  without checking nothing depends on the old "must configure explicitly" `RuntimeError` path
  in a test.
- **Batch reservation's real concurrency hazard is "no batch exists yet", not "the batch is
  full".** `select_for_update()` on `RequestMediaBatch` has nothing to lock when the row
  doesn't exist — two concurrent "open the initial batch" calls for the same request both see
  "no open batch" and race to `INSERT` batch #1, tripping the `(request, number)` unique
  constraint instead of serializing cleanly. Fix: lock the **parent** `AssistanceRequest` row
  (`select_for_update().get(id=request_id)`) first, inside the same transaction, before the
  get-or-create — every concurrent reservation/reopen for that request then serializes on that
  lock. Proved this with a real `threading` + `pytest.mark.django_db(transaction=True)` test
  (`connections.close_all()` in each thread's `finally`, since Django connections are
  thread-local) — a test that only calls the service sequentially from one thread would never
  have caught it; select_for_update-on-a-nonexistent-row races only show up under genuine
  concurrent transactions.
- **"Consequential enough to audit" is narrower than "every DB write."** `reserve_uploads`
  (reserving upload slots + presigning PUT URLs) is a plain service function, not
  `@command`-wrapped, even though it creates rows — it isn't in intake.md §6's declared
  audit-action list (only `request_media.uploaded`/`.rejected`/`.removed`/`.batch_opened`
  are), and an abandoned reservation just times out (`MEDIA_UPLOAD_INTENT_LIFETIME`) with no
  lasting effect. Its authorization is the calling view's own `@requires_action(
  "requester.media.upload")` route guard (foundation.md §7), same pattern as
  `ham.identity.services.list_users`. `complete_upload`/`remove_item`/`reopen_batch` (state
  changes another party can observe) are all `@command`-wrapped. Don't assume "creates a row"
  implies "needs `@command`" — check the plan's declared audit-action list first.
- **Administrator-sees-counts-only (Q-138) is service-layer masking, not a second matrix
  action** — same pattern as `requester_pii.reveal`'s Q-024 exemption. `ham.media.services.
  media_gallery_for(ctx, request_id)` always computes `MediaCounts`; it returns `items=None`
  unless `ctx.effective_roles` intersects `{DIR, AD, PAS, BRD}` (i.e. unless something *other*
  than Administrator alone grants `request_media.view`). The view still gates entry with
  `@requires_action("request_media.view")`, which both roles hold — the masking decision
  happens only once you're already inside.
- **Media re-encoding strips EXIF/GPS "for free"**: Pillow's `Image.save(..., format="JPEG")`
  does not copy source EXIF into the output unless the caller explicitly passes `exif=...`.
  Never pass that kwarg in `ham.media.processing.process_photo` — the re-encode itself is the
  metadata-stripping step, not a separate "scrub" pass that could be forgotten or miss a field.
  Proved this in a test with `piexif` (new dev-only dependency) building a real JPEG with GPS
  IFD tags, not just asserting "doesn't crash".
- **Video processing needs a real "ffmpeg isn't installed" degrade path, tested for real.**
  `ham.media.processing.ffmpeg_available()` (`shutil.which`) gates every video call;
  `ProcessingUnavailable` (distinct from `ProcessingError`, which is "processed but failed a
  check" — too_long/too_large/unsupported/corrupt) is caught by `ham.media.jobs.process_item`
  and marks the item `failure_code="processing_unavailable"`, **and still deletes the
  original** — never leave an unprocessed original sitting in `quarantine/` "for later," Q-120
  is "never serve/keep the original" unconditionally. `apt-get install ffmpeg` failed in this
  sandbox (upstream mirror 404s on several `noble-updates` packages) — don't assume it'll
  succeed; write the video-path tests to `pytest.mark.skipif(not ffmpeg_available())` for the
  real-encode assertions and a separate `unittest.mock.patch("...ffmpeg_available", ...)` test
  for the degrade path itself, so the suite is still meaningful with or without the binary.
- **Image/video derivative technical settings (long edge, thumbnail size, JPEG quality, H.264/
  720p) live as plain module constants in `ham/media/processing.py`, explicitly NOT in
  `ham.rules`** — intake.md §9 calls these out as "technical settings ... not business rules".
  Only the 2-minute video-length cap is a real rule
  (`RULES.media.REQUESTER_MEDIA_MAX_VIDEO_DURATION`), passed into `process_video` by the
  caller rather than imported inside `processing.py`, so that module stays pure/no-Django.
- **Retention sweep is written against the general `ham.rules.media_retention_period(kind,
  closing_status)` helper, not hard-coded to the statuses step 2 can actually reach.**
  `ham.media.jobs.retention_sweep` (a `ham.jobs.periodic_job`, daily 03:00 UTC) filters
  `AssistanceRequest.status__in=(CANCELLED, REJECTED)` today (step 2 has no COMPLETED yet) —
  when step 3 adds COMPLETED, add it to that tuple; the rule lookup itself needs no change.
- **Added three new rules mid-slice** (`media.MEDIA_UPLOAD_INTENT_LIFETIME`/
  `PRESIGNED_UPLOAD_URL_LIFETIME`/`PRESIGNED_VIEW_URL_LIFETIME`) that intake.md §9's plan-body
  rules table already named as engineering values but S2.1 hadn't added to `ham/rules/v1.py`
  yet — followed the full protocol (bump `RULES_VERSION` to `2026.09.28-5`, `docs/
  rules-changelog.md` entry, new `PINNED_HASHES` line, `tests/rules/test_rules_values.py`'s
  independent `EXPECTED` oracle, a new invariant). Gotcha: `ham/rules/v1.py`'s own source-format
  test (`SOURCE_RE`) only accepts `PRD §N` / `Q-NNN` / `foundation.md §N` in a rule's
  `sources=` tuple — `"intake.md §9"` fails that regex; put the architecture-plan citation in
  `note=` prose instead, `sources=` gets the PRD section(s) only.
- **`ham/requests/models.py` and `ham/requests/migrations/0001_initial.py` are a deliberate,
  clearly-flagged PLACEHOLDER** (S2.2 owns the real `AssistanceRequest`, running in a parallel
  worktree not yet merged into this one) — minimal `id`/`status`/`closed_at` only, enough for
  the `"requests.AssistanceRequest"` FK string and the retention sweep. Also added a
  placeholder `ham.requests.services.is_request_open(request_id)` (media needs to refuse
  uploads on a closed/decided request; layering forbids `ham.requests` importing `ham.media`,
  so this had to go the other way — `ham.media` importing `ham.requests.services`, which the
  `ham.media` -> `ham.requests` layers direction already allows). Both files' docstrings spell
  out exactly what the orchestrator should do at merge time (drop the placeholder model/
  migration, keep S2.2's; re-point `ham/media/migrations/0001_initial.py`'s dependency at
  whichever migration in S2.2's history actually creates the real table; reconcile
  `is_request_open` with S2.2's equivalent, which will likely be status-based rather than
  bare-`closed_at`-based once step 3's states exist).
- **Cross-module reaction without a forbidden import**: `ham.media` reacts to `ham.requests`'
  `RequestCancelled` outbox event (closes any still-open media batch) via its own outbox
  subscriber (`ham.media.subscribers.handle_media_event`, registered `"media"` from
  `MediaConfig.ready()`) — exactly the established `IntegrationsConfig.ready()` pattern, just
  used for a same-repo domain-to-domain reaction instead of a third-party integration. This is
  how a *lower* layer's event reaches a module that layering says may import it (`media` is
  above `requests`) without the *requests* side ever importing `ham.media` back.
- **A background job (`ham.jobs.job`/`periodic_job`) that's only ever imported by the module
  defining it never actually registers with Procrastinate** — `jobs.defer("name", ...)` then
  raises `KeyError` at call time, not at import time, which makes the failure show up in an
  unrelated-looking test. Fix: import the module (even just `from . import jobs  # noqa: F401`)
  from the owning app's `AppConfig.ready()`, mirroring how `MediaConfig` now imports both
  `.jobs` (task registration) and `.subscribers` (outbox registration) there.
## S2.5 additions: notifications module (Notification, inapp subscriber, attention registry)
- **`ham.notifications.inapp.register_inapp`/`handle_inapp_event`** is an exact mirror of
  `ham.integrations.email.notifications.register_notification`/`handle_email_event` (list of
  builders per event type, builder returns `None`/one/`list[InAppNotice]`), but it is
  registered as the `"inapp"` outbox subscriber from **`NotificationsConfig.ready()` itself**,
  not from `IntegrationsConfig` — intake.md §2 calls this "internal, not a third party": since
  `ham.notifications` sits at the bottom of the domain-module stack (just above
  `ham.identity`), it can own its own outbox integration without triggering the "domain
  modules never import `ham.integrations` directly" contract at all (no `ignore_imports` entry
  needed, unlike every other domain module's `.notifications.py`).
- **`Notification.title` gets its own PII guard** (`ham.notifications.validation.check_title`,
  reusing `ham.platform.logging.EMAIL_RE`/`PHONE_RE`), called from `handle_inapp_event` before
  every `Notification.objects.create(...)` — mirrors `ham.outbox.validation.validate_payload`
  but is a separate, smaller check (title is one free-text field, not an arbitrary payload
  dict) rather than reusing the outbox validator directly.
- **"Needs response" has no table.** `ham.notifications.attention` is a second, independent
  registry (`register_attention_provider(fn)`, `fn(ctx) -> list[AttentionItem]`,
  `attention_items_for(ctx)` concatenates every provider) — completely separate from
  `register_inapp`. A provider returns already-aggregated, PII-free rows (e.g. "Waiting for a
  decision (3)"); nothing is stored, so resolving the underlying thing (e.g. a request leaving
  Awaiting Approval) clears the card everywhere for free. `AttentionItem.muted` (Director/AD
  see pastors'/Board's rows, de-emphasized, **not hidden**, and **excluded from the badge
  count** — intake.md §6) is a per-item flag the *provider* sets based on the actor's role, not
  something the registry computes; `needs_response_count(ctx)` sums `count` for non-muted items
  only, `needs_response_for(ctx)` returns everything (view renders muted differently).
- **Read vs. acknowledge, two very different authorization shapes for the same table.** Marking
  an Update read is scoped by plain ownership-filter-in-the-query
  (`Notification.objects.filter(pk=..., recipient_user_id=ctx.user_id)`), gated only by the
  route's `shell.use`, and is **not** a `@command`/not audited — same rationale as "page views
  ... are not audited" (intake.md §9.8): it changes nothing another party can observe.
  Acknowledging (`notification.acknowledge`, `Scope.SELF`, `blocked_while_impersonating=True`,
  already declared in the matrix by S2.0) *is* a `@command`, because it is what makes the
  urgent banner (§10/§35) disappear. Wiring pattern for a `Scope.SELF` action keyed by a
  specific row (not "always yourself" like `me.update`'s `_resource_self` returning `ctx`
  outright): `resource_from` loads the row and returns `SimpleNamespace(user_id=row.
  recipient_user_id)` if found, or `None` if not — `Scope._self_scope_ok` treats a `None`
  resource as "nothing to check yet, let the service body raise" (same escape hatch role-grant
  finer-grained checks use), so a bad id gets a plain `ValueError` from inside the service
  rather than a scope denial that would otherwise require a second DB read just to build the
  `Decision`.
- **`identity.services.notification_recipients(roles: Iterable[str]) ->
  list[tuple[UUID, str, bool]]`** (user_id, email, notify_email) is the one function this slice
  added to `ham.identity` (intake-contracts.md §7's "only ham.identity reads auth tables"
  rule) — filters `role_assignments__role__in=role_set, revoked_at__isnull=True,
  is_active=True, disabled_at__isnull=True`, de-dupes with a manual `seen: set[UUID]` (not
  `.distinct()`) because a JOIN against `role_assignments__role__in={A, B}` returns one row per
  matching assignment, so a user holding *both* roles in the set would otherwise appear twice;
  `user.profile.notify_email` is wrapped in `except ObjectDoesNotExist: notify_email = True`
  since `SharedIdentityProfile` is only reliably created via `get_or_create` at bootstrap/
  invite time, not guaranteed for every row a test or edge case might create.
- **New `tests/notifications/` package** (`__init__.py`, `test_inapp.py`, `test_attention.py`,
  `test_services.py`) — first backend slice to add a whole new top-level `tests/<app>/`
  directory outside the ones S1/S2.0 already scaffolded; nothing extra was needed (pytest
  picks it up via `testpaths = ["tests", "ham"]`, no per-directory conftest required beyond the
  shared `tests/conftest.py`'s `make_user`/`_reset_clock`).
- **Retention for `Notification` rows is an explicit, intentional gap** (task brief: "note the
  gap; don't invent a value") — intake.md's D4/Q-116 retention decision covers
  `AssistanceRequest`/`Requester`/`Property`, not this table; no `ham.rules` constant exists or
  was added for it. Don't backfill one without an owner decision.

## Step-2 "known loose ends" fixup (2026-09-28, wave-3 close-out)
- **Cross-app lookup registration must be wired from the *importing* side, not the *owned*
  side, when the layers contract only allows one direction.** The step-2 handoff doc said
  `RequestsConfig.ready()` should register `ham.requester_portal`'s three portal lookups
  (`register_request_facts_lookup` etc.) — that's backwards: `ham.requests` sits *below*
  `ham.requester_portal` in the `web -> requester_portal -> media -> requests -> ...` layers
  contract, so `ham.requests` may never import `ham.requester_portal.services` to call
  `register_*` on it (import-linter flags it even from inside `AppConfig.ready()`, and even
  from a `TYPE_CHECKING` block — it's a static-analysis check, not a runtime one). The
  registrations belong in **`RequesterPortalConfig.ready()`** instead, which legally imports
  `ham.requests.queries` (downward) and wraps its plain-value return types (this slice added
  `ham.requests.queries.request_facts_for_portal`/`.request_contact_for_portal`/
  `.request_ids_for_portal_email`, all returning plain str/UUID/a local `PortalRequestFacts`
  dataclass, never a type from the app above) into the portal's own `RequestLinkFacts`. If a
  handoff doc's literal instruction on *which app's `ready()`* conflicts with the layers
  direction, trust the layers contract (`lint-imports`) over the doc's wording.
- **Two independently-built parallel slices reusing "the same" fixed vocabulary/wording will
  drift unless one side imports the other's constants.** S2.2 (`ham.requests.models`/
  `.certifications`, what's actually persisted/checked) and S2.3
  (`ham.requester_portal.choices`/`.attestation`, the public form's own vocabulary) each
  independently invented different string codes for need category, property type, and the
  certification statements (e.g. portal `"roof_or_ceiling"` vs. persisted `"roof"`; portal's
  2-tick `owner_authority`/`responsibility` vs. persisted 3-code
  `true_to_knowledge`/`owner_permission`/`hoa_responsibility`). Passing the portal's codes
  straight into `SubmittedRequestPayload` wouldn't raise (Django's `choices=` isn't enforced at
  `.create()`), it would just quietly corrupt the stored value or make
  `certifications.statements_satisfy_relationship` refuse every submission. Fixed by adding
  translation tables (`_NEED_CATEGORY_TRANSLATION`/`_PROPERTY_TYPE_TRANSLATION`) and a direct
  `certifications.required_statements(relationship)` call in
  `ham.requester_portal.services._payload_from_cleaned` — the one place that already imports
  both vocabularies to cross the seam — rather than touching either module's own (already
  green-tested) vocabulary. When two slices each own "the same" fixed choice list, check their
  actual string values match before wiring the seam between them; don't assume matching English
  labels means matching codes.
- **A plain orchestration function that calls two-plus `@command`s in one transaction (not
  itself a `@command`) must still hand-write any audit event the individual commands don't
  cover.** `ham.requester_portal.services.submit_and_issue_link` calls `submit_request`
  (audits `request.submitted`) then `issue_link` (a plain function, "does not itself audit or
  email; the caller does" per its own docstring) — nothing wrote `requester_link.issued` even
  though the label existed in `ham/audit/labels.py`. Fixed with a hand-written
  `ham.audit.services.record(...)` call inside the same `transaction.atomic()` block, same
  pattern `complete_intake_checks` already uses for its second `request.duplicates_flagged`
  event. When auditing a multi-command orchestration, check every label the module docstring/
  contracts doc promises actually gets written somewhere, not just that each individual
  `@command` fires its own.
- **A "the initial container open isn't audited" design flag from a previous slice is usually
  correct, not a bug** — confirmed for `ham.media._get_or_open_initial_batch`: opening a
  requester's own batch #1 is a side effect of their own (already-unaudited, per that module's
  own docstring) `reserve_uploads` call, not a distinct actor decision, unlike `reopen_batch`'s
  audited `request_media.batch_opened` (a deliberate staff decision on an already-closed
  request). Documented the reasoning directly in `_get_or_open_initial_batch`'s docstring and
  added a regression test (`test_opening_the_initial_batch_is_not_audited`) instead of changing
  behaviour — CLAUDE.md priority 3 doesn't require auditing every DB write, only consequential
  *actions* by an actor.
- **The one flaky/real pytest warning left over from a previous wave** ("Error when trying to
  teardown test databases: ... database is being accessed by other users") came from
  `tests/e2e/test_smoke.py`'s `live_server` (pytest-django, session-scoped): a real
  `ThreadedWSGIServer` handling Playwright's HTTP/1.1 keep-alive traffic in per-request worker
  threads, each with its own Postgres backend session, with no hard guarantee every one of
  those sessions is closed by the time pytest-django's own session-scoped `django_db_setup`
  fixture tears down and runs `DROP DATABASE`. Root-caused by reproducing it standalone
  (`pytest tests/e2e/test_smoke.py -p no:randomly`, ~100s, much faster to iterate on than the
  full ~150s suite) and bisecting with `--deselect`; ruled out `CONN_MAX_AGE` (already tried
  forcing it to 0 in `config/settings/test.py` — didn't help, so don't re-try that) and a
  `LiveServerThread.terminate()`-doesn't-`.join()` theory (Django's `terminate()` already calls
  `self.join()` — checked the installed Django's source directly rather than assuming). Fixed
  defensively rather than by chasing the exact leaking thread: a `tests/conftest.py` session-
  scoped `autouse` fixture (`_terminate_stray_backends_before_db_teardown`) that requests
  `django_db_setup`/`django_db_blocker` as dependencies (so pytest's LIFO teardown order runs
  it *right before* `django_db_setup`'s own teardown) and runs `pg_terminate_backend` on every
  *other* backend still connected to `current_database()`. No-op on a clean run; removes the
  warning unconditionally regardless of which test (if any) is the actual culprit next time.
- **When two `Bash` tool calls against the same Postgres-backed pytest suite overlap (e.g. a
  timed-out call auto-moved to background, then another blocking call issued before checking
  the first one's result), you get spurious "database is being accessed by other users"
  noise that has nothing to do with the code under test.** Burned real time here chasing a
  ghost before noticing two concurrent `pytest -q` processes via `ps -ef`. Before treating a
  DB-teardown warning as reproducible, confirm there is exactly one pytest process running
  (`pgrep -af pytest`) — and don't fire off a second full-suite run without first reading the
  previous one's completion notification/output.

## Fix E (step-2 fix round: security re-check + PRD re-check, parallel with other fix rounds)
- **A `django_db(transaction=True)` test that reuses a helper (`run_due_jobs_now()`) another
  test in the *same file* also calls can break that other test even though both pass in
  isolation** — a real `TransactionTestCase`-style commit+truncate cycle doesn't compose
  cleanly with Procrastinate's job queue the way plain `pytest.mark.django_db` (one wrapped,
  rolled-back transaction) does; a later, unrelated test's `run_due_jobs_now()` can then hit
  `AssistanceRequest.DoesNotExist` from a job that shouldn't even exist anymore. The PoC this
  slice turned into a real test (`test_poc_cross_draft.py`) used `transaction=True`, but
  didn't actually need it (two `django.test.Client()` instances share one connection-backed
  test transaction just fine) — dropped it once bisection (`pytest tests/web/ -q` reproduces
  deterministically, no `pytest-randomly` in this project, so it's file-collection-order, not
  random; add/remove files with `--deselect`/run one at a time to bisect) pinned the exact
  file. **Before trusting a "looks environmental" full-suite failure is pre-existing, run
  `pytest <the one file that reproduces it> -q` alone, then `-k` bisect which of *your own new
  test files* is the culprit** — don't assume it's flaky prior-slice infrastructure just
  because the traceback shows a generic-looking `TransactionManagementError`/`DoesNotExist`
  deep in Django internals.
- **`verify_code`'s challenge-selection query needs `draft_id`/`request_id` in its `.filter()`
  the moment the caller has one, not just in a separate rate-limit counter** — N3: it used to
  select "the most recent, unconsumed challenge for this `email_key`+`purpose`" with no
  `draft_id`/`request_id` filter at all (those were only ever used by
  `_recent_failed_attempts`, a sibling function). An attacker who types a victim's real email
  into their *own* draft (cooldown blocks a second challenge from being created, since it's
  keyed on email+purpose) then has their wrong-code guesses land on the *victim's* actual
  challenge row, burning the victim's real attempt budget. Fix: `verify_code` now requires
  `draft_id is not None or request_id is not None` up front (`no_challenge` otherwise) and
  filters the `select_for_update()` queryset by whichever one it got, in addition to
  `email_key`/`purpose`/`consumed_at__isnull=True` — every existing test that called
  `verification.verify_code(...)` directly (not through the view, which already passed
  `draft_id`/`request_id`) needed a `draft_id=` kwarg added or it now gets `no_challenge`
  instead of exercising the wrong/expired/locked paths it meant to.
- **A `_after_verified`-style dispatcher that reads "which resource does this apply to" from
  session state must re-derive it from the thing that was actually verified, not the
  session** — same H1 shape as an earlier slice's draft_id fix, but for link regeneration:
  `_after_verified`'s link-regeneration branch used `_pending_link_regen_request_id(request)`
  (a session key) to build the `RequesterContext` it then regenerated a link for, ignoring
  `challenge.request_id` entirely. With the `verify_code` fix above already scoping challenge
  *selection* by the session's `request_id`, this exact bypass is unreachable through the HTTP
  flow (querying by the wrong id just returns `no_challenge`) — but `_after_verified` itself
  still needed its own `challenge.request_id != request_id` check as defense in depth (L8),
  provable by calling `_after_verified` directly with a hand-built mismatched challenge
  (bypassing `verify_code` entirely) rather than trying to reach it through two real HTTP
  requests.
- **A verification action that issues something (a link, a code) needs its own append-only
  history row and audit `context`, mirroring whatever the *original* verification already
  does — check both ends independently, an existing "record X" helper for one path doesn't
  imply the sibling path has one.** L8/M4: `submit_request` already wrote a
  `RequestContactVerification(purpose="intake", ...)` row and `complete_intake_checks`/etc.
  set audit context, but `regenerate_link_for_own_request` (link regeneration, "the same kind
  of event, a different trigger") wrote neither. New `ham.requests.services.
  record_link_regeneration_verification(*, request_id, method, verified_value, challenge_id)`
  (plain function, not `@command` — the actor-visible action is still just
  `requester_link.regenerated`) is the one write path both `ham.web.views_requester` call
  sites (`_after_verified`'s email-code branch, `request_help_new_link`'s email-link branch)
  now feed through, with `verification_method` threaded as a new required kwarg on
  `regenerate_link_for_own_request` itself (a signature change — every direct caller in tests
  needed updating, not just the two view call sites). `CommandResult(context=..., after=...)`
  both getting the same `{"verification_method":..., "challenge_id":...}` dict is intentional
  (M4 wants it on the audit event; `ham.audit.services.record` still adds its own `link_id`
  from `ctx.link_id` on top for a requester actor, on top of whatever `context` already has —
  don't assert an exact `context` dict in a test without accounting for that).
- **`is_masked_view(ctx)` is the one gate multiple independent surfaces (list marker, detail
  contact block + reveal button + free-text fields, media gallery) must all call, and each of
  those call sites needs the SAME impersonation-aware fix, not just the function itself** —
  N5/Q-151 extended `is_masked_view` (already Q-124's "Administrator, no leadership role also
  granting access") with `ctx.is_impersonating and user_holds_global_role(ctx.real_user_id,
  ADMINISTRATOR)` (same helper/reasoning as the earlier `reveal_requester_pii` L7 fix — see
  that fix's own memory entry). But `is_masked_view` being correct doesn't automatically fix
  every caller: `ham.requests.queries.list_requests`' `has_possible_duplicate` marker (M2) and
  `RequestDetailRow.contact_note` (NEW-1) each had their own separate, un-gated field
  assignment that needed touching individually — grep every place a P/C/sensitive field or
  marker is assigned in a query function, don't assume "the shared helper is fixed" is
  sufficient. New `ham.requests.queries.can_view_history(ctx)` (`not is_masked_view(ctx) and
  authorize(ctx, "request.history.view", None).allowed`) replaces a bare `authorize()` call in
  `ham.web.views_requests._build_detail_context` that had the identical impersonation gap for
  the History section/duplicate panel — a raw `authorize()` call is *never* enough on its own
  when the matrix rule's roles include one that changes meaning under impersonation.
- **A route that streams bytes through the app must scope the *lookup*, not just the media
  item, through the same query every list/detail screen already uses** — N1:
  `ham.web.views_requests._serve_media` called `get_ready_item(request_id=..., media_id=...)`
  directly (scoped only to "does this item exist under this request", no status/role check at
  all), letting a Pastor fetch photo bytes for a request stuck in `NEEDS_PHONE_CHECK` (Q-025:
  Director/AD only) by knowing/guessing the request+media ids. Fixed by calling `ham.requests.
  queries.get_request_by_id(ctx, request_id)` first (404 if `None`, same scoping `list_requests`
  uses) before ever touching storage. Separately, `read_media_bytes` (`ham.media.services`)
  loaded the *whole* object into a `bytes` before handing it to `HttpResponse` — added
  `ObjectStore.open_object(key) -> BinaryIO` to the protocol (local: `Path.open("rb")`; S3:
  return the `boto3` `StreamingBody` from `get_object` directly, no read() upfront) and a new
  `ham.media.services.open_media_stream` the view wraps in `django.http.FileResponse` instead
  of `HttpResponse(data, ...)`.
- **A background job's storage-deletion side effect belongs behind `transaction.on_commit`
  when it runs from inside a `@command`'s own `transaction.atomic()` block, and its hook
  registration should raise loudly if missing, not silently no-op** — N6:
  `purge_all_for_request` (`ham.media.services`, the spam-purge's registered `ham.requests.
  services._media_purge_hook`) used to call `store.delete(key)` synchronously mid-transaction;
  a later failure in the same `purge_expired_request` transaction (e.g. the request-row delete
  or the `@command` wrapper's own audit/outbox write) would then roll the DB back with the
  bytes already gone from storage, unrecoverably. Wrapped each `store.delete(key)` in
  `transaction.on_commit(functools.partial(store.delete, key))`; testing this requires
  pytest-django's `django_capture_on_commit_callbacks(execute=True)` context manager around
  the call under test (`on_commit` callbacks never fire in a normal rolled-back-at-teardown
  `django_db` test otherwise) — existing tests asserting storage was actually deleted needed
  wrapping, not just new ones. Also changed `if _media_purge_hook is not None: hook(...)` to
  raise `RuntimeError` when the hook is `None` — a missing registration (a startup-wiring bug,
  `MediaConfig.ready()` always registers it) used to mean "spam purge silently never deletes
  storage", which is worse than a loud failure.
- **`ham.notifications.services.mark_read` needed a read-only sibling
  (`get_owned_notification`) so a caller can look up "is this mine, what's its subject" without
  the side effect of marking it read** — N7: `ham.web.views.notification_open` now branches on
  `ctx.is_impersonating` to call `get_owned_notification` instead of `mark_read` while
  impersonating, so browsing someone else's inbox to open a linked request doesn't silently
  change what they see as unread next time they sign in themselves. Same view also wraps the
  final `redirect(url_name, request_id=...)` in `try/except NoReverseMatch: redirect("web:
  inbox")` (defensive — no known way to trigger it today, but a future `subject_type` ->
  wrong-shaped URL name mapping shouldn't 500) and whitelists `request_detail`'s `back_tab`
  query param against a fixed `_KNOWN_LIST_TABS` set before putting it in the "Back to
  Requests" link's query string (Django's auto-escaping already blocked attribute breakout,
  but the destination `requests_list` view's own tab validation was the only thing stopping an
  unrecognized value from round-tripping into a rendered URL — defense in depth, not a fix for
  an actual exploit).
- **A queryset `.update()` that's the one deliberate escape hatch around a model's append-only
  `save()` guard should be a *named manager method*, not a bare call at the service-layer call
  site** — N4: `RequestContactVerification.objects.filter(request=request).update(value_key=
  "")` (the 7-year retention purge's hashed-value erasure, L8) became `RequestContactVerification
  Manager.erase_value_keys_for_retention(request)` (a custom `models.Manager` subclass,
  `objects = RequestContactVerificationManager()` — Django's own style-guide linter, `ruff`'s
  `DJ012`, wants the manager assignment *after* every field, before `Meta`, not before the
  first field). Lets a test prove "only the purge sweep does this" by grepping source for the
  method name and for the raw `.update(value_key=` pattern separately (the grep-style check
  the wave brief asked for) — a hand-written oracle over `ham/**/*.py`, no new dependency.
- **A required-field validation added to a shared form validator needs every existing test
  fixture that posts that field re-checked, including ones nested in a different test file's
  own local wizard-fill helper** — M5/Q-099: `ham.requester_portal.forms.validate_intake_
  payload`'s `availability` list now rejects empty with "Choose at least one time (Any time
  works counts)" (it was previously silently optional — `bad_availability` only ever fired for
  a *wrong* value, not a *missing* one). `tests/web/test_requester_portal_screens.py::
  _fill_wizard`'s own `no_email=True` branch built a hand-trimmed POST body that dropped
  `availability` entirely (along with `contact_preference`, which is fine — it's auto-filled
  for the no-email path) — grep every test fixture/dict literal with `"availability":` (or
  building one without it) across the whole `tests/` tree, not just the form-validator's own
  test file, before assuming a new required-field check is safe to land.
- **A relationship-scoped fixed vocabulary (certification statement codes) must be filtered to
  "what's actually offered for this relationship" at the point of storage, not just checked as
  a subset** — cert-codes PRD fix: `statements_satisfied(relationship, accepted)` only ever
  checked `required.issubset(accepted)` (accepted may be a *superset*), and the old `cleaned
  ["attested_statements"] = sorted(accepted)` stored the raw POSTed set verbatim, including any
  stray/forged code (even a *different* relationship's own authority-tick code, since the
  authority code differs by relationship — `_AUTHORITY_BY_RELATIONSHIP`). Fixed with `accepted
  & {code.value for code in required_statements(relationship)}` at the point `cleaned[...]` is
  assigned — intersect, don't just validate a subset relationship and store the untouched
  input.
- **A field the admin settings view/model already had, with a stale "the template doesn't
  render it yet" comment, just needed the template control added** — N15: `ChurchProfile.state`/
  `views_admin_settings.admin_church_settings` already existed (an earlier slice's Q-147 work);
  only `admin_church_settings.html` was missing a `<select>` (2-letter `US_STATE_CODES`,
  `ham.platform.church`, sorted for a stable option order) and the view's stale "doesn't render
  yet" comment needed correcting once it did. `manage.py seed_dev` (the persona seeder,
  `ham.identity.management.commands.seed_dev`) now also sets `ChurchProfile.get_solo().state =
  "FL"` inside its existing transaction, for local dev/Playwright runs to start from a
  prefilled state instead of "not set" — but never write the literal deployed church name in a
  comment/docstring anywhere in `ham/` (even explaining *why* FL), `tests/web/test_no_hardcoded
  _church_or_colors.py::test_no_literal_church_name_in_python_source` greps all of `ham/` (not
  just `tests/`) for `FORBIDDEN_CHURCH_STRINGS`.

## FIX-F2 (step-2 intake, requester flows/M4/M6/M7/M8 re-check round)
- **"Fixed but not fixed" review findings (an earlier pass claimed M4/M6/M7/M8 fixed without
  changing them) need an independently-written failing-before/passing-after test per item, not
  just a code diff** — every item in this round got a new test file (`tests/**/test_fix_f2_*.py`)
  that fails on the pre-fix code and passes after, named in the handback, per the parent task's
  explicit instruction. Don't trust a prior "Fixed" claim in a review doc without re-deriving
  the check yourself.
- **A "reason code" and a "free-text justification" collected on the same form question are two
  separate fields, always** — the recurring bug shape (M4/N-M1: `urgency_reason` was composed
  into `urgency_justification` via `f"{label}. {justification}"` at *view* level, re-run on
  every re-save, silently duplicating/mutating the requester's own words) is the same class of
  mistake as the earlier hazard-note-in-parens bug: never fold a fixed-vocabulary code into a
  free-text field's *stored* value. Compose "Label. Text" only at *display* time
  (`ham.requests.presentation.urgency_line`, new — same shape as `hazard_labels`), never at
  write time. When one such field is optional depending on the other's chosen value (here:
  justification required only for the "Something else" reason), the DB `CheckConstraint` mirror
  of the Python validation needs the same conditional shape
  (`Q(reason="something_else") & ~Q(justification="") | ~Q(reason="something_else")`), not a
  flat "always required when urgent" — a flat constraint silently regresses the "optional for
  every other reason" requirement the very next migration.
- **Adding a new required field to a `SubmittedRequestPayload`/`AssistanceRequest.objects.
  create()` call touches every test factory that builds an urgent payload, transitively** —
  `tests/requests/conftest.py::make_payload` is the one shared factory nearly every urgent-
  request test routes through (directly or via a per-file `_submit`/`_submitted`/`_make_request`
  wrapper); adding `overrides.setdefault("urgency_reason", "something_else")` there when
  `urgent_requested` is truthy fixed every call site in one place instead of touching a dozen
  test files. `ham/requests/management/commands/seed_dev_requests.py`'s own `_create()` (which
  calls `AssistanceRequest.objects.create()` directly, bypassing `SubmittedRequestPayload`
  entirely) needed the same new kwarg threaded through by hand — grep for *every* direct
  `AssistanceRequest.objects.create(...)` call site, not just the one this slice's own service
  module uses, before trusting a new required-field DB constraint is safe to land.
- **A "same wording for every purpose" bug (M6) is fixed by threading `purpose` into the shared
  copy-building function itself, not by branching at every call site** —
  `verification._code_email_text(*, code, link_url, church, purpose)` now branches once,
  internally, on `purpose == PURPOSE_INTAKE` vs. link-regeneration; the one call site
  (`_request`) just passes `purpose` through. Same pattern in the template
  (`r8_verify.html`'s `{% if purpose == "intake" %}`) and in `confirm_link.html`'s `kind`.
- **"No enumeration, identical response" (H2) does not mean "the two flows must go through the
  same code path"** — M7's fix deliberately gives R11b ("check on your request") its own,
  completely separate issue-link+email function (`ham.requester_portal.services.
  _issue_and_notify_found_link` / `notifications.send_found_request_email`, own
  `requester_link.found` audit action, own E4 wording), never touching the
  `requester_link.regenerate`/`RequesterAccessLinkIssued`/E3 path R11a still uses. The
  HTTP-visible response (`ChallengeRequestResult("sent")`, no branching) stays identical either
  way; only the internal code path differs. When an earlier slice's docstring flags "two flows
  share one event with nothing to tell them apart, coordinator TODO" — that's a real
  invitation to *split* them, not evidence the sharing was intentional.
- **A cross-app "facts" lookup dataclass (`ham.requester_portal.services.RequestLinkFacts`,
  registered by `ham.requests` at `AppConfig.ready()`, per intake.md §2's layering) is the right
  place to add a new plain-value field (here: `display_number`) that a lower-layer app's data
  needs to surface in an upper-layer app's UI/email — not a direct model import.** Adding
  `RequestLinkFacts.display_number`/`PortalRequestFacts.display_number` (computed as
  `f"HAM #{reference_number:03d}"`, matching `AssistanceRequest.display_number`'s own property
  exactly, never re-derived differently) let `send_found_request_email` build its subject
  without `ham.requester_portal.notifications` importing `AssistanceRequest` for this call path
  at all (it already does so elsewhere, legally, for the *outbox-driven* builders — this one
  path is different because `find_my_request`'s fake-lookup test fixtures, by design, never
  create a real `AssistanceRequest` row).
- **This exact lookup-wiring function is duplicated three times on purpose (documented in
  `tests/conftest.py::real_portal_lookups`'s own docstring) and all three need the same edit
  together**: `ham.requester_portal.apps.RequesterPortalConfig.ready()`'s `_facts_lookup`
  closure, and `tests/conftest.py::real_portal_lookups`'s own copy of the identical closure (its
  docstring explains *why* it's a second copy rather than calling `ready()` again). Forgetting
  the test-conftest copy when adding a new `RequestLinkFacts` field produces a subtle failure:
  tests using the *fake* per-file lookup fixtures (e.g. `tests/requester_portal/
  test_regenerate_and_find.py`'s own `_lookups`) still worked, but tests using the *shared*
  `real_portal_lookups` fixture silently got an empty value for the new field (no error, just a
  blank subject line) until the second copy was updated too.
- **M8 "already received" (confirming a code/link after the draft already became a request on
  another device) needs a `reveal: bool` gate, not a uniform response** — whether to show the
  HAM # and a direct link to the secure page depends on whether *this exact browser* just
  proved something (a code that matched inside its own session, or a link-consume POST that
  itself just succeeded) vs. merely replaying an already-dead code/link with no proof at all.
  New shared context builder `ham.web.views_requester._already_received_context(request_id, *,
  reveal)` and shared partial template `web/requester/_already_received.html` (included from
  both `r8_verify.html` and `confirm_link.html`) keep the two "reveal" vs. "neutral" renderings
  in exactly one place each. Distinguishing "this draft already became a request" from "this
  draft id is simply unknown" needs a dedicated query
  (`ham.requester_portal.drafts.consumed_request_id`, `IntakeDraft.objects.filter(pk=...,
  consumed_at__isnull=False).first().request_id`) — `load_payload`'s existing `None` return
  means either one identically, by design (no enumeration), so it can't be reused for this.
  Finding "which draft an already-*used* link token belonged to" (to decide even whether to
  offer the neutral message) needs its own lookup too, without the usual `consumed_at__isnull=
  True` filter every other link-consuming query applies —
  `ham.requester_portal.verification.challenge_for_link_token` (docstring: "used only to
  detect... never to grant access on its own").
- **A background job deferred by `submit_request` (the duplicate-check `complete_intake_checks`
  job) that a test never drains with `run_due_jobs_now()` leaks into the *next* test's own
  `run_due_jobs_now()` call and blows it up with a confusing `TransactionManagementError`/
  `DoesNotExist` from a job that isn't even the failing test's own** — `pytest-django`'s
  per-test transaction rollback does not appear to clean up already-deferred Procrastinate job
  rows the same way it does ORM rows, at least not reliably enough to trust. Existing convention
  (`tests/web/test_requester_portal_screens.py::TestFullEmailFlow`'s own comment) is the fix:
  call `run_due_jobs_now()` once, explicitly, right after any `submit_request`/full-wizard-POST
  call that creates a real `AssistanceRequest`, even in a test that has nothing to do with that
  job's own effects — "drains the duplicate-check job so it doesn't leak into a later test's
  `run_due_jobs_now()` call" is worth writing as a one-line comment every time.
- **`hazard_labels`'s wrapper-note parse (`"codes (note)"`) is unambiguous with `str.partition`
  (first occurrence), not `str.rpartition` (last occurrence), once you notice hazard codes
  themselves never contain a parenthesis** — the codes prefix can only ever contain one kind of
  character run (`[a-z_,\s]`), so the *first* " (" in the whole string is always the wrapper's
  own opening paren, no matter how many further "(" / ")" pairs the requester's own note text
  contains after that. A bare `"none_known"` code is not itself a hazard for display purposes —
  filter it out of `hazard_labels`'s returned list entirely (not just relabel it) so the
  caller's pre-existing "no hazards" empty-state branch (shield icon, "None that they know of")
  renders for it automatically, rather than adding a second special case in every template that
  calls this function.

## FIX-G (step-2 intake, NH1/NM1 security re-check + UX minors)
- **"A session/cookie is proof of nothing" is a distinct bug shape from H1/N3's "the wrong
  challenge got selected" (Fix A) — both need fixing, and fixing one does not fix the other.**
  NH1: `_already_received_context`'s `reveal=True` branch used to fire whenever *this
  browser's session* merely still named an already-submitted draft id, even when the POST that
  reached that branch had just **failed** verification (`verify_code` returned
  `reason="no_challenge"`, i.e. no correct code was ever entered on this browser). Fixed by
  keying `reveal` strictly on "did THIS request just independently prove something" (a code
  that verified inside this exact POST, or a link-consume POST that itself just succeeded),
  never on session contents alone — the `no_challenge` branch in `ham.web.views_requester.
  request_help_verify` now hard-codes `reveal=False` and pops `_SESSION_VERIFY` (so a bare
  replay of the same failed POST doesn't keep re-checking a spent session). Even the
  legitimate `reveal=True` branches stopped decrypting and handing out a live secure-page
  token (`ham.requester_portal.services.current_secure_page_path`, deleted outright) — "you
  proved something" still isn't the same authorization level as "the audited link-issuance
  path decided to hand you a token"; the reveal template now says "open the link in your
  email" instead of linking anywhere.
- **An unauthenticated "prove you own this address" POST must never itself be the thing that
  mutates state (issues a live credential, revokes an old one) — it may only ever *trigger a
  send* of something that, when clicked, goes through the exact same audited re-verification
  path a "my link already expired" flow already uses.** NM1/PRD NEW-2:
  `ham.requester_portal.services.find_my_request` (R11b "Check on your request") used to call
  `issue_link`+email directly, synchronously, from the POST handler itself — no click-through,
  no `verification_method` recorded anywhere. Fixed by giving R11b its own challenge purpose,
  `RequesterVerificationChallenge.PURPOSE_FIND` (new, alongside `PURPOSE_INTAKE`/
  `PURPOSE_LINK_REGENERATION` — CharField `choices=` metadata only, no real migration
  behavior, but `makemigrations` still wants a state migration for it), and a new
  `ham.requester_portal.verification.request_find_verification` that creates that challenge
  and emails only a link (an E4-specific text builder, no code — R11b's UI never had a code
  field) pointing at the **same URL** link-regeneration's own click-through page already uses
  (`/request-help/new-link/<token>`, reusing `_CONFIRM_PATH_TEMPLATES`) — since
  `ham.web.views_requester.request_help_new_link`'s POST handler never branches on
  `challenge.purpose` (only checks `request_id is not None`), no view code needed touching at
  all: it already calls `regenerate_link_for_own_request` (issues, revokes the old one,
  records `verification_method="email_link"` + a `RequestContactVerification` row) for
  whichever purpose's challenge got consumed. The old `_issue_and_notify_found_link`/
  `send_found_request_email` (notifications.py) are gone entirely — nothing issues a link
  from the `find_my_request` call path itself anymore, only `request_find_verification`'s own
  independent rate limits (new rule `RULES.intake.FIND_REQUEST_EMAILS_PER_ADDRESS_PER_DAY`,
  Q-121; the "1 per request" limit reuses the existing `REQUESTER_CODE_RESEND_COOLDOWN` rather
  than inventing a new rule for it — reuse an existing named rule before adding a new one when
  the numeric value and its rationale really are the same).
- **A per-address abuse counter that's meant to be independent of a *different* flow sharing
  the same underlying model needs its own `purpose` value, not a shared one filtered some
  other way** — `request_find_verification`'s cooldown/daily-cap queries are plain
  `purpose=PURPOSE_FIND` filters, so R11a's own link-regeneration resends (`purpose=
  PURPOSE_LINK_REGENERATION`) never eat into R11b's budget or vice versa, for free, the same
  H2 "split the counters by purpose" pattern Fix A already established.
- **A rate-limit cooldown/hourly-cap keyed only on the untrusted-input side of a two-sided
  relationship (here: `email_key` alone) is abusable as a denial-of-service against the
  *other* side (here: `draft_id`), even when neither side alone is secret** — L(low):
  `ham.requester_portal.verification._request`'s cooldown and
  `REQUESTER_CODE_EMAILS_PER_ADDRESS_PER_HOUR` queries now additionally filter by `draft_id`
  when one is given (i.e. for `purpose=PURPOSE_INTAKE` only — link regeneration/find have no
  browser-created `draft_id` to scope by, they're already scoped by `request_id`), because
  anyone can create their own draft and type a victim's real email into it with zero proof of
  ownership, then use *that* draft's sends to burn the shared per-email cooldown/hourly budget
  and block the victim's own "resend code" button for up to an hour. This incidentally fixed
  an already-flagged flaky test (`tests/web/test_fix_f2_already_received.py`, real-clock,
  shared fixed test email `doris.p@example.org` across many test files) — draft-scoping the
  budget means unrelated tests using the same address no longer share a rate-limit counter at
  all.
- **A `FixedClock` (`ham.platform.clock`) advances via `.advance(timedelta)`, not `.tick()`**
  — there is no `tick` method; grep the class before guessing a name that reads naturally.
- **`ham.platform.church.church_profile()` returns a frozen `ChurchProfileView` dataclass, not
  a mutable model instance** — to change the phone/email/etc. a test exercises, mutate the
  real singleton row instead: `from ham.platform.models import ChurchProfile; row =
  ChurchProfile.get_solo(); row.ham_phone = "..."; row.save(update_fields=["ham_phone"])` (the
  view's `phone`/`email` map from the row's `ham_phone`/`ham_email` fields, not same-named).
- **A free-text note field that's only ever collected for ONE specific fixed-vocabulary code
  (here: hazards' `hazard_note`, only ever paired with `Hazard.SOMETHING_ELSE` by the form)
  must be attached to that code specifically when reconstructing a list from a stored
  comma+paren string, not to "whichever code happens to be first"** — `ham.requests.
  presentation.hazard_labels` now looks for `"something_else"` among the parsed codes and
  attaches the note there; when it's absent (a defensive-only case — the form itself requires
  it) and there's more than one code, the note becomes its own separate item (`code=""`,
  already-existing rendering shape for "note with no codes at all") rather than silently
  landing on an unrelated hazard. Kept a narrow backward-compatible exception: when there is
  *exactly one* code (no "something_else" needed to disambiguate at all), the note still
  attaches to that lone code, same as before — several pre-existing tests exercise a single
  arbitrary code + note as a generic "parenthetical-note parsing" fixture, not a hazard-
  semantics one.
- **Removing a function whose only caller imported a module for exactly that one call trips
  `lint-imports`'s "unused ignore" check, and it's a hard failure (exit 1), not a warning** —
  deleting `ham.requester_portal.notifications.send_found_request_email` (its only reason to
  import `ham.integrations.email.service`) left a stale `ignore_imports` entry in
  `pyproject.toml`'s `[tool.importlinter]` section; `lint-imports` fails the whole run on "No
  matches for ignored import X -> Y" until the now-dead ignore line is deleted too. Grep
  `pyproject.toml` for the module's own name whenever deleting its last cross-layer import.
- **A "leadership viewer" page wrapping an already-authorized raw media route
  (`ham.web.views_requests.request_media_thumb`/`request_media_view`) should reuse the exact
  same scope/masking checks by hand (`get_request_by_id(ctx, request_id)` then
  `is_masked_view(ctx)`), not factor `_serve_media` to also return HTML** — the new
  `request_media_viewer` view (`/requests/<id>/media/<mid>/`, new URL name
  `request_media_viewer`) sets `Cache-Control: no-store` manually rather than stacking
  `@never_cache` on top (the two don't compose to the same string — `@never_cache` adds
  `max-age=0, no-cache, must-revalidate, private` alongside `no-store`, which broke an exact-
  match test expecting bare `"no-store"`, the same value `_serve_media`'s raw routes send).
  Gallery thumbnails (`_request_media_gallery.html`) now link `<a href>` at this new route
  instead of the raw `/view` route; the raw route is unchanged and is what the new page's own
  `<img>`/`<video src>` still points at.
- **The e2e/Playwright suite silently times out waiting for a selector (30s, unhelpful stack)
  when the frontend simply hasn't been built yet in this worktree (`frontend/dist` missing) —
  not a flaky test.** `npm ci --prefix frontend && npm run build --prefix frontend` once per
  worktree before trusting any `tests/e2e/*` failure as a real regression; check `ls
  ham/web/static/web/dist/` or `frontend/dist` first if an e2e test fails on a file this
  slice never touched.
- **Verifying "fails before, passes after" empirically for a fix round with many small,
  interdependent changes**: `git worktree add /tmp/<scratch> <pre-fix-sha>`, copy just the new/
  changed test files into it (not the source), point a second scratch Postgres DB at it,
  `migrate` then `pytest` them there — every one should fail (confirms the test actually
  exercises the old bug, not a tautology), then re-run the same files against the real
  worktree's post-fix code (should all pass). Clean up with `git worktree remove --force` +
  `DROP DATABASE` when done; don't leave the scratch worktree/DB behind.

## S3.0 (step 3 approvals — seams and contracts)
- **`AppendOnlyOnceMixin`** (`ham/requests/models.py`): generalizes
  `RequestContactVerification`'s single-field Python-level append-only guard to models that
  need *several* independent "settable once, from null" field groups (`Approval`'s
  told-by-phone pair, undo pair, and effects-ran-at marker; `RequestQuestion`'s answer group
  and closed group). A plain mixin (not a `models.Model` subclass, no `abstract=True`) so MRO
  cooperates cleanly with `models.Model` in `class Approval(AppendOnlyOnceMixin,
  models.Model)`. Declares `ONCE_FIELDS: frozenset[str]`; `save()` after insert requires
  `update_fields=[...]` naming only those fields, and refuses if the current DB value isn't
  still `None`/`""`/`False`. A model with `ONCE_FIELDS = frozenset()` (`Reconsideration`) is
  therefore fully immutable after insert with zero extra code. Reuse this for any future
  model needing more than one append-only exception field instead of hand-rolling another
  `save()` override.
- **A CHECK constraint fix that used to be a silent no-op will surface real bugs at other,
  unrelated call sites the moment it becomes real** — fixing `req_closed_at_when_terminal`'s
  tautology (`approvals.md §2.1`) into two real CHECKs broke `seed_dev_requests.py` (created a
  CANCELLED row open, closed it in a follow-up `.save()` — the *initial insert* now violates
  the constraint) and a step-2 fix-round test (`test_fix_f2_urgency_reason.py`, manually set
  `closed_at` on a still-`AWAITING_APPROVAL` row without also moving `status` to `CANCELLED`).
  Both were latent: the old constraint let an open-status row carry a `closed_at` silently.
  Run the **full** suite (not just the new model's own tests) after tightening any
  long-standing tautological/no-op constraint — grep for `.save(update_fields=[...` near
  `closed_at`/`status` assignments is a fast way to find every other two-step
  create-then-close call site before they surface as CI failures instead.
- **A Playwright/e2e test failing with a 30s `Locator.wait_for` timeout on a selector the
  diff never touched, right after a fresh `git worktree add`, is almost always a missing
  frontend build, not a real regression** — `frontend/dist`/`ham/web/static/web/dist` don't
  exist until `cd frontend && npm ci && npm run build` has run once in *this* worktree (each
  worktree is its own checkout). Confirmed by re-running the same two failing tests after the
  build: both passed unchanged. Do this once, early, per worktree — before spending time
  investigating an e2e failure as a real bug.
- **Service-layer seam files for a slice's own later implementer, not appended to an
  already-live file another parallel slice also edits**: `ham/requests/services_decisions.py`
  / `services_questions.py` (new, `NotImplementedError` stubs per approvals-contracts.md §2)
  and `ham/web/urls_requests_approvals.py` / `urls_requester_approvals.py` (new, empty
  `urlpatterns: list = []`, spliced into `ham/web/urls.py` as a no-op today) — mirrors
  `ham/web/urls_inbox.py`'s S2.0 "empty stub, real routes land later" shape, but as brand-new
  files rather than edits to `services.py`/`urls_requests.py`, which other parallel worktrees
  (S3.2/S3.3/S3.6/S3.7) are actively building against in the same commit window. One
  exception: `close_open_questions(request_id, *, reason)` is a real, fully-implemented plain
  function (not a stub) in the S3.3 seam file, because S3.2's decision commands call it
  *inside their own transaction* the moment a decision closes a request — S3.0 fixed its exact
  behavior so S3.2 doesn't have to guess. A plain function calling `.save(update_fields=[...])`
  on an `AppendOnlyOnceMixin` model needs no `ctx`/authorization of its own when it is always
  a side effect of another, already-authorized command, never a standalone entry point.
- **New matrix actions declared this slice but not yet wired to a real `@command` site must
  be added to `tests/audit/test_command_registry.py`'s `PLACEHOLDER_ACTIONS`**, or
  `test_every_mutating_matrix_action_is_wired_or_a_known_placeholder` fails — this file isn't
  in a "seams" slice's nominal owned-files list, but it's a static registry test that breaks
  the moment any new matrix row's stub isn't `@command`-wrapped yet; touch it in the same
  commit as the matrix rows, with a comment naming which later slice wires the real command.
- **Held/undoable side effects (Q-156/Q-176 "confirm first, undo within a window"): a
  scheduled job at `effective_at` that checks `undone_at` first, not a new outbox/effects
  table.** Store `effective_at = decided_at + <undo window>` directly on the decision row
  itself (computed once, at write time — never recomputed from the live rule later), defer
  one job for it the same way `ham.requests.jobs.defer_complete_intake_checks` defers from
  inside the write transaction, and give the row its own idempotency marker
  (`effects_ran_at`, one more `ONCE_FIELDS` entry) so a retried job invocation is provably a
  no-op. Keeps "was this undone" a single append-only-once field pair
  (`undone_at`/`undone_by_user_id`) instead of a second table to keep in sync. Effects that
  must NOT be held for safety (an urgent-approval alert) go out immediately through the
  normal `@command` outbox path from the deciding command itself, never through the held-
  effects job — write that split down explicitly in the contracts doc, since it's easy to
  assume "the decision's outbox event" is one single held thing when it's actually two
  (an immediate safety alert plus separately-held effects).
- **Coordinator correction: a plain `UNIQUE(request, stage)` on an "undoable decision" row is
  wrong — undo must free the slot for a fresh decision, not permanently occupy it.** My first
  cut of `Approval` kept a plain `UNIQUE(request, stage)`, reasoning (wrongly) that this was
  what Q-176's "other approvers can't decide during the window" required, and flagged
  "decide again after undo" as an open gap instead of just fixing it — undo's entire point
  (Q-156/Q-176: "fix a mistake ... recorded, never deleted") is that the request returns to
  its prior state and can be decided again, by anyone eligible. Fix: a **partial** unique
  index, `UniqueConstraint(fields=["request","stage"], condition=Q(undone_at__isnull=True))`
  — only *live* (not-undone) rows are unique per stage, so undoing a row frees its slot for
  exactly one new live decision while two *simultaneously live* decisions for one stage are
  still refused (the "can't decide during the window" property falls out automatically, for
  free, from the row still being live). When a slice's own migration hasn't merged yet, fix a
  constraint like this by editing the model and **regenerating the same migration** (`migrate
  <app> <prior>`, delete the migration file, `makemigrations`, `migrate`) rather than adding a
  second one — confirm the fix is real by reverting the constraint change temporarily, running
  the new regression test (must fail), then restoring it (must pass) before committing. **Only
  do this when the migration is still your own slice's, not yet relied on by anyone else** — a
  migration another already-merged/parallel slice's code and tests depend on (e.g. S3.0's
  shared `requests/0004`, containing `Approval`/`Reconsideration`/`RequestQuestion` in full,
  not a stub) should get a normal new follow-up migration (`0005_fix_...`) instead;
  regenerating an already-relied-upon migration in place risks silently rewriting history
  other parallel worktrees' own migration state assumes is fixed.

## S3.3 (HAM questions to the requester)
- **A `CheckConstraint` written as a biconditional (`answer='' <=> answered_at IS NULL`) on a
  model whose own manager method exists specifically to *erase text while keeping the date*
  (Q-145 retention: "blank `answer`, keep `answered_at` so 'Answered on {date}' and outcome
  reporting still work") is a bug the moment that method actually runs** — S3.0's
  `RequestQuestion` shipped exactly this shape (`reqq_answer_iff_answered_at`), which
  `erase_text_for_retention`'s own `.update(answer="")` immediately violates. The fix is
  loosening the CHECK to the one-directional invariant that was actually meant (`answer<>'' ⇒
  answered_at IS NOT NULL`; the reverse — a surviving `answered_at` with erased text — is the
  retention state itself, not a defect), in a new migration since `0004` was already shared/
  relied-upon (see the note above). Lesson: whenever a contract promises "blank text field X,
  keep timestamp Y", write the retention test *first* and actually run it against the real
  constraint before trusting the schema someone else wrote is compatible with it.
- **Requester ownership proof = "came from a token resolved fresh, right now" — a
  `RequesterContext` is never itself the proof, only the vehicle.** `answer_question`'s job is
  just `ctx.request_id == question.request_id` (the matrix's own `Scope.OWN_REQUEST` already
  does this before the function body runs; the in-body check is defense in depth for a caller
  that builds a `RequesterContext` by hand). The actual security property — "a forwarded/old
  link can't act" — lives one layer up, in `ham.requester_portal.services.resolve_token`
  always being called per-request, never cached/reused across requests; there is nothing a
  callee holding a `RequesterContext` can check to detect "this came from a stale token",
  because a freshly-resolved context for the *current* (surviving) link is indistinguishable
  in shape from one that was somehow held onto longer. Test this at the integration seam
  (`resolve_token(old_token) is None` after a second `issue_link` supersedes it), not by
  trying to fabricate a "stale" `RequesterContext` object directly — that object carries no
  timestamp/staleness of its own to assert against.
- **Reuse `ham.requests.queries.is_masked_view(ctx)` for any new "Administrator sees X but not
  Y" rule** (Q-124/Q-151) rather than re-deriving the Administrator-role-without-leadership-
  role-and-not-impersonating-around-it check again — it already handles the impersonation
  loophole (`ctx.real_user_id` check) that's easy to miss on a first pass.
- **Implementing a stub the seam-owner (S3.0-style) declared touches three shared files, not
  just the stub's own module**: (1) the stub's own file: replace `NotImplementedError` bodies
  with real `@command`-wrapped ones; (2) the shared `tests/.../test_*_service_stubs.py` (or
  equivalent) that pins "still raises `NotImplementedError`" for the whole seam — remove only
  *your* functions' `lambda:` entries from its parametrize list, leave the other slice's stubs
  (still genuinely unimplemented) alone; (3) `tests/audit/test_command_registry.py`'s
  `PLACEHOLDER_ACTIONS` — remove your now-wired action codes so
  `test_every_mutating_matrix_action_is_wired_or_a_known_placeholder` doesn't silently pass
  for the wrong reason (a `@command` site now exists, it should count as wired, not as an
  ignored placeholder). All three are usually owned by someone else's slice on paper, but
  editing them minimally (only the lines your own newly-real functions touch) and flagging it
  in the hand-back is the expected move, not leaving the shared file broken/stale.
- **An "owner decisions and reconciliation" box's numbers can contradict the *same document's*
  contracts-file appendix, not just its own prose body** — approvals.md's box said "question
  500 characters, answer 1,000"; approvals-contracts.md §1.4 (written by the same slice,
  S3.0) still said question ≤500/answer ≤2000 in the model docstring, an unfixed copy-paste
  from before the box was added. The box wins (repo rule: "overrides the text below and the
  other step-3 plan where they differ"), but the mismatched contracts-file text is worth
  flagging in the hand-back for whoever reconciles docs — a later reader trusting the
  contracts file alone would get the wrong number.
- **A test asserting a cross-cutting "every closing edge does X" rule (approvals.md §2.2
  "auto-closes open questions ... in the same transaction") must check the *actual* real
  command, not just call the lower-level helper it's supposed to wire in** — writing
  `cancel_request(...)` then asserting the question got auto-closed looked like the obvious
  test, but `cancel_request` (a different slice's file, not yet updated to call
  `close_open_questions`) doesn't do this yet; the test would have been asserting future/
  wished-for behavior, and (as happened here) failed immediately, revealing it's not wired.
  Test your own function directly, and flag in the hand-back what the *other* file still
  needs to call, rather than writing an integration test across a not-yet-built seam.

## S3.2 (decisions core: approve/reject/certify/reconsider/undo/held effects)
- **"First decision wins" concurrency needs no special mechanism beyond the existing
  `select_for_update()` pattern.** `approve_request`/`reject_request`/`decide_reconsideration`
  already `select_for_update()` the `AssistanceRequest` row before calling `check_transition`;
  a second concurrent decider's transaction blocks on that row lock until the first commits,
  then re-reads a status that's already moved on, so `check_transition` returns `WRONG_STATE`
  on its own. The `Approval` table's partial unique index (`condition=Q(undone_at__isnull=
  True)`) is a DB-level backstop for any write path that *doesn't* go through this lock, not
  the primary mechanism. Testing this for real needs `@pytest.mark.django_db(transaction=True)`
  + two real `threading.Thread`s (a plain `db` fixture's single wrapping transaction can't
  demonstrate cross-transaction blocking) — **and that real-commit test must clean up after
  itself**: every job it deferred (including an unrelated one a shared test helper enqueues,
  e.g. `submit_request`'s own `defer_complete_intake_checks` even when the test also calls
  `complete_intake_checks` directly right after) survives the test's DB flush as a real
  `procrastinate_jobs` row. Don't call `run_due_jobs_now()` to "clean up" — it *executes*
  every due job, including that unrelated stale one, which can now fail loudly against
  already-decided state (`wrong_state`) and crash the test. Instead, delete the leftover
  `todo` rows directly (`DELETE FROM procrastinate_jobs WHERE status = 'todo'`) so nothing
  survives to be picked up by an unrelated *later* test's own `run_due_jobs_now()` call
  (confirmed empirically: without this, two unrelated tests two files away failed with
  `AssistanceRequest.DoesNotExist` purely from running the suite in full vs. deselecting the
  one `transaction=True` test — order/isolation bugs like this only show up at full-suite
  scale, never in isolation).
- **A held-decision-effects job doesn't need its own new outbox/effects table — reuse the
  decision's own `effective_at` + a same-shaped idempotency marker (`effects_ran_at`,
  `ONCE_FIELDS`) already declared on the `Approval` row, and `ham.jobs.defer_later(...,
  schedule_at=...)`** (the existing "defer a job for a specific future instant" primitive,
  distinct from `periodic_job`'s cron shape). The job itself: re-fetch under
  `select_for_update()`, check `undone_at` first (still mark `effects_ran_at` even when
  undone — that's what makes a retried/duplicate invocation provably a no-op either way), then
  release effects and mark `effects_ran_at`. Release = emit the *same* `RequestApproved`/
  `RequestRejected` outbox event the deciding command *didn't* emit at decide time (the normal
  `@command` pattern doesn't apply to this one event for this one purpose) plus call the
  already-real `close_open_questions(request_id, reason="request_closed")` — never re-derive
  "what does closing mean" logic in the job; call the one function that already knows.
- **"The urgent-approval alert is never held" means literally emit the decision's own outbox
  event (`RequestApproved`/`UrgencyCertified` with `urgent_approval=True`) a second time,
  immediately, from inside the deciding `@command`'s own transaction** (via `ham.outbox.api.
  emit` called by hand, same shape as `complete_intake_checks`'s hand-written second audit
  row) — *not* a new, separate "alert" event type. The held copy still goes out later at
  `effective_at` for the batch-close/question-close/leader-update side effects; the immediate
  copy exists purely so the leadership notification builder (a later slice) can react to
  `urgent_approval=True` right away. This means `RequestApproved` can legitimately be
  delivered twice for one urgent decision (once immediate, once held) — every subscriber for
  it must already be a safe no-op on a repeat for the same `request_id`/`stage` (media close
  and `close_open_questions` already are; flag any new one that isn't in the hand-back rather
  than silently assuming).
- **`Approval` stores no "urgency before this decision" field** — a decision that bundled a
  certify/decline (`approve_request(certify_urgent=True/decline_urgency=True)`) can't have
  that urgency choice reconstructed and restored by a later `undo_decision` call; undo can
  only safely restore the request's *status* (and `closed_at`/`reconsideration_deadline_at`
  where the decision closed/opened the request). Don't invent a reconstruction heuristic
  (e.g. "certify implies it was AWAITING_CERTIFICATION") — it's genuinely ambiguous (could
  also have been NOT_CERTIFIED) with today's schema. Flag it as a real gap in the hand-back
  instead of guessing.
- **A matrix action declared `ANY` scope with `resource_from` omitted is fine** — `Scope.ANY`
  never inspects the resource `authorize()` receives, so a command like `request.decision.undo`
  (looked up by `approval_id`, not `request_id`) doesn't need a `resource_from` at all; don't
  manufacture one just to match a pattern other commands in the same file happen to use.
- **Extending an existing edge's actor set to include already-closable states (the CANCEL
  extension, Q-165) means auditing every existing caller of `check_transition` for that
  action, not just adding the new source states to `states.py`.** `ham.requests.services.
  cancel_request` (a different slice's original file) had never passed `now`/`closed_at`/
  `decision_undo_open` to `check_transition` at all — harmless while CANCEL's only sources
  were pre-decision statuses (nothing there is ever "closed" or mid-undo-window), but once
  APPROVED/RECONSIDERATION_PENDING joined the source set those three facts are exactly what
  gates "not while closed already" (`ALREADY_FINAL`) and "not while the decision that
  produced this state can still be undone" (`DECISION_UNDO_WINDOW_OPEN`). Grep every call
  site of an edge before assuming "the rule lives in states.py" is the whole story — a caller
  built before the edge grew new guards can silently bypass them by omitting the new kwargs
  (they all default away to "no restriction").
- **When a coordinator/merge note says "every closing edge must call `close_open_questions`
  in the same transaction," that's about *immediate* closes (cancel, finalize) — it does
  *not* override a slice's own already-decided held-effects design for a *different* set of
  edges (the Approval-driven approve/reject/reconsider-reject closes, which intentionally
  hold question-closing until `effective_at` per the undo contract).** Read a coordinator
  note as "the specific gap it names," not as blanket license to unwind a documented,
  deliberate design difference elsewhere — when genuinely unsure whether it's one or the
  other, that's a "stop and report the conflict" moment, not a silent pick.

## S3.2 coordinator fix round (undo restores urgency; standalone urgency review undoable; no double-delivered RequestApproved)
- **When a pure rules function (`states.py`) already accepts a parameter your service layer
  never passes, check whether the rules layer quietly anticipated a fact your model doesn't
  persist yet** — `check_undo`'s `prior_urgency`/`accompanying_urgency` params, and its whole
  `isinstance(kind, UrgencyAction)` branch, were already built and tested by S3.1 *before*
  `Approval` had anywhere to store "urgency before this decision" or before any
  standalone-urgency-review record existed at all. Once the two missing columns
  (`Approval.prior_urgency`/`.accompanying_urgency`) and the new `UrgencyReview` model landed,
  zero changes were needed in `states.py` — the fix was entirely "persist the fact at decision
  time, then pass it through", not new pure-function logic. Don't assume a flagged gap needs
  rules-layer work without first re-reading the rules function's own signature for params your
  service never uses.
- **A record that's "undoable within a window" but has no held effects of its own still wants
  the same `effective_at = decided_at + DECISION_UNDO_WINDOW`, computed-and-stored-once
  shape** as a record that does (`Approval`) — `UrgencyReview.effective_at` exists purely so
  `decision_is_undoable`/the undo-window check reads a stored value, never recomputes from a
  possibly-since-changed rule, even though nothing is ever deferred to run *at* that instant.
  Don't skip the field just because "there's no job to schedule" — the undo-window contract
  and the held-effects contract are two separate reasons to store the same kind of timestamp.
- **"Emit event X's payload flag to drive a later notification" and "emit a whole second copy
  of event X" are different fixes for the same underlying need, and only one of them avoids
  double delivery.** The pre-fix design used `RequestApproved(urgent_approval=True)` as an
  *immediate* alert AND relied on the exact same event type as the *held* copy for
  batch-close/question-close/leader-update — meaning any urgent decision produced two
  deliveries of one event type, silently requiring every subscriber to be repeat-safe. The
  fix was a **dedicated event type** for the immediate-only concern (`RequestUrgentApproval`),
  never reusing the held event's name for an out-of-band emission. When a coordinator says
  "don't double-deliver X", check whether the immediate and held paths are using the *same*
  event type before assuming a payload-shape tweak is enough — if they are, the real fix is
  splitting the event, not deduping payload fields.
- **Two different "kinds of undoable record" sharing one action code
  (`request.decision.undo`) is cleanest as one `@command` function with two private,
  same-shaped helpers it dispatches to** (`_undo_approval`/`_undo_urgency_review`), not two
  separate `@command("request.decision.undo")` sites — `tests/audit/test_command_registry.py`
  explicitly forbids the same action string being wired twice (`test_no_command_action_is_
  defined_twice_with_different_wiring`), so "reuse the matrix action, extend the function
  signature to take either id (exactly one)" is the only shape that both reuses the action and
  keeps the one-write-path invariant. `ctx.effective_roles`/impersonation-block/step-up all
  still apply uniformly across both record kinds for free, since they're evaluated before the
  dispatch, at the matrix-action level.
- **Coordinator fix-round workflow that actually proves the fix:** write the new/updated
  tests first, run them against the pre-fix code to confirm they fail for the *right* reason
  (not a typo), then implement, then re-run to green, then run the *whole* existing suite
  (not just the new tests) since a payload/event-shape change ripples into every earlier test
  that asserted the old shape (`test_s32_decisions.py` had three tests asserting the old
  `RequestApproved(urgent_approval=True)`/`UrgencyCertified(urgent_approval=True)` payloads
  that needed updating alongside the fix, not just new gap-specific tests).
