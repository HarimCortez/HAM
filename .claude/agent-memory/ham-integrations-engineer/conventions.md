# ham-integrations-engineer — conventions and decisions from slice S4 (outbox + adapters)

## Repo layout (S4)
- `ham/outbox/` — `OutboxEvent`/`OutboxDelivery` models, `registry.py` (subscriber name ->
  handler(event) dict, `register`/`unregister`/`reset`/`is_registered`/`subscribers`),
  `api.py` (`emit()` — the exact public contract, see below), `validation.py` (PII payload
  guard), `dispatch.py` (the `outbox.dispatch_delivery` job: retry/backoff/dead-letter),
  `services.py` (`retry_delivery`, `subscriber_status_counts`, `recent_failures`).
- `ham/integrations/` — `channels.py` (`NotificationChannel` Protocol), `email/` (adapters,
  `send_transactional_email`, the `email` outbox subscriber + builder registry),
  `calendar.py`/`fitness.py`/`drive.py` (Protocol + no-op adapter + outbox subscriber per
  deferred system), `dev_logging.py` (dev-only subscriber), `apps.py` (`ready()` wires every
  subscriber into `ham.outbox.registry` — **only** place that does so).
- Both apps added to `INSTALLED_APPS` in `config/settings/base.py`, in dependency order
  (`ham.platform`, `ham.outbox`, `ham.integrations`, `ham.web`).

## `ham.outbox.api.emit` — exact public contract (S3a/domain code codes against this)
```python
from ham.outbox.api import emit
emit(event_type: str, *, aggregate_type: str, aggregate_id: uuid.UUID | str, payload: dict,
     schema_version: int = 1) -> None
```
- **Must** be called inside the caller's own `transaction.atomic()` — raises `RuntimeError`
  (checked via `transaction.get_connection().in_atomic_block`) if not. In a pytest-django test
  using the plain `django_db` mark, the test itself already opens an atomic block, so testing
  the "outside atomic" failure needs `@pytest.mark.django_db(transaction=True)`.
- Validates `payload` with `ham.outbox.validation.validate_payload` (raises `PayloadPIIError`,
  a `ValueError` subclass) **before** writing anything — rejects PII-shaped keys (email, phone,
  mobile, full_name/first_name/last_name/surname, address, street, city, state, zip, postal,
  dob, birth, ssn, circumstance — recursively, any depth) and PII-shaped string values (email
  or phone regex from `ham.platform.logging`), except values that parse as a UUID (so ids with
  numeric-looking hex runs don't false-positive against the phone regex).
- Writes one `OutboxEvent` + one pending `OutboxDelivery` **per currently-registered
  subscriber** (i.e. every domain event fans out to email/calendar/fitness/drive/dev_logging
  automatically — a new subscriber just registers itself, no `emit()` call site changes).
- Dispatch is deferred with `transaction.on_commit`, not called inline — so a rolled-back
  caller transaction leaves zero events/deliveries and enqueues nothing.

## Retry/backoff/dead-letter (`ham/outbox/dispatch.py`)
- One job, `outbox.dispatch_delivery(delivery_id)`, registered via `ham.jobs.job` (never import
  `procrastinate` outside `ham/jobs/`). Since Procrastinate's `Task.__call__` runs the
  underlying function body synchronously, tests call `dispatch_delivery(delivery_id=...)`
  directly (no worker needed) to simulate "the job ran now"; `Task.defer()` is the real
  enqueue path used by `emit()`/`retry_delivery()`.
- Backoff: `RULES.outbox.OUTBOX_BACKOFF_INITIAL * 2**(attempts-1)`, capped at
  `OUTBOX_BACKOFF_MAX`; dead-letters at `OUTBOX_MAX_ATTEMPTS` (read from `ham.rules.v1`, never
  a literal here).
- `last_error` is `ham.platform.logging.scrub()`-ed before saving (adapter exception text can
  otherwise echo back caller-supplied data).
- `retry_delivery(delivery_id)` (in `services.py`) is a **plain function, no permission check,
  no audit event** — its docstring says S3a/S5 must wrap it as `@command("outbox.retry")`.
  Does not reset `attempts`, so retrying an already-dead delivery that fails again dead-letters
  immediately (one-shot manual retry, not a reset of the automatic budget).

## Known landmine found in `ham.platform.ids.UUID7Field` (not fixed here — owned by S1/backend)
`UUID7Field.__init__` does `kwargs.setdefault("primary_key", True)`. Constructing it with
`primary_key=False` works at first, but Django's generic `Field.deconstruct()` omits
`primary_key` from its output when the *current* value equals the *base* `Field` class's
default (`False`) — which it does here. On any deconstruct+clone round-trip (migration
autodetector's `ModelState.from_model`, `field.clone()`), the field is reconstructed without
`primary_key` in kwargs, so `UUID7Field.__init__`'s own `setdefault` silently flips it back to
`True`. Net effect: **`UUID7Field(primary_key=False, ...)` is not safe** — it works when you
inspect the live model class, but breaks (produces a second primary key / makemigrations
writes `primary_key=True` anyway) the moment migrations are generated. Worked around in
`ham.outbox.models.OutboxEvent` by using a plain `models.UUIDField(default=uuid7,
editable=False, unique=True)` for the non-PK `id` column instead (`seq`, a `BigAutoField`, is
the real primary key there). Flagged to the architect/backend engineer for a real fix
(e.g. `UUID7Field` should only apply its `primary_key=True` default when the kwarg is *absent*
at the call site that matters, which it already tries to do — the bug is that Django's
deconstruct/clone cycle re-triggers that same absence).

## Email adapter (`ham.integrations.email`)
- `DjangoEmailChannel` (implements `NotificationChannel` Protocol structurally, no inheritance)
  sends via `django.core.mail.EmailMultiAlternatives` using whatever `EMAIL_BACKEND` is
  configured — dev: console, test: locmem, prod: `anymail.backends.<esp>.EmailBackend` named
  by `DJANGO_EMAIL_BACKEND` env var, with `ANYMAIL_SETTINGS_JSON` (a JSON blob) providing
  ESP-specific settings (`config/settings/base.py`: `ANYMAIL = json.loads(env(...))`). No ESP
  is hard-coded anywhere — confirmed against django-anymail's docs (`message.tags = [...]` is
  read by any Anymail ESP backend when set on a plain `EmailMessage`/`EmailMultiAlternatives`;
  console/locmem ignore the extra attribute).
- Two entry points, per the task:
  (a) `ham.integrations.email.notifications.handle_email_event` — the `email` outbox
      subscriber. It looks up a per-`event_type` builder registered via
      `register_notification(event_type, builder)`; a builder gets only the `OutboxEvent` and
      must resolve the recipient/copy itself (never trust the payload to carry an address —
      it's PII-validated to reject that anyway). **No step-1 module registers one** (logged as
      `PRD-GAP Q-078`: the PRD doesn't specify this mechanism; it's this slice's proposed
      seam, not yet signed off).
  (b) `ham.integrations.email.service.send_transactional_email(*, to, subject, text_body,
      html_body=None, category)` — the one documented exception to "only via the outbox"
      (foundation.md §1), for S3b's sign-in codes/links. Enqueues an immediate
      `integrations.send_transactional_email` job (not through `ham.outbox` at all).

## Stub subscribers (`ham/integrations/{calendar,fitness,drive}.py`)
- Each has a `Protocol` (e.g. `CalendarAdapter`), a `NoOp*Adapter` no-op implementation, and an
  outbox-subscriber function. `calendar`'s subscriber logs at INFO (event type + ids only,
  never payload) per the explicit spec; `fitness`/`drive` log at DEBUG (same fields) since the
  spec only calls those "no-op" without requiring a log line — kept minimal but consistent.
- `dev_logging.py` is registered only when `settings.DEBUG` is true (never in test/prod).

## Import-linter (`pyproject.toml`)
- Extended the `layers` contract to `["ham.web", "ham.outbox", "ham.platform"]`.
- Added two `forbidden` contracts: "only ham.integrations imports anymail" and "domain modules
  never import ham.integrations directly" (`source_modules` currently `["ham.web",
  "ham.outbox", "ham.platform"]` — **when `ham.identity` lands (S3a/S3b) and calls
  `send_transactional_email`, add `ham.identity` to `source_modules` on both contracts AND add
  an `ignore_imports` entry for that one call site** rather than deleting the contract).
- `include_external_packages = true` had to be added to `[tool.importlinter]` — required
  whenever a contract's `forbidden_modules` names an external (non-`ham`) package like
  `anymail`.

## Testing
- `django_capture_on_commit_callbacks` (pytest-django fixture) is how to test
  `transaction.on_commit` behaviour without a real commit — works fine under the plain
  `django_db` mark (Django's `TestCase.captureOnCommitCallbacks` is designed for exactly this).
- A `fake_subscriber` fixture (`tests/outbox/conftest.py`) registers under a name that can't
  collide with the real ones and unregisters (not `registry.reset()`) in teardown, so the real
  `email`/`calendar`/`fitness`/`drive` subscribers (registered once by `IntegrationsConfig`
  at Django startup) keep working for every other test in the session. Because of this, `emit()`
  always creates deliveries for the real subscribers too — assert with set membership /
  `filter(subscriber=...)`, never an exact equality on the full delivery list.

## S2.6 — Intake notification builders (docs/handoff/wave-brief.md, docs/ux/intake.md §7)

Two new files, both registered from their app's own `ready()` (not `IntegrationsConfig`, the
step-1 email/calendar seam owner — step 2's domain modules resolve their own notification
content, same carve-out `ham.identity.notifications` already used):
- `ham/requester_portal/notifications.py` — requester email builders (E2/E2u "request
  received", E3 "new link", E5 "more photos asked", E6/E7 "closed before a decision"). The
  verification code email (E1) was already built by S2.3 (`ham.requester_portal.verification`,
  `send_transactional_email`, not the outbox) — nothing to add there.
- `ham/requests/notifications.py` — leadership email + in-app builders (L-E1 "waiting for
  review", L-E2 "urgent, needs a pastor", L-E3 "phone check needed"), plus a `RequestCancelled`
  in-app-only builder to Director/AD (intake.md §6's "who is notified" table, not itself in
  docs/ux/intake.md's E-row table).

Both added two `pyproject.toml` `ignore_imports` entries (`ham.requester_portal.notifications
-> ham.integrations.email.notifications`, `ham.requests.notifications -> `same`) — the
`ignore_imports` list itself already documented exactly this shape and where to add it
(intake-contracts.md §6, pyproject.toml's own comment).

**Recipients.** Never read `User`/`RoleAssignment` directly — always through
`ham.identity.services.notification_recipients(role_set) -> list[(user_id, email,
notify_email)]` (built by S2.5, already resolves active/non-disabled/non-revoked). Urgent
overrides (Q-123/Q-133) are implemented as "build the email list without checking
`notify_email` for the urgent-privileged role (pastors for RequestAwaitingApproval, Director/AD
for RequestSubmitted-as-NEEDS_PHONE_CHECK), otherwise filter on it" — never a rules-module
literal (there's no numeric threshold here, just a role-scoped override, so nothing belonged in
`ham.rules`).

**Coordination note, not silently resolved:** docs/ux/intake.md's E3 ("your link expired",
R11a) and E4 ("check on your request" result, R11b) are two different-copy emails in the UX
spec, but intake-contracts.md's route table sends both flows through the same
`requester_link.regenerate` action and the same `RequesterAccessLinkIssued(kind="regenerated")`
event — nothing in the payload tells the two origins apart, and adding a field to do so is a
new contract decision, not something I invented silently. One builder covers both, using E3's
wording; flagged in the file's own module docstring and in this slice's hand-back for the
coordinator.

**Decided NOT to build this slice (documented, not a silent gap):**
- `request.duplicates_flagged` gets no separate notification of its own — it's an audit event
  only; leaders see it via the request detail page's duplicate panel the moment they open an
  Awaiting Approval request. Documented in `ham/requests/notifications.py`'s module docstring.
- `RequestMediaStored` (first item of a reopened batch) → in-app to the batch's reopener (L-E4
  "New photos", intake-contracts.md's own notification table) was not built — it wasn't in this
  slice's task list, and it lives more naturally as `ham.media.notifications` (a new file,
  needing its own `ignore_imports` entry the pyproject.toml comment already anticipates). Left
  as a gap for whichever slice next touches `ham.media`.

**Test gotcha:** any test file under `tests/requester_portal/` that calls
`ham.requester_portal.services.issue_link`/`resolve_token`/etc. needs its own `autouse` fixture
re-registering the real `ham.requests.queries` lookups (see `test_submission_flow.py`'s
`_real_portal_lookups`, copied into `test_notifications.py`) — sibling test modules
(`test_links.py` and friends) reset the module-level lookup globals to `None` on teardown
rather than restoring them, so relying on `RequesterPortalConfig.ready()`'s startup
registration breaks depending on test run order. Passing in isolation but failing in the full
suite is the symptom.

**Test gotcha 2:** `ham.jobs.run_due_jobs_now()` only runs jobs that were already `todo` when
it started (one `SELECT` up front, no loop) — a job whose own `transaction.atomic()` commits
mid-run and triggers a new `transaction.on_commit` deferral (e.g. the duplicate-check job
emits `RequestAwaitingApproval`, whose outbox dispatch job is only enqueued once *that*
transaction commits) needs a second (or third/fourth) call to actually observe the end state
(e.g. a `Notification` row landing). Call it in a small loop, not once, when chaining more than
one hop.

## FIX-B (step-2 fix round, media security + requester email links)

Branch `fix-b` off `feature/step-2-intake`. Findings worked: security H4/M2/M3/M4/L1/L3, PRD
guardian M3/M7/N6/N9/N10/N11, N3/Q-149. Full list and rationale in the handback message; a few
reusable decisions worth keeping for next time:

- **The reverse-lookup pattern for "a lower layer needs to call a higher layer's function"**
  (not just "a higher layer needs the lower layer's data", which `ham.requester_portal`'s
  existing `register_request_facts_lookup`-style seam already covered): the higher layer
  defines the registration point **in the lower layer's own module** (`ham.requests.services.
  register_media_purge_hook`, a plain `_media_purge_hook: Any = None` global + setter), and
  registers its real implementation from its own `AppConfig.ready()` (`ham.media.apps.
  MediaConfig.ready()` calls `register_media_purge_hook(purge_all_for_request)`) — legal
  because the higher layer (`ham.media`) is always allowed to import the lower one
  (`ham.requests`), just not the reverse. Used for `ham.requests`'s spam purge
  (`purge_expired_request`) needing to delete `ham.media`'s storage objects before
  `request.delete()` cascades away the rows that pointed at them (M4).
- **`ObjectStore.presign_put`'s `max_bytes` param was a ceiling, not an exact size** (M2): a
  simple S3 PUT presign has no native max-size parameter, only an exact one — signing
  `ContentLength` makes SigV4 reject a PUT whose `Content-Length` header doesn't match
  exactly, so I renamed the param to `content_length` (breaking change to the `ObjectStore`
  Protocol, all three implementations — R2, local, and the dev-storage view's token payload
  — updated together) and pass the intent's already-validated `declared_bytes`, not the
  type's rules-module cap. `complete_upload`'s own `head()`-based re-check on completion
  still exists as defense in depth; `process_item` (the background worker) now does its own
  `head()`-based re-check too, before `get_object()`, since nothing guarantees the object at
  that key is still the same one `complete_upload` looked at.
- **A periodic sweeper needs its own rule for "how stuck is too stuck"** (M3): there was
  already `MEDIA_UPLOAD_INTENT_LIFETIME` in the rules module (defined, never read by
  anything) for a reservation that's never completed, but nothing covered an item stuck in
  `processing` because the worker that had it died mid-job — added `media.
  MEDIA_PROCESSING_TIMEOUT` (1 hour, an engineering value, not Q-numbered) for that second
  case. Bumped `RULES_VERSION` to `2026.09.28-6`; both this and the (pre-existing, dormant)
  intent lifetime are read by one new job, `media.sweep_stale_uploads` (`*/15 * * * *`),
  registered the same way as `media.retention_sweep`.
- **Two "reverse lookup" cross-app registries with the same shape now exist in this repo**:
  `ham.requester_portal.services`'s three (portal → requests) and `ham.requests.services.
  register_media_purge_hook` (requests → media, this fix round). If a third one shows up,
  it's probably worth a shared tiny helper in `ham.platform`, but two didn't justify it yet.
- **Model `choices=` changes need a migration** even though nothing enforces them at the DB
  level by default — Django's field deconstruction includes `choices`, so
  `makemigrations --check` fails without one. Added two new `RequestMedia.failure_code`
  values (`upload_expired`, `processing_timed_out`) for the M3 sweeper; migration
  `ham/media/migrations/0002_alter_requestmedia_failure_code.py`.
- **`is_masked_view(ctx)` (from `ham.requests.queries`) vs. "does this actor hold role X"**:
  several places in this codebase had drifted to checking role membership directly instead of
  the shared masking predicate (N9's `media_gallery_for`) — worth grepping for
  `effective_roles & _SOME_ROLE_SET` in any module that's supposed to honor Q-124's masking
  before assuming a set-membership check is equivalent to it; they diverge the moment an
  actor holds two roles at once, which nothing else in the test suite exercises by default.
- **Streaming vs. presigned-URL for the leadership thumb/view routes**: chose streaming
  (`ham.media.services.read_media_bytes` + a `Cache-Control: no-store` response) over
  redirecting to a fresh `presign_get()` URL, mainly so there's exactly one place that sets
  the no-store header and the route never leaks a signed storage URL into the browser's
  network panel / history for someone to reopen after the leader's session ends. The existing
  `view_urls_for` (presigned-URL variant) is still there, unused by any route — flagged as
  dead code for whoever next touches `ham.media`, not removed (wasn't part of this fix round's
  task list).

## S3.5 — Approvals notification builders (docs/handoff/step3-wave-brief.md,
docs/architecture/approvals-contracts.md §4/§6, docs/ux/approvals.md E8-E15/L-E5-L-E12)

Two files, both extending the register() functions S2.6 already created (no new AppConfig
wiring needed — `RequestsConfig.ready()`/`RequesterPortalConfig.ready()` already call
`notifications.register()`):
- `ham/requester_portal/notifications.py`: `_build_approved_email` (E9/E9u/E12 — one builder,
  branches on `payload["stage"]`/`"urgent_approval"`), `_build_rejected_email` (E10/E13,
  branches on `payload["final"]`), `_build_question_asked_email` (E8), `_build_reconsideration_
  received_email` (E11, Q-175).
- `ham/requests/notifications.py`: `_build_decision_notices`/`_build_decision_emails`
  (RequestApproved/RequestRejected, held), `_build_urgent_approval_notices`/`_emails`
  (RequestUrgentApproval, immediate, Q-161), `_build_decision_undone_notices`/`_build_
  urgency_review_undone_notices` (Q-176 "urgent approval was undone" follow-up), `_build_
  urgency_certified_notices`/`_build_urgency_not_certified_notices` (+ banner clearing),
  `_build_reconsideration_notices`/`_emails` (Q-168 addressing), `_build_question_answered_
  notices`/`_emails` (L-E7).

**No email/no in-app registered at all for these events (the "no email" decision itself, not a
gap):** `RequestCategoryChanged` (Q-109), `RequestRejectionFinalized` (E14 — she already had
the deadline on E10), `RequesterQuestionAsked`→leadership (only the requester-side builder
listens to it). A `RequesterQuestionAsked` whose question was answered in the *same* phone
step (`ask_question(..., phone_answer=...)`, Q-159 no-email path) also gets no requester email
even when registered — `_build_question_asked_email` checks `question.answered_at is not None`
and returns `None`, since there's nothing left to ask.

**RequestApproved/RequestRejected held-effects payload has no `approval_id`** (only
`request_id`/`stage`/`route`/...) — both leadership and requester builders that need the
`Approval` row (for the rejection message text, the decider id to exclude, `took_over_from_
user_id`) look it up via `Approval.objects.filter(request_id=..., stage=payload["stage"],
undone_at__isnull=True).order_by("-decided_at").first()` — safe because `approval_unique_live_
stage` guarantees at most one live row per `(request, stage)`, and the held-effects job only
ever fires while that row is still live (undone before `effective_at` short-circuits before
emitting the event at all, contracts.md §4).

**The "urgent approval was undone" follow-up (Q-176) can't be driven off a flag in the undo
payload** (`RequestDecisionUndone`/`RequestUrgencyReviewUndone` carry only `approval_id`/
`review_id`, no repeated `urgent_approval` bit, per the outbox PII/minimal-payload rule) — has
to be reconstructed at build time:
- `RequestDecisionUndone`: trivial, `Approval.urgent_approval` is already the exact flag set
  at decide time.
- `RequestUrgencyReviewUndone` (a standalone `UrgencyReview`, no `urgent_approval` field of its
  own): `review_urgency`'s own code only ever emits `RequestUrgentApproval` for a certify when
  `becomes_urgent_approval` — which requires the request to already be `APPROVED` at review
  time, and `review_urgency` never itself changes request status. So "`review.action ==
  certify_urgency` and the request's status is *currently* `APPROVED`" is a reliable
  reconstruction, **unless** something else changed the request's status between the review
  and this undo (e.g. a later Director/AD cancel) — flagged as a PRD-GAP in the module
  docstring rather than silently trusted; a future slice could close it for good by adding an
  `Approval`-style flag to `UrgencyReview` itself.

**Urgent must-ack banner clearing (Q-160/L-E12 "the urgent banner clears") is NOT built into
`ham.notifications` itself** — `Notification.acknowledged_at` is per-recipient, set only by
that person's own acknowledge action (`ham.notifications.services`), so "every pastor's banner
clears once *any* pastor reviews the urgency" needed a new, deliberate side effect: `_clear_
urgent_banner(request_id)` bulk-`.update(acknowledged_at=now)`s every still-unacknowledged
`requires_ack=True` `Notification` row for that request's `subject_id`, called from both the
`UrgencyCertified` and `UrgencyNotCertified` builders (a builder function causing a DB write as
a side effect, not just returning notices, is new here — documented in the module docstring;
no other builder in this codebase does this).

**Test-pollution landmine confirmed and worked around (worth remembering for any future
`transaction=True` test in this codebase):** a `@pytest.mark.django_db(transaction=True)` test
that calls a real `@command` like `approve_request`/`submit_request` — which internally defers
a Procrastinate job via `ham.jobs.defer`/`defer_later` (writes through the *same* Django
connection, confirmed by reading `ham/jobs/__init__.py`) — really commits that job row to
Postgres. If the test never drains it (e.g. it calls the underlying plain function directly
instead of going through the job queue, as `run_held_decision_effects` here), the job row
survives that test's teardown. `run_due_jobs_now()` in *any later* test then picks it up
(`scheduled_at <= now()` for an immediate `defer()`, or even a `defer_later()` whose
`schedule_at` was computed off a `FixedClock` set to a date in the past relative to real wall
time — do not combine `set_clock(FixedClock(<past date>))` with a code path that defers a real
job) and tries to run it against rows that a *different* test's flush already truncated away —
symptom: `AssistanceRequest.DoesNotExist` / "delivery not found" warnings in completely
unrelated test files, only reproducible when running the *full* suite, never in isolation.
Fixed by not using `transaction=True` for a test that doesn't actually need cross-transaction
commit visibility (the default `django_db` mark's single rolled-back transaction never lets the
orphaned job row reach Postgres at all). If a test genuinely needs `transaction=True` and also
defers a real job it won't drain, call `ham.jobs.run_due_jobs_now()` (or cancel/delete the
`procrastinate_jobs` row) before the test ends.
