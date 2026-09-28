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

## Step 2 (Intake) fix round FIX-C (step2-ui-visual-qa.md / step2-ux-usability.md / privacy-security.md)
- **Layer rule for label maps:** `ham.requests` sits *below* `ham.requester_portal` in the
  layer order, so `ham.requests.presentation` (leadership labels) can't import
  `ham.requester_portal.choices` (hazard/availability vocab) even though the codes are
  identical -- duplicated `HAZARD_LABELS`/`AVAILABILITY_LABELS` there by hand, commented "keep
  in sync". `ham.web` (top of the stack) CAN import both, so `views_requester.py`'s R10
  `_hazards_display`/`_availability_display` were rewritten to delegate to
  `ham.requests.presentation.hazard_labels`/`availability_labels` instead of keeping their own
  second, buggier parser (the old one broke when a hazard note itself contained a comma).
- **A template tag name can be a variable.** Django templates are plain text substitution
  before HTML parsing, so `<{{ heading_tag }} id="...">...</{{ heading_tag }}>` legitimately
  renders `<h2>...</h2>` or `<h3>...</h3>` depending on context -- used this to fix L2's
  heading-order (`_request_detail.html`'s sections are `<h2>` on the standalone page, `<h3>`
  in the split pane, from one shared partial) instead of duplicating every section block.
- **`{{ var|filter }}` escapes; literal template text doesn't.** A pre-existing test asserted
  on a raw apostrophe (`b"We've received your request"`) that used to come from literal
  template text; once R10's welcome-mode text was unified to go through the same
  `{{ status_sentence }}` variable the non-welcome path already used, Django's autoescaping
  turned it into `We&#x27;ve received your request` -- byte-exact response-content tests need
  to assert the escaped form once a literal moves into a variable (matches the existing "HTML
  escaping" gotcha above, worth re-checking any time inline copy becomes a context var).
- **`django.views.decorators.cache.never_cache` composes fine with `@requires_action`/
  `@require_http_methods`** despite `requires_action` mutating the bare function's `__dict__`
  rather than wrapping it -- `functools.wraps` (which both Django decorators use) copies
  `__dict__` forward through the chain either way, so decorator order around it doesn't matter
  for the route guard. Added to `request_detail`, `request_reveal_contact`,
  `request_phone_check`, `request_help_secure_page` (privacy/security L5).
- **The close-note-in-URL fix (H3):** `request_close`'s POST error path now re-renders
  `web/request_close.html` directly with `status=422` and the posted `reason_code`/`note`
  instead of `redirect(...?note=...)`. The L5 "Close this one as a duplicate..." link now
  passes `?duplicate_of=<uuid>` only; the view resolves that id to the matched request's
  display number itself server-side (never trusts a client-supplied note string).
- **Split-view row navigation (M12)** is a progressive-enhancement inline `<script>` in
  `requests_list.html`, not a new frontend/dist bundle: every row's real `href` is the
  standalone detail page (works at every width, JS off); a small script rewrites each row's
  `href` to `?tab=...&id=<uuid>` (same list page) only when `matchMedia("(min-width: 1280px)")`
  matches, which is what actually keeps the split view instead of navigating away.
- **`.filter-bar-sheet` (M16):** a `<details>` without `open` collapses the filters behind a
  "Filters" summary below 768px; `@media (min-width: 768px) { .filter-bar-sheet:not([open])
  .filter-bar { display: flex; } }` forces it open above that width by overriding the UA
  stylesheet's `details:not([open]) > :not(summary) { display: none }` rule (author CSS beats
  UA CSS at equal-ish specificity, so this works without ever setting the `open` attribute).
- **Icons:** `icons.svg` had no `siren`/`hourglass`/`inbox`/`shield-check`/`circle-alert`/
  `circle-check`/`circle-help`/`phone`/`phone-incoming`/`chevron-right`/`info`/`image-off`
  before this round; added them (same hand-drawn outline style, `.disclosure summary::after`'s
  chevron is drawn with CSS borders instead, to avoid a static-URL dependency in a CSS file
  whitenoise may hash-rename).
- **`AttentionItem`/`AttentionCard` (ham.requests.attention, ham.notifications.attention)**
  don't carry enough shape for true per-request urgent cards (M17's "Urgent · HAM #050 needs a
  phone check · waiting 3h [Call now]" as its own card) without a registry-wide shape change --
  out of scope for this fix round; only the wording (`_plural_verb_phrase`, oldest-waiting
  context folded into `title`) and the awareness-row-never-gets-a-chip bug were fixed. Flagged
  in the handback as a follow-up if the product owner wants the full per-request split.
- **Known open items handed back, not fixed:** M2 (secondary-link/Back-bar placement rework
  across R1/R2/R8/R12), full `aria-invalid`/`aria-describedby` wiring on every R2-R5 field
  (only R6's error summary + certification group got it), the wizard "Good to know" aside and
  R1-R6/R9 desktop two-column layout (M9 desktop), R3's "Owner's full name" always-visible bug,
  R5 "I don't use email" not locking the contact-preference group, per-request urgent Home
  cards (see above).

## Step 2 (Intake) fix round FIX-D (leftover Majors from FIX-C's visual/UX reports)
- **`{# ... #}` is a single-line Django comment tag.** The tokenizer regex is `{#.*?#}`
  *without* `re.DOTALL`, so `.` never matches `\n` — a `{# #}` comment that spans more than one
  physical line is never recognized as a tag at all, and the literal comment text (including
  internal dev notes) renders straight into the page. This was already present in several
  templates from earlier fix rounds (`home.html`, `requests_list.html`, `_request_detail.html`,
  `_error_summary.html`, `r6_review.html`, `r9_photos.html`, `r10_secure_page.html` — the R10
  one put a stray paragraph of dev notes right above the real `<h1>`) and I reintroduced it
  twice myself before catching it. Always use the block form for anything that doesn't fit one
  line: `{% comment %}...{% endcomment %}`. `tests/web/test_fix_d_no_leaking_template_comments
  .py` now scans every template in `ham/` for this pattern so it can't regress silently again.
- **M2 remainder (secondary links/Back/Resend/Start over below the sticky bar):** fixed by
  moving the secondary `<form>` (Start over, Resend) to live *outside* the primary `<form>`,
  with the button living inside `.action-bar__inner`/`.form-actions` via `form="<id>"` (a
  submit button's `form=` attribute overrides which `<form>` it submits, regardless of DOM
  nesting) — R1, R2, R8. Other secondary content (R1's "Already asked"/"Prefer to talk" links)
  just needed reordering above the form in the template; wrapped in `.public-card__links` (new,
  `shell.css`) for consistent spacing, not a new component.
- **R3 "Owner's full name" / R5 "I don't use email" locking contact preference:** both are
  progressive enhancement done with CSS `:has()`, not JS-only — `#owner-name-field { display:
  none } fieldset:has(input[value="authorized_family_member"]:checked) + #owner-name-field {
  display: block }` in shell.css. R5's lock instead swaps a `.choice-card--locked` (new
  modifier: `bg.sunken`, dashed border, non-interactive) in for the fieldset via the existing
  JS pattern (matches R2/R4's precedent for reveal groups) since the real enforcement is
  already 100% server-side (`ham.requester_portal.forms.validate_intake_payload` always forces
  `contact_preference = phone_call` when `no_email` is set, regardless of what's posted) — the
  UI only needed to *look* locked, not actually block a value from being submitted.
- **Per-field `aria-invalid`/`aria-describedby` + error-summary anchors (R2-R5):** every
  fieldset that can error now has `id="id_<field>"` (some, like R4's hazards or R5's contact
  preference, previously had no id or a different one — `_error_summary.html`'s generic
  `href="#id_{{field}}"` link depends on that id existing verbatim); help/error `<p>`s got
  matching `id="id_<field>-help"`/`-error"` ids referenced from the input's
  `aria-describedby`. R6 is the one step that *doesn't* use `#id_<field>` anchors (the field
  isn't on the review page) — it already had its own `review_errors` → step Edit-URL scheme
  from FIX-C; left that alone.
- **Wizard desktop 2-column (visual M9 remainder), no real spec-matched step rail:** `base_
  public.html` grew one new hook, `{% block card_modifier %}` on the `.public-card` div, so a
  template can opt into a modifier class without editing the shared shell. `.public-card:has(>
  .wizard-aside)` becomes a `size.wizard-max` 2-column grid at >=1280 (all direct children
  except the aside forced to `grid-column: 1`, since CSS Grid's default auto-placement would
  otherwise scatter them across both columns) — R1-R5 and R9 each `{% include "web/requester/
  _wizard_aside.html" %}` after their form, with `aside_heading`/`aside_body` context set in
  `views_requester.py`'s `_STEP_ASIDE` map (`_step_context` looks it up per step). R6 has no
  aside by design (per spec); instead `public-card--review` widens the card to `wizard-max`
  and `.summary-card-grid` turns the 4 summary cards 2x2. R7/R10 (`r10_secure_page.html`) got
  its own, different 2-column treatment (`size.requester-wide-max`, `3fr 2fr`,
  `public-card--request-status`/`.request-status-grid`) since that page has no aside at all —
  don't reuse `.wizard-aside`'s grid rules for it. The step rail itself was *not* built (an
  accepted simplification per both visual QA passes).
- **Home attention cards, one per urgent+actionable request (visual M17 remainder):**
  `ham.requests.attention.awaiting_approval_cards` (renamed from the old singular
  `awaiting_approval_card`) now returns a list: one `AttentionCard` per urgent request in
  `AWAITING_APPROVAL` (title `"{display_number} · {need_category_label}"`, `href=
  "/requests/<uuid>"` straight to that request, PII-free per Q-132) for Pastor/Board rep, plus
  one aggregate card for the rest ("N requests are/is waiting for a decision"). Director/AD's
  muted awareness row stays a single card and is now *never* urgent-flagged (no more danger
  chip on a non-actionable row) — the home.html template's chip logic (`item.urgent and not
  item.muted`) was already correct; the bug was the provider always setting `urgent=True` on
  the shared aggregate regardless of `muted`. No `AttentionItem`/`AttentionCard` shape change
  was needed — `title`/`url`/`urgent`/`muted` already supported this; only how many cards a
  provider returns, and what it puts in each one's `href`.
- **Shared `.filter-bar` (M16) on `audit_log_list.html`:** wrapped each bare `<label>`+
  `<select>`/`<input>` pair in its own `.filter-bar__field` (same fix L1's requests list
  already had), since `.filter-bar select, .filter-bar input { width: 100% }` at <768 was
  forcing every bare control full width with no wrapper to keep its label attached, separating
  them onto different rows. `admin_users_list.html` did **not** need the same treatment — its
  labels are `.visually-hidden`, so there was nothing visible to separate in the first place;
  confirmed with a test rather than changed.
- **Test DB transaction gotcha, take 2:** a *new* test file marked `pytest.mark.django_db(
  transaction=True)` that drives the requester wizard through a review-step POST (which defers
  a "send verification code" Procrastinate job) without ever draining that job will leak an
  undrained `status='todo'` row into whatever `run_due_jobs_now()` call happens to run next in
  the same pytest process — even in a completely unrelated test file — and that test then sees
  an extra, unexpected email in `mail.outbox`. If a new view-level test doesn't specifically
  need `transaction=True` (real cross-request session/cookie continuity works fine under the
  default rollback-per-test `django_db` marker — `transaction=True` is only for tests that
  themselves call `run_due_jobs_now()`/need Procrastinate to see committed rows), just use
  plain `@pytest.mark.django_db`; it rolls back and nothing leaks.

## Known open item (handed back, not fixed)
- Audit log at >=1280 (visual QA M3): chose fix option (b) — dropped the `.list-detail`
  wrapper so the table fills the width — over building a real split-pane detail view (option
  a). A `?event=<uuid>` query param rendering the detail in a second grid column is the next
  step if the product owner wants that back.

## S2.8 (step 2 leadership screens L1-L11)
- Real `.list-detail` split view: `?id=<uuid>` on `GET /requests` selects the detail pane
  (defaults to the top row); `_build_detail_context(ctx, request_id, revealed=...)` in
  `ham/web/views_requests.py` builds one context dict reused by both `web/requests_list.html`
  (via `{% include "web/_request_detail.html" with ... standalone=False %}`, renaming every
  key so it doesn't collide with the list page's own context) and the standalone
  `web/request_detail.html` (`{% include %}` with no `with`, sharing the full view context).
  The partial picks `<h1>`/`<h2>` off `standalone` so a split-view page never carries two
  `<h1>`s. `.list-detail .split-detail { display: none }` below 1280 — the detail pane is
  still server-rendered on that response, just hidden, rather than a second template.
- **A `@requires_action`-decorated view is a plain function**, not a runtime wrapper — the
  decorator only sets an attribute the route *guard middleware* reads via
  `request.resolver_match`'s view function. Calling one view directly from another in Python
  (`requests_needs_phone_check` delegating to `requests_list(request, forced_tab=...)`) does
  **not** re-run any authz check; only going through URL dispatch does. Safe and the normal
  pattern for "this route is a filtered variant of that one."
- **`blocked_while_impersonating` in the matrix blocks the whole route, not just the mutating
  call.** If a GET+POST view shares one `@requires_action("some.command")` and that action is
  `blocked_while_impersonating` (e.g. `request.contact_verify_phone`), the route guard 404s
  the GET too — there's no way to show a sheet with a disabled button while impersonating
  under that pattern. Don't design a UI that assumes the GET is reachable; the neutral 404 *is*
  the impersonation-blocked experience for that whole screen.
- A reveal that must sometimes be un-audited (`ham.requests.services.reveal_requester_pii`,
  Q-024) is called directly from the view, not through `@command` — it does its own
  `authorize()` + conditional audit. The view still must catch `PermissionDenied` itself (no
  `@command` wrapper doing it) and return `not_found.html` (404), e.g. for the Administrator.
- `ham.notifications.services.needs_response_for`/`updates_for`/`urgent_banner_for` are the
  only entry points Home/Inbox/the shell need; "Needs response" is never stored (computed live
  by `ham.notifications.attention.attention_items_for`). The urgent banner (§10/§35, Q-123) is
  wired into `ham.web.context_processors.shell` (not each view) so it shows app-wide — guard
  it with `isinstance(actor.user_id, uuid.UUID)`, since a couple of unit tests build a bare
  `ActorContext` with a placeholder string `user_id` to exercise the route guard in isolation.
- `bottom_nav_for` (`ham/authz/nav.py`) is a hand-maintained tab list, not "every built item";
  flipping a `NavItem.built` flag to `True` does **not** automatically add it to the mobile
  bottom nav or the More page — you must decide where it goes and update
  `tests/authz/test_nav_mobile.py`'s exact-match assertions (`test_administrator_bottom_nav_...`,
  `test_director_bottom_nav_...`) and `tests/e2e/test_smoke.py`'s nav-label assertions
  together, or the mobile smoke test fails on an apparently unrelated persona.
- Icons: `icons.svg` had no `lock`/`eye`/`triangle-alert`/`phone-call`/`copy`/`clipboard-list`
  symbols before this slice; added them (same hand-drawn outline style). Never use an HTML
  numeric character reference for an icon glyph (`&#128274;` etc.) — `tests/web/
  test_no_hardcoded_church_or_colors.py`'s hex-color regex (`#[0-9a-fA-F]{3,8}\b`) false-
  -positives on a 3/6/8-hex-digit-*looking* entity number, and also on a literal request
  number placeholder like `"e.g. HAM #047"` in copy — avoid a bare `#NNN` in template text.
- A `{% include %}`'d partial needs its **own** `{% load %}` line for any tag it uses
  (`static`, `web_extras`, ...); Django's `{% load %}` is per-template-file, not inherited from
  the including template, and the failure mode (`Invalid block tag ... expected 'elif' /
  'else' / 'endif'`) looks like a mismatched `{% if %}` even though the real bug is a missing
  `{% load %}` a few lines up.
- **`transaction=True` / `live_server` e2e tests (`tests/e2e/*`) commit real rows with no
  per-test rollback.** If a test's flow defers a Procrastinate job (e.g. `submit_request`'s
  `defer_complete_intake_checks`) and then the test *also* independently drives the state
  machine forward (a UI action, or calling the command directly) without ever letting that
  original job run, the job row is left `status='todo'` in the shared test DB **permanently**
  (it survives across separate `pytest` invocations, not just within one run) — the next
  *unrelated* test anywhere in the suite that calls `ham.jobs.run_due_jobs_now()` will pick it
  up, find the request has already moved on, and blow up with a `WRONG_STATE` `ValueError`
  that `run_due_jobs_now()` re-raises. Symptom: assertion failures in totally unrelated test
  files, reproducible only when the whole suite runs together, gone when the e2e file is
  excluded. Fix: at the end of any `transaction=True` e2e test that leaves a job undrained,
  `DELETE FROM procrastinate_jobs WHERE status = 'todo'` via a raw cursor (not
  `run_due_jobs_now()`, which tries to *execute* stale rows too, including ones a previous
  interrupted run of the same test already left behind, and needs an ambient transaction for
  `select_for_update()` that a bare test function doesn't have).
