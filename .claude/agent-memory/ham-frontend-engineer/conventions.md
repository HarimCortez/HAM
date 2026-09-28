# ham-frontend-engineer conventions

## Locations
- Shell templates: `ham/web/templates/web/` (`base.html` signed-in, `base_public.html`
  signed-out — no nav). Partials start with `_` (`_nav_items.html`, `_impersonation_banner.html`,
  `_not_found_content.html`, `_server_error_content.html`, `_head.html`).
- Shell CSS: `ham/web/static/web/shell.css`. Tokens only, from `design-system/tokens.css`
  (built by `manage.py build_tokens --brand <brand> --check`). Icons: `ham/web/static/web/icons.svg`
  (hand-drawn Lucide-style symbols, `<use href="...#icon-<name>">`); add new ones there, not
  inline SVG paths in templates.
- Nav is server-computed, never hard-coded in templates: `ham.authz.nav` (`nav_for`,
  `bottom_nav_for`, `admin_group_items`, `more_items`) → `ham.web.nav` (adds `.built` filter,
  request-aware wrappers) → `ham.web.context_processors.shell` (puts `nav_items`,
  `bottom_nav_items`, `nav_active_key`, `bottom_nav_active_key` in every template's context).
- Audit action labels: `ham/audit/labels.py` (`ACTION_LABELS`, `ACTION_GROUPS`) — add every
  new audit `action=`/`audit_action=` string here too, or the UI shows the raw code.
- Church-local time: `ham.platform.church.format_church_time`, exposed as the `church_time`
  template filter (`ham/web/templatetags/web_extras.py`). Never render a raw UTC datetime.

## Mobile nav (navigation.md §3.1, Q-091)
- `bottom_nav_for(ctx)` caps the phone bottom nav at 5 items. Only `ADMINISTRATOR` gets a
  dedicated "Admin" tab (grouping Users & roles/Church settings/Integrations/Rules/Audit log
  behind `GET /admin`); `ADMINISTRATOR`/`HAM_DIRECTOR`/`ASSISTANT_DIRECTOR` end in a "More"
  tab (`GET /more`: leftover admin-group items + Me + Sign out) instead of a direct Me tab;
  everyone else ends in Me directly. `tests/authz/test_nav_mobile.py` is the source of truth
  for this — read it before changing the rule.
- Sign out is a POST-only route (`web:sign_out`, owned by identity/auth work) — link to it
  with a `<form method="post">`, never a plain `<a href>`.

## Ownership boundaries hit during Fix C
- `ham/identity/*` (models, middleware, services) belongs to the auth/identity slice. Don't
  edit it for a UI fix — instead add a small resolution in `ham.web` (e.g.
  `context_processors.shell` calls the existing `get_user_detail()` read to get a *full* name
  for the impersonation banner, because `ActorContext.target_display_name` and
  `display_names_for()` both intentionally return the short "Kevin T." form used in the audit
  log — don't "fix" that; it's by design, only the banner wants the full name).
- `ham/web/templates/web/auth/*` and `ham/web/auth_views.py`/`stepup.py` may be owned by a
  parallel Fix while it's in flight — check the current task's file-ownership note before
  editing. Once that Fix merges, the public-layout CSS (`.public-shell`, `.public-card`,
  `.btn--ghost`, etc.) already applies to those templates automatically since they extend
  `base_public.html`; usually only small copy/class tweaks (guard blank `church.phone`, apply
  `.btn--ghost` to a Cancel/Sign-out button) are needed, not a rewrite.

## Gotchas
- MFA-required roles' permissions don't activate until `request.session["ham_mfa_satisfied"]`
  is set (Q-045, `ActorContext.effective_roles`). Any test fixture that signs in an
  Administrator/Director/Pastor/Board rep and then hits a real route must set that session key
  (see `tests/web/test_admin_screens.py`'s `_mfa_login`), or every `@requires_action` check
  fails and the route 404s (looks exactly like a routing bug — it isn't).
- The shared `.venv` at `/home/user/HAM/.venv` has an **editable install pinned to the main
  checkout** (`/home/user/HAM/ham`, not this worktree) for the `ham`/`config` packages *and*
  separately for the `ham.web.templates`/`ham.web.static` namespace packages
  (`__editable___ham_0_1_0_finder.py`'s `MAPPING`/`NAMESPACES`). Running `python some_script.py`
  directly (sys.path[0] = the script's own directory) can silently load templates/static from
  the *other* checkout. Always run via `pytest`/`manage.py` from the worktree root (or
  `python -c "..."`, which puts cwd on sys.path first) so the worktree's own files win.
- HTML-escaping: a template label containing `&` (e.g. "Users & roles") renders as
  `Users &amp; roles`; assert against the escaped form in response-content tests.
- `docs/prd-open-questions.md`'s "UX backlog" section is the tracker for
  navigation/screens gaps the ux/ui reviewers file (Q-091, Q-092, ...) — update the entry to
  "Done"/"Closed" with a one-line pointer to the fix and its tests, don't just delete it.

## Step 2 (Intake), S2.7: public requester screens (R1-R12)
- Location: views `ham/web/views_requester.py`, urls `ham/web/urls_requester.py` (spliced
  into `ham/web/urls.py` already), templates `ham/web/templates/web/requester/*.html`
  (`_step_header.html`/`_error_summary.html` partials), CSS appended to the end of
  `ham/web/static/web/shell.css` under the "Step 2 (Intake), S2.7" banner comment.
- Every requester route name is public (`ham/authz/guard.py` `PUBLIC_ROUTES`) — there is no
  `ActorContext`/sign-in for a requester (PRD §7). Per-request access control is the draft
  resume cookie (`ham.requester_portal.cookies`) or the access-link token
  (`ham.requester_portal.services.resolve_token`) the view resolves itself, exactly like
  `ham.web.auth_views`'s sign-in-link family.
- The wizard is one view per step (`request_help_step(request, step)`), not one Django
  `Form` per step: each POST merges that step's fields into the whole draft payload and calls
  `ham.requester_portal.forms.validate_intake_payload` on the *merged* result, then only shows
  the errors belonging to that step's own field set (`_errors_for_step`) — reuses the portal's
  one whole-payload validator instead of duplicating field rules.
- Anti-abuse (honeypot + minimum fill time, `ham.requester_portal.antiabuse`): the fill-time
  clock starts once, in the session, when the wizard is first begun
  (`request_help_begin`/`_SESSION_FORM_OPENED_AT`) — not re-stamped on the review step's own
  GET, or a real multi-step fill (which takes longer than the review page alone) can still
  trip "too fast" incorrectly. Tests that drive the whole flow via the Django test client (near
  -instant) must backdate this session key past `RULES.intake.INTAKE_MIN_FILL_TIME` (see
  `tests/web/test_requester_portal_screens.py`'s `_backdate_form_opened_at`) or the submission
  silently no-ops (by design — same page, nothing sent). A real-browser (Playwright) test
  instead just waits out the real `INTAKE_MIN_FILL_TIME` before clicking Send.
- The secure page's own read model is `ham.requests.queries.get_request_for_requester` (added
  by S2.7, not S2.2 — `RequestDetailRow` is leadership-shaped and calls `authorize()`
  internally, wrong for a self-view already scoped by the resolved link token). Returns raw
  field values; the view/template is responsible for masking (`ham.requester_portal.projection
  .masked_contact`) before render.
- R9 upload module: `frontend/src/upload.ts`, built to `frontend/dist/upload.js` (added a
  second `esbuild.build()` call in `frontend/scripts/build.mjs`; keep both in sync if the
  build script changes shape again). Talks to `POST .../media/reserve` (JSON) ->
  `ham.media.services.reserve_uploads`, then PUTs straight to the presigned URL with
  `Content-Type` from the reservation response (`PresignedUpload` carries no headers of its
  own), then `POST` the per-file `complete_url` -> `ham.media.services.complete_upload`.
  `XMLHttpRequest`, not `fetch` (upload progress events).
- Gotcha: a Django test-suite-wide `#[0-9a-fA-F]{6}` hex-color-hard-coding check
  (`tests/web/test_no_hardcoded_church_or_colors.py`) also matches HTML numeric character
  references like `&#128274;` (6 hex-looking digits) — use `&#x1F512;`-style hex entities
  (the `x` breaks the match) or a literal Unicode character instead.
- Gotcha: `ham.requester_portal.services`'s three cross-app lookups
  (`register_request_facts_lookup` etc.) are *global* module state; other test files reset
  them to `None` on teardown instead of restoring the real production callables
  (`RequesterPortalConfig.ready()`'s own registration), so a view-level test that runs after
  one of those in the same pytest process needs its own autouse fixture re-registering the
  real callables (copy `tests/requester_portal/test_submission_flow.py`'s
  `_real_portal_lookups` fixture) — don't rely on process-startup registration surviving.
- Playwright text selectors: `text=Confirm` (unquoted, substring) can match unrelated prose
  containing the word ("Or tap **Confirm my email**...") as well as the actual button, and
  clicking the wrong match times out waiting for navigation with no obvious error. Scope to
  the tag: `button:has-text('Confirm')`.

## Known open item (handed back, not fixed)
- Audit log at >=1280 (visual QA M3): chose fix option (b) — dropped the `.list-detail`
  wrapper so the table fills the width — over building a real split-pane detail view (option
  a). A `?event=<uuid>` query param rendering the detail in a second grid column is the next
  step if the product owner wants that back.
