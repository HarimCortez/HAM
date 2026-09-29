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

## S3.6 (step 3 leadership screens: Decision card, A2-A12 sheets, list tabs)
- Files: `ham/web/views_requests.py` (added `_decision_panel`/`_decision_error_redirect`/12 new
  views), `ham/web/urls_requests_approvals.py` (the 12 routes, exact names from
  `docs/architecture/approvals-contracts.md` §8), `ham/web/templates/web/_decision_card.html`
  (new partial, included from `_request_detail.html` before the Earlier-request alert) + 11 new
  `web/request_*.html` sheet templates, `ham/requests/presentation.py` (added
  `REJECTION_REASON_LABELS`/`REJECTION_REASON_PREFILLS`/`DECLINE_MESSAGE_MAX_CHARS` — the S3.0
  contracts doc never assigned an owner for the Q-154 prefill copy, so this slice added it here
  since it's leadership-screen-only display text, same layer as the rest of the file), CSS
  appended to `shell.css` under "Step 3 (Approvals), S3.6", 4 new icons in `icons.svg`
  (`message-circle-question`, `message-circle`, `phone-outgoing`, `calendar-clock`).
- **`_decision_panel(ctx, request_row, detail, has_email=...)`** builds the *entire* Decision
  card's data in one place (state: `awaiting`/`pending`/`decided`/`reconsideration`, or `None`
  for a status the card doesn't cover) by querying `Approval`/`Reconsideration`/`RequestQuestion`
  directly, the same "reach into the model, don't wait on a parallel slice's query module" move
  `_build_detail_context` already made for `Requester.email`. `ham.requests.queries`/
  `queries_questions` are S3.2/S3.3's files, not this slice's — only used where they already
  exposed exactly what was needed (`list_requests(view=...)`, `waiting_on_requester`,
  `question_thread`), never edited.
- **Route-guard-first, not view-first, for "impersonation blocks a whole screen."** Every
  decision/undo/question/phone action is `blocked_while_impersonating` in the matrix, so
  `@requires_action` 404s the entire GET+POST route before the view body ever runs (the
  step-2-established gotcha, "the neutral 404 *is* the impersonation-blocked experience").
  `request.category.change` is the one action that's `blocked_while_impersonating=False`
  (Q-109/Q-172), so only that sheet is reachable while impersonating — proved directly.
- **"Someone decided first" (A13) needed the view's own state check turned from a 404 into a
  friendly redirect.** The natural guard ("if the request isn't in the expected source status,
  404") looks right until a concurrent decision moves the request out of that status between a
  GET and a POST (or even the GET itself, if reached from a stale card) — that's supposed to be
  A13's clean "Someone else already decided this" alert, not a blank not-found page.
  `request_approve`/`request_reject`/`request_reconsideration_decide` all changed their early
  guard to: `request_row is None` → 404 (truly missing); wrong status → `_decision_error_redirect`
  (a `messages.error` + redirect to the detail page). Caught by
  `test_concurrent_decision_shows_clean_alert` (expected 404, got a real one — the guard itself
  was the bug, not the service layer, which had already refused correctly).
- **`_decision_error_redirect` doesn't try to parse `ValueError`'s message string for the exact
  `Refusal` code.** `ham.requests.states.check_transition` raises a plain
  `ValueError(f"... refused: {decision.refusal}")` — decision commands don't structure this as
  a typed exception the view layer could safely pattern-match. Re-fetching the request and
  comparing its *current* status to what this sheet expected is enough to tell "someone else
  decided while you were looking" from "a genuine validation error" without depending on string
  parsing; both paths still land on an honest, kept-nothing-changed message.
- **Known simplifications, handed back rather than built** (design-system/screens/approvals.md
  §§34/39 called for more than this slice built; noted inline in `shell.css`'s own block
  comment too):
  - No real `role="dialog"` right-anchored side-sheet frame at ≥1024 (C§39). Every sheet here
    reuses the step-2 `.sheet.sheet--fullscreen` + `{% block bottom_nav %}{% endblock %}`
    pattern (`request_phone_check.html`'s precedent) at *every* width, not just <768.
  - No duplicate decision-pair copy in a separate sticky bottom action bar (C§34). The Decision
    card carries its own buttons at every width and is itself `position: sticky` at ≥1024 (one
    copy of each button, not two — satisfies C§33's "the card must work alone" without the a11y
    bookkeeping a hidden duplicate would need).
  - The A3 "Replace your message with the suggested one?" inline confirm row (C§10) was
    simplified to "changing the reason always refills the suggested wording" (a plain
    `<script>` listener, no confirm dialog) — the field starts empty, so there's rarely
    anything real to lose on the first choice, and re-choosing a reason after editing is an
    edge case this slice didn't build a confirm step for.
  - List rows don't carry the "Question open · 2 days" (A7) marker — `RequestListRow`
    (`ham.requests.queries`, not owned by this slice) has no field for it; adding one would mean
    editing a shared dataclass other slices' tests also assert on. The marker/state is instead
    fully covered on the request detail page's own Decision card and the L16 Q&A thread.
  - A11 "Tell by phone" doesn't yet reuse `RECONSIDERATION_NOTE_MAX_CHARS`-style copy for its own
    script text beyond the fixed approve/decline sentences already in the template.
- **Concurrency test gotcha:** to prove "someone else decided first" from the *view* layer (not
  just the service layer, already covered by S3.2's own tests), call the losing decision
  through the Django test client (`client.post(...)`) but make the *winning* decision by calling
  `approve_request`/`reject_request` directly with a second actor's `ActorContext` first — no
  threads needed, since the row lock only matters within one call; sequencing the "other
  decider's" call before the client's `post()` reproduces the same `WRONG_STATE`-driven refusal
  a true race would, deterministically.
- **Playwright async-context gotcha (new one, not in the step-2 list):** any Django ORM/service
  call made *after* entering `with sync_playwright() as p:` raises
  `SynchronousOnlyOperation` (playwright's sync API runs its own event loop on the test's
  thread) — create every fixture row *before* opening the `sync_playwright()` block, never
  mid-test between page actions (e.g. to seed a second request for a later step in the same
  flow).
- **Full-page Playwright screenshots misplace `position: sticky` elements.** A `full_page=True`
  screenshot of a sheet with a sticky `.action-bar` (Cancel/Primary) rendered the bar in the
  middle of the captured image, not at the page's visual bottom — a known Playwright/Chromium
  full-page-screenshot quirk with sticky positioning, not a real layout bug (the same page
  behaves correctly in a real scrolled viewport, confirmed by the interactive Playwright flow
  test clicking the same buttons without incident). Didn't chase a workaround (e.g. per-viewport
  non-full-page screenshots) given the time budget; flagged here rather than "fixed" by
  guessing.
- `RULES.approvals.DECISION_UNDO_WINDOW` (30 min) and `RECONSIDERATION_REQUEST_WINDOW` (14
  days, Q-155/Q-174 final) are only ever read through `ham.rules`/`ham.requests.states` helpers
  (`decision_is_undoable`, `reconsideration_deadline`) from the service layer already wired by
  S3.2 — this slice never re-implements the arithmetic, only renders what the service/query
  layer already computed (`Approval.effective_at`, `AssistanceRequest.reconsideration_deadline_at`).

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

## Step 2 (Intake) fix round FIX-F1 (final visual pass, step2-ui-visual-qa.md / -ux-usability.md
"Re-check at 90f28d8")
- **B1 (sticky action bar clipped at 200% text / 195px):** `.action-bar { container-type:
  inline-size }` + `@container (max-width: 22em) { .action-bar__inner { flex-direction:
  column } }`, with `flex-wrap: wrap` on `.action-bar__inner` itself as the no-container-query
  fallback. The earlier "fixed" commit (FIX-C) never actually added this — always verify a
  claimed fix by reading the CSS diff, not the commit message.
- **N3 (the 200%-text proof script never enlarged anything):** `page.add_init_script(...)`
  runs before `<html>` exists, so `document.documentElement.style.fontSize = ...` at the top
  level throws and is silently swallowed by Playwright — wrap it in `document
  .addEventListener('DOMContentLoaded', () => { ... })`. Proof: assert
  `getComputedStyle(document.documentElement).fontSize === '32px'` after navigation, not just
  that the screenshot "looks" bigger — compare the regenerated PNG's height to a same-page
  non-200% screenshot (a real fix makes a `full_page` screenshot 2-3x taller from wrapped
  text/stacked rows).
- **N1 (leadership filter bar invisible at >=768):** don't rely on `.filter-bar-sheet:not(
  [open]) .filter-bar { display: flex }` to override a closed `<details>` — Chromium 131+
  hides closed `<details>` content through its `::details-content` slot in a way `display`
  can't reach, so `checkVisibility()` stays false even though the element "looks" laid out
  (76px box, per the QA report). Fix: render the `<details open>` server-side always (so it
  works with JS off and at every width), then a small inline script removes the `open`
  attribute on mobile viewports only (`matchMedia("(max-width: 767px)")`) to restore the
  "starts collapsed" behaviour — the opposite direction from the old (broken) "closed by
  default, JS/CSS opens it at desktop" approach.
- **N2 (wizard aside stretching row 1, ~130px dead space above the h1 at >=1280):**
  `.wizard-aside { grid-row: 1 / -1 }` inside a grid with no explicit `grid-template-rows`
  doesn't reliably span "all the rows the other column needs" — `-1` doesn't resolve the way
  you'd expect without an explicit row template. Fixed *without* touching any per-step
  template (several, e.g. r2_need.html, were a parallel fix's file-ownership) by making it a
  pure CSS change on the shared `.public-card:has(> .wizard-aside)` selector: `row-gap: 0`
  (so the aside spanning multiple auto rows doesn't also inherit a full `gap` between every
  column-1 child) + `.wizard-aside { grid-row: 1 / span 99 }` (spans comfortably past any
  realistic number of rows instead of relying on `-1`). A `.wizard-main` wrapper div was the
  UI designer's first suggestion but would have required editing every per-step template
  (including ones this fix round didn't own) and would have silently broken the `:has(>
  .wizard-aside)` selector for any template that still nested the aside include one level
  deeper — the CSS-only fix has neither problem. Proved with a Playwright test measuring
  `h1.getBoundingClientRect().top - .public-card.getBoundingClientRect().top` before/after.
- **N4 (`scrollable-region-focusable`, axe serious):** `tabindex="0"` on `.split-detail`
  (it already had `role="region"` + `aria-label`) — axe wants a scrollable region to be
  reachable by keyboard even with no focusable content inside it.
- **N-M2/M10 (L9 primary button hidden behind the fixed bottom nav at <1024):** gave
  `base.html`'s bottom nav its own `{% block bottom_nav %}` (default: the real nav) so a
  full-screen-sheet template (`request_phone_check.html`) can override it to nothing —
  simpler than trying to offset one sticky bar around another with `calc()` and safe-area
  insets, and it's the only page in this slice that's a true full-screen sheet. Proved with
  `document.elementFromPoint()` at the primary button's center, comparing against an
  `element_handle()` (not `document.querySelector('button')` again inside `page.evaluate` —
  that can resolve to a *different* button on a page with more than one).
- **N5 (urgent banner squeezed to ~170px text column at 390):** the bug wasn't really "flex: 1
  shrinks it" — it was that `min-width: var(--ham-size-target-min)` resolves to `48px` (a
  tap-target token, not a text-readability one); the `, 200px` in the old rule was a CSS `var()`
  *fallback* that never applied because the variable **is** defined. `flex: 1 1 16em; min-width:
  0` fixed it. Wrapped the two banner actions (`<a>` + `<form>`) in one `<span
  class="urgent-banner__actions">` so they move to their own row as a unit instead of each
  wrapping independently.
- **Home urgent-card cap:** `AttentionCard`/`AttentionItem` still don't carry enough shape for
  a "which card is first" flag (see FIX-D's note above) — solved by having the *view*
  (`ham.web.views.home`) compute `first_urgent_kind` (the first urgent+non-muted item's
  `.kind`) once and pass it as a separate context var, rather than changing the shared
  dataclass. `ham.requests.attention.MAX_URGENT_CARDS` (module constant, not `ham.rules` — a
  display cap isn't a business rule) folds anything past 3 individual urgent cards into one
  "N more urgent" card.
- **Icons:** `icons.svg` had no `key-round`/`building`/`building-2`/`caravan`/`dog`/
  `droplets`/`zap`/`bug`/`circle-ellipsis`/`file-x` before this round (R3/R4 choice-card icons
  + the R9 rejected-upload-tile icon, all named exactly per design-system/screens/intake.md).
  R2's icons (also specified there) were **not** added — r2_need.html was a parallel fix's
  file-ownership this round.
- **`get_item` template filter (`ham/web/templatetags/web_extras.py`) now humanizes an
  unknown key** (`"yard_outdoor"` -> `"Yard outdoor"`) instead of returning the raw code
  verbatim, for any label-map lookup app-wide (visual QA minor: pre-fix seed rows with a
  retired code showed the snake_case code). New `media_status_label` filter (same file) for
  the gallery's fallback chip, backed by `ham.media.models.STATUS_CHOICES`.
- **Gallery (`_request_media_gallery.html`) is its own file, not part of
  `_request_detail.html`** — the wave-brief's exclusion list only named `_request_detail.html`
  for the parallel fix, so the gallery partial (viewer `target="_blank"` removal, one shared
  `role="status"` region instead of one per processing chip, fallback status label) was fair
  game. `media_gallery_for`'s query only ever returns `ready`/`processing`/`uploaded`/
  `rejected+processing_unavailable` items, so the template's final `{% else %}` fallback
  branch is legitimately unreachable through the real service today — tested by rendering the
  partial directly with `render_to_string` and a synthetic dataclass item instead of driving
  the full view (that also sidesteps needing a real request/media fixture for a defensive-code
  path).
- **Upload picker layout (`data-icons-url`):** `frontend/src/upload.ts`'s `addRejectedTile`
  needed an icon (`file-x`), but the module has no way to know the *hashed* static URL for
  `icons.svg` (whitenoise may rename it) — passed it through as a `data-icons-url` attribute
  on the same `data-upload-root` div that already carries `data-reserve-url`, read once in the
  constructor, not a hardcoded path in the TS module.
- **Proof-test discipline this round:** for every item, reverted just that one change (CSS
  block, template line, or an `origin/feature/step-2-intake:<path>` `git show` dump for a
  whole file) via a plain file copy/restore — never `git stash` on a shared worktree stash
  stack — reran the new test to confirm it failed, then restored the fix and reran to confirm
  it passed. Caught two cases where a first-draft test *didn't* actually fail pre-fix (N5's
  first "banner height < 140px" threshold, N1's "processing" count of 1 with only one item) —
  worth budgeting time for this "does it actually fail" step, not just writing an
  assertion that looks plausible.

## Step 2 (Intake) fix round FIX-H (final visual pass, step2-ui-visual-qa.md "Final re-check
   at f1d4fb9")
- **N6 (Back/Start over drops out of the sticky bar under `@container(max-width:22em)`):** the
  in-bar Back/Start-over button gets an `.action-bar__back` class and is hidden by that
  container query; its "in-flow" twin is a plain `<p class="wizard-back-link"><a>...</a></p>`
  (or a `.link-button` for R2's Start-over, since that's a same-page confirm-submit, not a
  link) placed as a sibling *before* `.action-bar`, inside the same `<form>` — never inside
  `.action-bar` itself, or it would still add to the sticky band's own height. The toggle needs
  its own size container: `form:has(> .action-bar) { container-type: inline-size; }` — the link
  isn't a descendant of `.action-bar` (which already has its own, separate `container-type` for
  the primary/ghost stacking rule), so it can't react to that container's query. Two different
  containers (form's un-bled width vs. the bar's own full-bleed width) measuring "the same"
  22em threshold slightly differently was a known simplification, not a bug — confirmed they
  agree at every width this actually gets tested at (390+200% text, 195px).
- **N7 (mid-word breaks in icon choice-cards) has two independent causes, not one:**
  1. `overflow-wrap: anywhere` on `.choice-card` (which also shrinks a flex item's min-content
     contribution, letting it collapse arbitrarily small) became `break-word` + `hyphens: auto`
     (`lang="en"` was already on both `base.html`/`base_public.html`) so a label breaks only at
     real word/hyphenation boundaries, not anywhere.
  2. That alone *reintroduced text overflowing past the card* (a real regression, caught by a
     test only after writing it): `break-word`, unlike `anywhere`, does **not** shrink a flex
     item's automatic min-content size — the label `<span>`'s default `min-width: auto` kept it
     sized to its *unbroken* content width, so the flex row just overflowed instead of
     wrapping. Fix: `.choice-card > span:last-child { min-width: 0; }`, so the label can
     actually shrink to the space the icon/radio leave, and only then does break-word/hyphens
     get a chance to wrap it.
  3. Icon-bearing grids (`.choice-grid:has(.choice-card__icon)`) also got a wider minimum
     column (15em, vs. 10.5em for icon-less grids) — deliberately **1 column at 390, 2 columns
     in the 640px wizard main column at >=1280** for icon cards. This is an intentional
     regression against the old B3 test (`tests/e2e/test_fix_f1_choice_grid.py`), which
     asserted the *old* narrower grid was 2 columns at 390 — updated it to assert 1 column at
     390 / 2 at 1280 instead of deleting the coverage.
  4. **Proof-test gotcha:** neither "does the word appear intact in `innerText`" nor "does the
     label's own `scrollWidth <= clientWidth`" actually detects a mid-word wrap — the DOM text
     node is never split, and a wrapped-but-not-overflowing box passes both checks. The only
     check that actually catches it is geometric: `document.createRange()` over just that
     word's substring, then `range.getClientRects().length` — more than 1 means the word itself
     painted across more than one line (raw split or hyphenated), regardless of whether the box
     around it overflowed.
- **M2 (short-page bar, R8/R11b/R12) is a stretch-and-push-to-bottom trick, not `min-height:
  100dvh` alone:** `min-height` on the card doesn't move a normal-flow, non-sticky-triggered
  element to the bottom of a taller-than-content box by itself. Below 1024 (`.action-bar` is
  already `position: static` at >=1024, so this doesn't apply there):
  `.public-shell__content:has(.action-bar) { align-items: stretch }` (was `flex-start`) lets
  `.public-card` fill the available height; `.public-card:has(.action-bar) { display:flex;
  flex-direction:column }` plus (for form-wrapped bars) `.public-card > form:has(.action-bar)
  { flex:1; display:flex; flex-direction:column }` propagates that height down to whichever box
  directly wraps the bar; `.public-card:has(.action-bar) .action-bar { margin-top: auto }`
  (scoped to <1024 only — doesn't touch the desktop static layout) is what actually pushes it
  to the bottom. On a page whose real content already exceeds the available height, the free
  space is zero and this is a no-op (bar just follows the content as before, same as pre-fix).
  Every existing public-card+action-bar template (R2-R6, R8, R9, R11b, R12, phone-check) uses
  the same two building blocks (card, and optionally a wrapping `<form>`) so this needed zero
  template changes — pure `shell.css`.
- **M2 (wizard aside before the bar):** moved each step's `{% include "_wizard_aside.html" %}`
  from after `</form>` to right after the intro copy, before `<form>` (R1, R2, R4, R5, R9) — a
  direct child either way, so the >=1280 `.public-card:has(> .wizard-aside)` grid (explicit
  `grid-column`/`grid-row` on every child) is unaffected by DOM order. R3's aside is a special
  case: it repeats the page's own intro line ("Filling this in for someone else?..."), so
  instead of moving it, `_wizard_aside.html` grew an `aside_repeats_intro` context var (passed
  via `{% include ... with aside_repeats_intro=True %}` **from the template**, not the view —
  `views_requester.py` is a parallel fix's file this round) that adds a
  `wizard-aside--repeats-intro` modifier class, hidden below 1280 only (still in the DOM, still
  shows in the >=1280 side column, a different-enough reading context that the repeat is fine
  there).
- **M3 (R2 category icons):** `ham.requests.models.NeedCategory`'s enum values (not the old,
  now-deleted `ham.requester_portal.choices` copy) map to icons inline in `r2_need.html`, same
  `{% if value == ... %}` chain pattern as R3/R4's icon selection. Added `droplet`/`plug-zap`/
  `door-closed`/`layers`/`accessibility`/`paint-roller`/`trees` to `icons.svg` (house/circle-help
  already existed). New `.choice-card--full { grid-column: 1 / -1 }` modifier keeps "Something
  else or not sure" full width and last, inside the same grid as the other 8 cards (not a
  separate element outside the grid, unlike R4's "None known" exclusion card).
- **Polish, worth remembering:**
  - A formatted phone number is short/bounded, unlike the arbitrary long values
    `.u-wrap-anywhere` guards against — new `.u-nowrap { white-space: nowrap }` utility for
    those (R7N's phone line).
  - "Waiting under 1 h" (`ham.requests.attention._waiting_words`/`_oldest_waiting_words`) is a
    plain Python string, not a template — the non-breaking-space fix
    (`f"waiting {round(hours)} h"`) lives there, not as CSS, since CSS `white-space:nowrap`
    on the whole title would also stop a long title from wrapping at all.
  - `.upload-tile__remove`: shrunk the *visible* circle to 32px (was a 48px solid circle
    nearly reaching a small thumb's centre) while keeping a real 48px tap target via a
    `::before` pseudo-element with a negative `inset` — never shrink the actual accessible
    target size to fix a visual-only complaint.
  - The L9 "What to say" disclosure chevron/stray-glyph/padding items in the last QA re-check
    turned out to already be fixed on this branch (verified by rendering it — `.disclosure
    summary::marker { content: ""; display: none }` plus `display: flex` on the summary, from
    an earlier round, does suppress the native marker in Chromium 141) — re-verify visually
    before assuming a stale QA note still applies; don't "fix" something that isn't broken.
  - `git checkout <old-commit> -- <paths>` (restore just the touched files to the prior commit,
    run the new tests, then `git checkout HEAD -- <paths>` to restore) is a clean way to get a
    real fail-before/pass-after proof across *many* files at once in one shot, instead of
    reverting one CSS rule at a time — as long as you commit your in-progress work first so
    `HEAD`/`HEAD~1` are meaningful anchors, and restore before continuing.

## Step 3 (Approvals), S3.7: requester screens R13-R19
- **Files:** views/urls stay in the existing `ham/web/views_requester.py` (two new view
  functions: `request_help_question_answer`, `request_help_reconsider`) and the new, previously
  empty `ham/web/urls_requester_approvals.py` (S3.0's URL-name contract, don't invent names —
  `docs/architecture/approvals-contracts.md` §8 is the source of truth). Templates:
  `r10_secure_page.html` grew the step-3 cards in place (no new template for R13/R14/R15/R17/
  R18 — they're all states of the one R10 page); `r16_reconsider.html` is the one genuinely new
  page. CSS: appended under a "Step 3 requester (S3.7)" banner at the end of `shell.css`.
- **`ham.requester_portal.page.secure_page_data`/`projection` are S3.4's contract, but had two
  real gaps this slice had to fix (both are legitimate contract fixes, not workarounds) since
  S3.7 is the *only* consumer:**
  1. `_status_card`'s step-1/2 fallback branch called `projection.status_wording(status)`
     without `cancel_reason` — silently dropped the CANCELLED reason line the pre-existing view
     computed by hand. Threaded `cancel_reason`/`has_open_question` kwargs through
     `secure_page_data` → `_status_card` instead (also adds the "Awaiting Approval + question
     open" row's one-line next-step, `projection.AWAITING_APPROVAL_QUESTION_NEXT_STEP`).
  2. `SecurePageData` had nothing for R17's "What you told us" (the `Reconsideration.
     requester_note`/`requested_at`) or R18b/c's footer access-until date — added
     `reconsideration_note`/`reconsideration_requested_at`/`access_ends_at` fields, the last via
     `ham.requester_portal.validity.normal_access_ends_at` (already existed, just not wired to
     this dataclass).
- **`page_data.reconsider` is `None` whenever the *current* status isn't an open rejection** —
  including `RECONSIDERATION_PENDING`, which is exactly the "already asked" state a stale R16
  page needs to detect. Don't gate "already requested" on `reconsider.already_requested`; query
  `Reconsideration.objects.filter(request_id=...).exists()` directly in the view for that
  specific check (R19 "already asked, another tab -> lands on R17 with no error").
- **A withdrawn (auto-closed) question is invisible to `page.secure_page_data`** — S3.4's
  `_question_cards` skips any `RequestQuestion` with `closed_at` set entirely (by design: a
  closed question is never shown as if still open). R13's "we don't need this answer anymore"
  soft notice therefore can't be rendered *inside* the `open_questions` loop (the row won't be
  in it by the time the redirect's `?withdrawn_question=<id>` param is read) — render it as its
  own standalone card, keyed only by the id the redirect query param carried, outside that loop.
- **CSS `display` on a class beats the UA `[hidden]` rule at equal specificity, regardless of
  source order** (same family of bug as FIX-C's `.filter-bar-sheet` note above, different
  direction this time): `.form-field__offline-reason { display: flex; ... }` made the "You're
  offline" reason line visible on every normal page load, `hidden` attribute or not, because an
  author `display` declaration always wins over the UA stylesheet's own `[hidden] { display:
  none }`. Fix: scope the rule to `:not([hidden])`. Caught by a Playwright test with a
  `page.wait_for_timeout(200)` before asserting `is_visible() is False` — `wait_for_selector`
  on server-rendered text proves nothing about whether the deferred client script has run yet.
- **Never seed a form's initial offline-detection state from `navigator.onLine` on load** — it
  can read `false` in a sandboxed/headless runner even though the page just finished loading
  over real HTTP a moment ago (this box's Playwright environment does exactly that). A page
  that finished loading is online by definition; only wire the *live* `online`/`offline` window
  events, seed the initial UI state as "online" unconditionally.
- **A date inside `<time>` must be *only* the date, never the whole sentence.** Putting
  `{{ reconsider.ask_line }}` ("You can ask until Thu, Oct 8.") inside `<time>` with
  `white-space: nowrap` forced the entire sentence onto one unbreakable line — a real horizontal
  -scroll bug at 390+200% text (caught by the always-on Playwright no-sideways-scroll test, not
  by eyeballing a screenshot). Split it in the template: plain text "You can ask until " +
  `<time>{{ date|date:'D, M j' }}</time>` + ".", so only the short date itself is nowrap and the
  sentence around it wraps normally. Also don't make the wrapping `<p>` itself `display: flex`
  for a "icon + text" row that needs to wrap — flex children don't wrap by default; keep the
  icon `vertical-align`-inline instead of flexing the whole paragraph.
- **`can_add_photos` (carried over from step 2) only ever excluded `CANCELLED`** — once step 3
  added APPROVED/REJECTED/RECONSIDERATION_PENDING statuses reachable from the same page, the
  "Add photos" card kept showing on a rejected-but-open request with no batch row (caught by
  visual QA screenshot, not a unit test at first — worth eyeballing every new status's
  screenshot, not just asserting individual strings appear). Fixed by excluding all three
  step-3 "nothing to add photos toward" statuses *unless* a leader has explicitly reopened a
  batch (`batch.is_open` on a real reopened-kind batch overrides the status exclusion).
- **One "Things we need from you" heading, not two.** The pre-existing photo-upload card had
  its own `<h2>Things we need from you</h2>` separate from R13's question-card section's own
  heading; when both apply on the same page (an open question + open uploads) they rendered as
  two adjacent identical headings. Merged into one heading above both blocks, with the open-
  question count only shown when there are open questions (`{% if open_questions %} (N){% endif
  %}`).
- **Text-limit constants for a still-`NotImplementedError`-stubbed sibling service:** when the
  service you're calling (`ham.requests.services_decisions.request_reconsideration`, S3.2's
  file) is still a stub, don't add a new constant to its module — define the UI-side limit
  locally in the view (`RECONSIDERATION_NOTE_MAX_LENGTH` in `views_requester.py`, same "form
  validation constant, not a rules-module entry" reasoning as `services_questions.
  ANSWER_MAX_LENGTH`) so your slice doesn't collide with the parallel slice's own file. Once
  S3.2 landed for real, its actual signature/exceptions (raises `ValueError` on a refused
  `check_transition`, same shape as every other decision command) matched the contract doc
  exactly — no view changes were needed after the merge, only dropping the `xfail` marker.
- **`xfail(strict=True)` for "my view already calls a real contract signature, the callee just
  isn't implemented yet" is the right tool** (not skip, not a TODO comment) — it fails loudly if
  the stub starts silently returning something instead of raising, and disappears cleanly (one
  line removed, test starts passing for real) the moment the parallel slice merges.

## Step 3 fix pass FIX-3B (step3-ui-visual-qa.md / step3-ux-usability.md)
- **Files:** `shell.css` (B1 urgent banner container query + wrapping actions; B2 sheet
  action-bar flex-column pin + reduced sheet inset padding; B3 `.btn { overflow-wrap: normal;
  word-break: normal }`; B4/M1 `.request-detail__grid` two-column container query at 42em with
  `.request-detail__side`/`__main`), `_urgent_banner.html`, `base.html` (new `{% block
  urgent_banner %}`/`{% block messages %}` so sheets can opt out), `_request_detail.html`
  (side/main split, `.urgency-block` for M13, header-actions duplicated once for >=1024 and
  once after the Decision card for <1024, per UX M15), `_decision_card.html` (B3: buttons as
  direct children of the alert body, not inside `<p>`), `requests_list.html` (M3: drop
  `row.decision_chip`; M4: `row.line2_text`/`row.is_final`/`row.markers` all optional, render
  if present else fall back — FIX-3A hasn't added them yet), `home.html` (M12/m18/m19: "N
  things need you" greeting, "Review" not "Open" with an aria-label, `item.meta` optional
  line, softer empty-state copy), `presentation.py` (**the one `ham/requests` file this slice
  may touch**: `STATUS_TONES`/`STATUS_ICONS` — Rejected is now `neutral`/`circle-x` (never
  red), Approved `info`/`badge-check` (new icon, hand-drawn to match), Reconsideration pending
  `attention`/`rotate-ccw`), 12 sheet templates (B2 Cancel→`action-bar__back` + in-flow
  `.wizard-back-link` twin; the request+category header line via a new template filter), and
  `requester/r10_secure_page.html` (m21/m22: hide the red Urgent chip and the "photos"/"close
  your request" lines once declined — `row.status == "REJECTED"` gates both; the photo line
  only shows for `APPROVED` now, not the old "APPROVED or REJECTED or RECONSIDERATION_PENDING"
  — **check this against a real existing test before changing it**, see gotcha below).
- **New template filter instead of new view context, for a cross-cutting sheet-header need:**
  M3's "the request + category line in every sheet header" (C§39, needed on 10+ sheets whose
  views are FIX-3A's/parallel-owned `views_requests.py`) was done as `ham.web.templatetags.
  web_extras.need_category_label` (`{{ request_row.need_category|need_category_label }}`),
  not a new context key threaded through every view function. `request_row.need_category` (the
  raw enum value) is already in every sheet's context; the filter does the
  `ham.requests.presentation.NEED_CATEGORY_LABELS` lookup at render time. Far less invasive
  than editing 10 view functions in a file two other slices are actively editing in parallel.
- **B1's "no sticky banner on a sheet" is a `{% block urgent_banner %}{% endblock %}`
  override, one per sheet template**, mirroring the pre-existing `{% block bottom_nav
  %}{% endblock %}` pattern those same 12 sheets already had. `base.html` wraps the banner
  include in the block so sheets that don't override it are unaffected.
- **The "duplicate error messages" usability fix is the same block-override trick**:
  `base.html` wraps its `{% if messages %}<ul>...` in `{% block messages %}{% endblock %}`;
  the 5 sheets that already render `messages` inline themselves (`request_category_change`,
  `request_question_ask`, `request_question_record_answer`, `request_reconsideration_decide`,
  `request_reject`) override it to empty so each message shows/announces exactly once.
- **B4/M1's two-column split is a container query on `.request-detail` itself
  (`container-type: inline-size`), gated at 42em, never a viewport media query** — this is
  what makes the split-view pane (`.split-detail`, narrower than the standalone page) and the
  standalone page each independently decide one- vs two-column based on their own real width,
  not the browser viewport. Proven with a Playwright test that scrolls `.split-detail` itself
  (`el.scrollTop = 400`) before measuring — the old bug (sticky card overlapping the "Earlier
  request found" alert) only reproduces after scroll; at initial paint the card and the alert
  are never near each other regardless of the bug.
- **Gotcha, hit twice this round: a `{# ... #}` comment spanning more than one physical line
  is never recognized as a Django comment tag at all (the tokenizer regex has no `DOTALL`) —
  it renders straight into the page as literal text.** Wrote several multi-line `{# #}`
  comments explaining a fix inline; one of them contained the literal string "Not approved"
  and broke a same-round Playwright test that grepped the rendered HTML for exactly that
  phrase (false failure that looked like a real regression). `tests/web/
  test_fix_d_no_leaking_template_comments.py` (FIX-C/FIX-D era) already scans for this, but a
  brand-new template file/section can still trip it before that scan's next run — always use
  `{% comment %}...{% endcomment %}` for anything that doesn't fit one physical line, on
  reflex, not just when a scanner catches it.
- **Gotcha: the repo's hex-color hard-coding scanner (`#[0-9a-fA-F]{3}\b` etc.) also matches
  a literal `#` followed by 3+ hex-looking characters *inside an English sentence in a
  template comment*** — a comment reading `...approve HAM #009?...` tripped it (`#009` reads
  as a 3-digit hex color + word boundary). Avoid literal `#NNN`-shaped HAM-number examples in
  comment prose; say "a HAM number" or use a non-hex-looking placeholder instead.
- **Gotcha: `page.locator(sel).count()` counts DOM elements regardless of `display: none`** —
  a B2 proof test asserting "only the primary button is in the action bar under 22em" first
  failed against the *fixed* code too, because the hidden `.action-bar__back` (correctly
  `display: none`) was still in the DOM and still matched the plain selector. Use `:visible`
  (`page.locator(".action-bar .btn:visible")`) whenever a test's assertion is really about
  what's visible, not what's present in markup.
- **Gotcha: two existing tests encoded the *pre-fix* copy/behavior as their expected value**
  (`test_fix_d_attention_cards.py`'s `"Open" in html`, `test_shell_pages.py`'s `"Your to-do
  list will appear here"`, and `test_requester_approvals_screens.py`'s `assert "Photo uploads
  are closed for now" in content` on a REJECTED request) and had to be updated in the same
  commit as the UX-review-mandated copy change (m19/m18/m22) — a full-suite run after any
  wording change is the only reliable way to catch these; grepping for the old string first
  would have missed the `test_requester_approvals_screens.py` one since it wasn't a "does the
  word Open appear" test that's obviously about the same copy.
- **`git checkout <sha> -- <paths>` against the shared branch base (`7f43fb4`, this round's
  `origin/feature/step-3-approvals` tip) is the reliable fail-before anchor, not
  `HEAD~1`/a same-session WIP checkpoint** — a WIP checkpoint commit made *after* a fix was
  already applied is not "before" that fix; checking it out to "prove" a regression silently
  proves nothing (the test still passes because the checkpoint already has the fix). Anchor
  fail-before proofs on the real pre-fix commit the branch started from.
- **Known simplification, handed back rather than built:** M4's per-row step-3 markers
  ("Undo until", "Question open · 2 days", "Yours"/"Goes to Pastor X", etc.) and the tab-
  appropriate line-2 text need new `RequestListRow` fields FIX-3A's `ham/requests/queries.py`
  doesn't have yet (out of this slice's file ownership) — `requests_list.html` reads
  `row.line2_text`/`row.is_final`/`row.markers` if present and falls back to the old
  age-only line 2 otherwise, so it activates automatically once FIX-3A adds them, no further
  template change needed. Also handed back: M6/M7/M9 (decline preview WYSIWYG, dual-role route
  preselect, hard-coded rule values/names) — explicitly FIX-3A's per the wave brief's
  file-ownership split, even though they live in files this slice otherwise owns.

## Step 3 fix pass FIX-3D (step3-ui-visual-qa.md "Re-check at 089473e"), round 2
- **CSS specificity beats source order for `@container`/`@media` overrides.** Adding
  `container-type: inline-size` to a wider ancestor (`.sheet--fullscreen`, for N1's h1 fix)
  does make it the "nearest container" for descendants that have no closer container (e.g. a
  standalone `.choice-card--statement` with no `.choice-grid` around it) — so a *later*
  `@container` rule scoped to plain `.choice-card` *does* start applying to it for free. But if
  an *earlier* rule used a more specific selector for the same property (`.sheet--fullscreen
  .choice-card { gap: ... }`, two classes) than your new one (`.choice-card { gap: ... }`, one
  class), the earlier-but-more-specific rule still wins regardless of source order — match or
  exceed the existing selector's specificity, not just add a rule after it. Caught by measuring
  the *computed* `gap`/`font-size` via Playwright (not by reading the CSS and assuming it
  applies).
- **M10 residue's real fix needed three numbers shrunk together, not one.** "available"/
  "reconsider"/"Something" (9-10 letters) still broke mid-word at 195px even after the standard
  22em choice-card padding trim, because those three sheets use standalone
  `.choice-card--statement` (no `.choice-grid`, so it never got the icon-drop rule at all) or a
  no-icon single-column category grid — the fixed 24px checkbox/radio + `body-lg` (18px) font
  left only ~74px for the label, and even `break-word` will still split a word wider than its
  available box. Fixed by shrinking, together, only inside `@container (max-width: 22em)` on
  `.sheet--fullscreen .choice-card`: font down to `type-small` (13px), the input to 18px, gap to
  `space-1` (4px), padding-inline to `space-1`. Verify with the geometric per-word `Range
  .getClientRects().length` check (same one B3 introduced), not just "does it fit visually" —
  the first two shrink attempts (16px font/20px input/space-2 gap, then still 16px font) each
  *looked* like enough headroom by arithmetic but still measured 2 line(s) for the word.
- **`position: sticky; bottom: 0` on the very last child of a flex column can appear "pinned"
  at the viewport bottom on first paint even with scrollY=0**, if its containing block (the
  `<form>`, once B2 wraps the whole sheet body in it) is taller than the viewport — sticky
  clamps the element so its bottom never exceeds the viewport's bottom edge *within the
  containing block's own extent*, which visually looks identical to "docked to the bottom of
  the screen" whether or not the rest of the document is short or long. Don't assert `bar.bottom
  >= documentHeight` (wrong — fails even on a correctly-fixed page whose content overflows one
  screen); assert `bar.bottom >= viewportHeight - epsilon` instead. Whenever a geometric sticky
  assertion is surprising, dump the raw `getBoundingClientRect()`/`scrollY`/computed `position`
  first rather than trusting the first plausible-looking assertion.
- **A submit button that only needs to POST a side-effect (e.g. "Show contact details") must
  get `formnovalidate`** once it's merged into the same `<form>` as other `required` fields
  (B2's A5/A11 single-form merge) — otherwise clicking it triggers the browser's native
  required-field validation on fields that have nothing to do with that button's action, and the
  click silently does nothing.
- **B2's "form wraps the whole sheet body" is judged relative to A2's own established pattern,
  not literally "every visible line."** A2/A3's `h1`/subtitle stay outside `<form>` (shell
  chrome); everything else (quote blocks, urgency text, consequence copy, the fields, the bar)
  goes inside. A2c/A2n/A2u had their intro `<figure>`/`<p>` sitting *before* `<form>` (same
  visual shape as A2's *passing* case) yet were still flagged — the residual bug wasn't really
  about which specific lines were outside the form, it was A5/A11 having a genuinely *separate*
  sibling `<form>` for "Show contact details" (see above) and U1 never having wrapped its
  consequence `<ul>`/deadline `<p>` in the first place. Fixed all of them the same way (move the
  intro content inside the one `<form>`) for consistency, but the two real, different root
  causes are worth remembering next time a QA note says "form wraps only the bar."
- **`RequestListRow.is_final`/`.markers` are still unset in `ham.requests.queries`** as of this
  round (grep found zero assignments) even though `requests_list.html`'s "· Final" rendering
  (`{% if row.is_final %}`) has existed since FIX-3B — the template-side work for M3/M4 was
  already done a round ago and needs no further template change; only the backend field
  (blocked by this round's file-ownership split, `ham/requests/*` is FIX-3C's) is still missing.
  Don't re-"fix" the template when a QA note says a row marker is missing — check whether the
  template already reads the field first (`grep row.is_final` before touching
  `requests_list.html`).
- **M12's real per-request Home cards need `ham/requests/attention.py`** (`reconsideration_
  cards`/`pastor_certify_card`/`decision_phone_card` are all still single-aggregate-card
  builders, "Reconsideration for you (1)" not one card per request) — entirely inside
  `ham/requests/*`, blocked by this round's file-ownership split. What *is* fair game and owned
  by `ham.notifications` (a separate app, not `ham/requests/*`): the banner's own count/copy.
  Added `urgent_banner_count_for(ctx)` next to the existing `urgent_banner_for(ctx)` in
  `ham/notifications/services.py`, threaded through `ham.web.context_processors.shell` as
  `urgent_banner_count`, and `_urgent_banner.html` now says "N urgent requests need you · " (N>1
  only) and "Got it" (was "I've seen this", and dropped the always-`None` `acknowledge_label`
  dead branch). Updating this copy required also updating `tests/e2e/test_fix3b_urgent_banner
  .py`'s old `'button:has-text("I\'ve seen this")'` selector — grep every old string literal
  before a copy change, not just the ones your own new tests touch.
- **Proof-test discipline, reinforced:** every fix in this round was checked against
  `git checkout bcb1a61 -- <paths>` (`bcb1a61`, this round's real pre-fix branch tip) before
  trusting a "passes" result — caught two tests that looked correct on paper but actually passed
  even pre-fix (the first draft of the U1 bar-pinning Playwright geometry test, and the first
  draft of the N2 chip test using the Decision card's own status chip instead of the narrower L5
  duplicate-panel chip the QA screenshot actually showed the break on) — both had to be
  rewritten (U1 became a structural DOM-order assertion instead of a sticky-geometry one; N2
  moved to the L5 panel with a `RequestMatch` fixture) before they were real regression guards.
