# HAM step 2 (Intake) — S2.0 contracts

Owner: ham-backend-engineer (S2.0). Built against `docs/architecture/intake.md` (the plan,
owner decisions box overrides its body) and `docs/prd-open-questions.md` Q-025, Q-099-Q-132.

This file is the exact-names reference so S2.1-S2.5 (running in parallel) can code against
each other without waiting. Nothing here is a new product decision — it is intake.md's plan
turned into literal function signatures, session keys and matrix action names.

## 1. Authz principals (`ham/authz/context.py`)

```python
@dataclass(frozen=True, slots=True)
class RequesterContext:
    request_id: uuid.UUID | None       # None only for the very first request.submit call
    link_id: uuid.UUID | None = None
    verification_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None           # always None (no User row, intake.md §3)
    real_user_id: uuid.UUID | None = None       # always None
    roles: frozenset[str] = frozenset({"REQUESTER"})
    scoped_roles: tuple[ScopedRole, ...] = ()
    is_active: bool = True
    step_up_at: dict[str, dt.datetime] = {}
    # + is_authenticated (True), is_impersonating (False), effective_roles (== roles),
    #   has_fresh_step_up(...) (always False) — duck-type-compatible with ActorContext.

@dataclass(frozen=True, slots=True)
class SystemContext:
    user_id: uuid.UUID | None = None
    real_user_id: uuid.UUID | None = None
    roles: frozenset[str] = frozenset({"SYSTEM"})
    scoped_roles: tuple[ScopedRole, ...] = ()
    is_active: bool = True
    step_up_at: dict[str, dt.datetime] = {}
    # same duck-type surface as RequesterContext.
```

Neither `"REQUESTER"` nor `"SYSTEM"` is in `ham.authz.roles.GLOBAL_ROLES` or
`ANY_STANDING_ROLE` — they never reach `shell.use`/`me.*`. `ham.audit.services.record`
branches on `"REQUESTER"`/`"SYSTEM"` in `ctx.roles` (duck-typed, no import of this module —
`ham.audit` sits below `ham.authz`).

`Scope.OWN_REQUEST` (`ham/authz/matrix.py`): `resource.request_id == ctx.request_id`. Every
action using it takes a `resource_from` that returns an object with a `.request_id` attribute
(the `AssistanceRequest` row itself, or any 1:1/FK row exposing that attribute).

## 2. Matrix actions this slice adds (`ham/authz/matrix.py`)

| Action | Allowed | Scope | IB | Audited on denial |
|---|---|---|---|---|
| `request.submit` | REQUESTER | ANY | | |
| `requester.request.view` | REQUESTER | OWN_REQUEST | | |
| `requester.media.upload` | REQUESTER | OWN_REQUEST | | |
| `requester.media.remove` | REQUESTER | OWN_REQUEST | | |
| `requester_link.regenerate` | REQUESTER | OWN_REQUEST | | |
| `request.list` | ADM, DIR, AD, PAS, BRD | ANY | | |
| `request.view` | ADM, DIR, AD, PAS, BRD | ANY | | |
| `request.history.view` | DIR, AD, PAS, BRD (not ADM) | ANY | | |
| `requester_pii.reveal` | DIR, AD, PAS, BRD (not ADM) | ANY | | yes |
| `request_media.view` | ADM, DIR, AD, PAS, BRD | ANY | | |
| `request_media.reopen` | DIR, AD, PAS, BRD (not ADM) | ANY | | |
| `request.cancel` | DIR, AD | ANY | yes | yes |
| `request.create_assisted` | DIR, AD, PAS | ANY | yes | yes |
| `request.needs_phone_check.list` | DIR, AD | ANY | | |
| `request.contact_verify_phone` | DIR, AD | ANY | yes | yes |
| `intake_source.manage` | DIR, AD | ANY | | |
| `notification.acknowledge` | any standing role | SELF | yes | |
| `system.request.complete_intake_checks` | SYSTEM | ANY | | |
| `system.media.process` | SYSTEM | ANY | | |
| `system.media.purge` | SYSTEM | ANY | | |
| `system.intake.purge` | SYSTEM | ANY | | |

ADM = Administrator (Q-124: view-only, contact masked, no reveal — gets `request.list`/
`request.view`/`request_media.view` only). None of these step-2 actions require step-up.

`requester_pii.reveal`'s Director-not-logged exemption (Q-024) and the masking rule for the
Administrator (Q-124) are **service-layer** behaviour (`ham.requests.services.
reveal_requester_pii`, S2.2), not matrix flags — the matrix only decides *who may ask*.

## 3. Command/service seams (stubs raising `NotImplementedError` today)

```python
# ham/requests/services.py
def submit_request(
    ctx: RequesterContext, *, draft_id: UUID, verification_id: UUID,
) -> AssistanceRequest: ...
```
`@command("request.submit")` (S2.2 wraps it). `ctx.request_id` is `None` on entry. Raises
`ValueError` if `verification_id` isn't a consumed, `purpose="intake"` challenge referencing
`draft_id` (Q-100: verify before the request reaches leaders).

```python
# ham/requester_portal/services.py
@dataclass(frozen=True, slots=True)
class IssuedLink:
    token: str
    link: RequesterAccessLink

def issue_link(
    *, request_id: UUID, kind: str, verification_id: UUID | None = None,
) -> IssuedLink: ...

def resolve_token(token: str, *, now: dt.datetime | None = None) -> RequesterContext | None: ...
```
`kind` is `"initial"` or `"regenerated"`. `issue_link` revokes the previous live link for
`request_id` (`revoke_reason="superseded"`) in the same transaction (§76 auto-invalidate,
intake.md §4). It does not audit or email; the caller does, since the audit action
(`requester_link.issued` vs `.regenerated`) and outbox event depend on `kind`.

**Orchestration** (S2.3, intake.md §2): the portal verifies the draft, then calls
`ham.requests.services.submit_request`, then `issue_link(kind="initial")`, all inside one
transaction.

## 4. Platform seams

- `ham.platform.otp` — `hash_value(value) -> str`, `hash_matches(value, expected_hash) -> bool`,
  `generate_code(length) -> str`, `generate_token(nbytes=32) -> str`. Keys from
  `settings.HAM_TOKEN_HMAC_KEYS` (comma-separated, first = current; every key tried on
  `hash_matches`). Empty/unset falls back to a `SECRET_KEY`-derived key (reproduces
  `ham.identity.authn`'s pre-S2.0 hash exactly — no behaviour change). `ham.identity.authn`
  now delegates to this module; `_hash`/`_generate_code` remain as thin wrappers.
- `ham.platform.net.client_ip(request) -> str` — honours `settings.HAM_TRUSTED_PROXY_COUNT`.
  `ham.web.auth_views._client_ip` is now `= net.client_ip` (existing tests import the old name).
- `ham.platform.storage` — `ObjectStore` protocol (`presign_put`, `presign_get`, `head`,
  `delete`, `copy`), `ObjectMeta`, `PresignedUpload`, `get_object_store()` (loads
  `settings.HAM_OBJECT_STORE_BACKEND` via `import_string`; raises `RuntimeError` naming the
  setting if unconfigured — no default backend ships in S2.0).

## 5. Audit

- `ham.audit.services.record(ctx=...)` — `ctx.roles` containing `"REQUESTER"` writes
  `actor_type="requester"`, `actor_user_id=None`; `context["link_id"]` is set when
  `ctx.link_id` is not `None`. `"SYSTEM"` writes `actor_type="system"`, `actor_user_id=None`.
  Anything else keeps the existing `ActorContext` (`"user"`) branch unchanged.
- `_AUDITED_ON_DENIAL` (`ham/authz/commands.py`) gained `requester_pii.reveal`,
  `request.cancel`, `request.create_assisted`, `request.contact_verify_phone`.
- `ham/audit/labels.py` gained groups/labels for every new `action` code listed in
  intake.md §6 ("Audit actions"): `request.submitted`, `request.contact_verified`,
  `request.status_changed`, `request.duplicates_flagged`, `request.cancelled`,
  `request.created_assisted`, `requester_link.issued`, `requester_link.regenerated`,
  `requester_verification.locked`, `requester_pii.revealed`, `request_media.batch_opened`,
  `request_media.uploaded`, `request_media.rejected`, `request_media.removed`,
  `request_media.purged`, `intake_source.created`, `intake_source.deactivated`.

## 6. Apps, URLs, nav

- New apps (empty, `apps.py` only): `ham.requester_portal` (label `requester_portal`),
  `ham.media` (label `ham_media`), `ham.requests` (label `requests`), `ham.notifications`
  (label `ham_notifications`). In `INSTALLED_APPS` between `ham.audit` and `ham.web`, in that
  dependency order.
- import-linter `layers` contract: `ham.web` -> `ham.requester_portal` -> `ham.media` ->
  `ham.requests` -> `ham.notifications` -> `ham.identity` -> ... (unchanged tail). The
  "domain modules never import `ham.integrations` directly" contract's `source_modules` now
  also lists the four new apps; the matching `ignore_imports` entries for
  `ham.requester_portal.verification`/`.notifications`, `ham.requests.notifications`,
  `ham.media.notifications` are **not yet added** (import-linter errors on an `ignore_imports`
  entry that matches nothing) — add the exact entry in the same commit that creates the file.
- `ham/web/urls_requests.py`, `urls_requester.py`, `urls_inbox.py` — each `urlpatterns: list =
  []` today; `ham/web/urls.py` splices all three in with `*urls_x.urlpatterns` after the
  step-1 routes. S2.7/S2.8 add real `path(...)` entries to these files, not new files.
- `ham.authz.nav._ITEMS` gained `NavItem("requests", "Requests", "web:requests",
  "clipboard-list", False, "request.list")` — `built=False`, so `ham.web.nav`'s
  template-facing helpers (which filter on `.built`) never render it yet, but
  `ham.authz.nav.nav_for`/`authorize()` already reflect who *could* reach it. S2.8 flips
  `built=True` once the URL exists.

## 7. Independent oracle (`tests/authz/generate_expected_matrix.py`)

Re-derived from the PRD/Qs, not copied from the matrix (per its own docstring rule). Step-2
"human-role" actions (`request.list`, `.view`, `.history.view`, `requester_pii.reveal`,
`request_media.view`/`.reopen`, `request.cancel`, `request.create_assisted`,
`request.needs_phone_check.list`, `request.contact_verify_phone`, `intake_source.manage`,
`notification.acknowledge`) were added to the existing `ORACLE` dict and flow through the
existing row-generation logic unchanged.

`RequesterContext`/`SystemContext` actions got a **separate** `PSEUDO_ORACLE` dict and
`_pseudo_rows()` generator (the existing MFA-gating/role-union/self-scope logic in `_rows()`
doesn't apply to a pseudo-role that never holds more than one role). New CSV `scope_case`
values: `"own_request"` / `"other_request"`. `tests/authz/test_expected_matrix.py`'s `_ctx_for`
builds a real `RequesterContext`/`SystemContext` (not a plain `ActorContext`) when
`row["role"]` is `"REQUESTER"`/`"SYSTEM"`.

Regenerate after any further change: `PYTHONPATH=. python tests/authz/generate_expected_matrix.py`.
