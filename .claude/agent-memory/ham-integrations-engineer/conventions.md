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
