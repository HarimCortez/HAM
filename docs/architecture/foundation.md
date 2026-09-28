# HAM foundation: build-order step 1

Owner: ham-architect. Status: plan. Assumes ADR 0001 Option B (Django + Postgres + HTMX + a TypeScript offline module). Sections 1–4 and 7 are stack-agnostic; paths and library names are Option B.
PRD trace: §3.1–§3.5, §4, §16, §17, §35 (seam only), §36.1, §36.4, §51 (seam only), §57/§56 (immutability pattern), §58, §59, §60, §66 (Identity, AuditEvent, ExternalIntegrationEvent), §67, §68, §70.2–§70.6, §76, §78, §79. Decided Qs used: Q-002, Q-006 (design only), Q-010, Q-011, Q-013, Q-014, Q-016, Q-019, Q-020, Q-021, Q-023, Q-024 (design only), Q-026.

> **Owner decisions after this plan was drafted (2026-09-27) — these override the text below.** Source of truth: `docs/prd-open-questions.md`.
> - ADR 0001 Accepted: Django (Q-003).
> - Before MFA enrollment, a person keeps non-MFA access (e.g. Volunteer); the MFA role's permissions activate only after enrollment (Q-045). Replaces §2.7 "only MFA setup and sign-out".
> - Step-up actions: global role grant/removal, audit export, MFA reset of another user, **starting impersonation**, regenerating recovery codes, changing sign-in email; 5-minute window per action kind (Q-010, Q-031, Q-046).
> - Sessions: passwordless 30 days inactivity; MFA roles 8 h idle + 7 days absolute; code/link 15 min, 5 tries (Q-032).
> - `role.grant_global` / `role.revoke_global`: Administrator (all roles, never own) and Director (all except Administrator, never own); Pastor/Board rep grants by Director require an authorizing-body reason; every grant/removal emails all Administrators (Q-041, Q-055). Director gets `user.list`/`user.view`.
> - Project/Task Leader assignment: Director and Assistant Director only — **not** the Administrator (Q-054).
> - Impersonation: not of another Administrator, no nesting; add `ImpersonationEnded` event + email to the impersonated person (Q-034, Q-049); idle timeout returns the Admin to own account (Q-053).
> - Self sign-up (Volunteer only, onboarding pending) plus invitation by Director/AD/Admin (Q-037). Step 1 may ship invite + self sign-up form; onboarding content comes in step 6.
> - Audit export in step 1: CSV; Excel/PDF (§58) before V1 ships.
> - Audit events store IDs, not requester PII (Q-050); purge at 1 year (Q-036).
> - Cut from step 1: optional personal note on invitations (§3.1); Inbox-dependent flows (MFA reset request via Inbox, large export via Inbox) — use email instead.

## 1. Module boundaries (all of V1; only **bold** modules are built in step 1)

```
config/                 settings (12-factor env), urls, wsgi/asgi
ham/
  **platform/**         Clock (injectable UTC now), ids (UUIDv7), church profile service, brand loader, jobs interface (ham.jobs → Procrastinate)
  **rules/**            THE versioned rules module (constants only, no DB)
  **identity/**         User, SharedIdentityProfile, RoleAssignment, sign-in, MFA enforcement, step-up, impersonation
  **authz/**            actions, deny-by-default matrix, policy engine, scope-provider registry, route guard, nav computation
  **audit/**            AuditEvent, record(), viewer/filter queries, CSV export, retention purge (job later)
  **outbox/**           DomainEvent outbox, subscriber registry, dispatcher job, dead letters
  **integrations/**     adapters: email (anymail), calendar (stub), fitness (stub), drive (stub). Never called directly by domain code
  **web/**              app shell, nav, Home placeholders, Me, Admin, Audit, sign-in screens, PWA manifest + service worker
  notifications/        in-app Notification + email fan-out (§35)                     – step with staffing
  requester_portal/     secure links, verification, survey links (§7, §54)            – step 2
  requests/             intake, approvals, reconsideration, urgent, duplicates (§6–§10) – step 2
  projects/             assessment, feasibility, scope, holds, schedule, status (§11–§13, §39, §52, §53)
  tasks/                tasks, dependencies, templates, unplanned work (§15, §18, §19)
  volunteers/           profile, skills, tools, availability, travel, credentials, mentors, deactivation (§20–§26)
  staffing/             matching, invitations, waitlist, 48h, reconfirmation, cancellation, reliability (§27–§34)
  attendance/           QR/GPS check-in, offline sync, hours, safety checklist (§37, §38)
  finance/              budget, lines, funding parties, cost-change approval (§14, §13)
  compliance/           agreements, versions, acceptances, contractor verification, media consent (§40–§43, §48)
  media/                uploads, compression, retention, publication (§45–§49, §69)
  incidents/, comments/, feedback/ (§55, §56, §57)
  reporting/            scorecard, dashboards, public embed, reports (§63–§65, §72)
  ai/                   advisory service layer; drafts only (§61, §79)
frontend/               TypeScript: service worker, offline queue (later), QR scanner (later); built by esbuild
design-system/          existing; tokens.css built per HAM_BRAND
tests/                  unit/, authz/, e2e/ (Playwright)
```

**Dependency rules** (enforced by an import-linter contract in CI):
- `web` → domain modules → {`authz`, `audit`, `outbox`, `rules`, `platform`}.
- Domain modules call each other only through their `services.py`, never another module's models.
- Only `integrations` talks to third parties, and only as an `outbox` subscriber (exception: sign-in emails are sent through the same email adapter via an immediate job).
- Only `identity` reads auth tables; other modules receive an `ActorContext`. This keeps the §36.1/§78 shared-identity seam: identity can later become an OIDC client of a shared provider without touching domain code.

**One write path (the command pattern).** Every consequential action is a service function decorated `@command("action.code")`, which:
1. builds `ActorContext`;
2. calls `authz.require(ctx, action, resource)`;
3. enforces step-up freshness if the action requires it;
4. refuses the action if it is blocked while impersonating;
5. runs the change, then `audit.record(...)`, then `outbox.emit(...)`, all inside one `transaction.atomic()`.

If any part fails, nothing is written. This is the §79 flow (validate → transaction → audit) for humans and, later, for accepted AI drafts.

## 2. Step-1 scope
1. **Skeleton:** Django project, Postgres, Procrastinate worker, Docker + `render.yaml`, env-based settings, UTC everywhere (`USE_TZ=True`), injectable Clock, health check, security headers (CSP, HSTS), structured logs that never contain names, emails or phones (user IDs only). Django admin mounted only when `DEBUG`.
2. **Church profile + brand (Q-026, Q-007):**
   - `HAM_BRAND` env selects `design-system/brands/<id>/`. The build runs `build_tokens.py --brand $HAM_BRAND --check` and collects `tokens.css`, the logos and self-hosted fonts named in `brand.json`.
   - `church_profile()` returns one merged read-only object:
     - from `brand.json` (deploy-time): name, shortName, missionLine, logos, alt text, fonts;
     - from the singleton `ChurchProfile` row (Admin-editable, audited): hamPhone, hamEmail, timeZone, websiteUrl.
   - Templates use `{church.*}` only; no literal church strings. The PWA manifest name/icons come from the profile.
3. **Users and roles (§4, §16, §17, §66):** `User` + `SharedIdentityProfile`, and one `RoleAssignment` table for global roles and project/task-scoped leader roles. Admin invites users and grants/revokes global roles. The leader-assignment service commands exist and are tested, but their UI arrives with projects/tasks.
4. **Permission policy layer (§67, §68):** a deny-by-default action matrix in code, scope providers, a route guard (every URL must declare an action or be in `PUBLIC_ROUTES`), `scope_queryset()` for list filtering (used from step 2), and the neutral no-permission/not-found response (navigation.md §6).
5. **Audit (§58, §59, §70.6):** an append-only `AuditEvent`; a viewer for Director/Admin with filters (date range, user, project, action type, role); CSV export (opens in Excel) with step-up. PDF export ships with the reporting step.
6. **Outbox seam (§36.4, §70.3, §78):** `OutboxEvent` + `OutboxDelivery`, a subscriber registry, a dispatcher job with retry/backoff and dead-letter, and an Admin integration-status page. Step-1 subscribers: email adapter; a no-op `fitness` stub; a logging stub in dev.
7. **Auth (§60, Q-010, Q-019):**
   - **Everyone signs in the same way.** The person enters their email and receives one email containing a 6-digit code and a one-click link. The link opens a "Continue" page with a POST button, so email link scanners can't use it up. It works in any browser, which matters because installed iOS PWAs don't share Safari's session. The response is identical whether or not the account exists.
   - **Privileged roles (§60.1: Administrator, Director, Assistant Director, Pastor, Board rep) must use TOTP.** Until they enroll, the session can reach only MFA setup and sign-out. Enrollment shows 10 recovery codes. "Trust this device for 30 days" is unchecked by default. Granting a privileged role to a signed-in user downgrades their session until they enroll or verify.
   - **Step-up:** audit export, global role grant/revoke and MFA reset require a TOTP entered within the step-up freshness window.
8. **Impersonation (§59):**
   - Admin only; a reason is required; no nesting; target rules per Q-034.
   - While impersonating, the effective identity is the target and the real actor is the Admin. Every audit event records both.
   - Idle 15 minutes → automatically returns to the Admin's own account.
   - Actions flagged `blocked_while_impersonating` are refused with a reason. This covers all step-up actions, role/leader changes, MFA changes, audit export, deleted-comment content, church profile, outbox retry, and starting another impersonation.
   - A non-dismissable banner is shown on every page (navigation.md §6).
   - Q-024 consequence: the Director's reveal-logging exemption never applies while an Admin is acting as the Director, because the actor is the Admin.
9. **Rules module** with the initial constants (§5 below).
10. **App shell (navigation.md §3):**
    - Layout: bottom nav under 768px, icon rail 768–1023px, sidebar from 1024px. Tokens only; light theme only (Q-016).
    - Nav is computed server-side from permissions via `authz.nav_for(ctx)`. Each destination declares its action and a `built` flag; step 1 renders only built destinations (Home, Inbox placeholder, Me, Admin, Audit log).
    - Home placeholder per highest role, e.g. "Your to-do list will appear here". Admin Home shows integration status and recent sign-in failures.
    - The PWA manifest and a service worker that precaches the shell and serves an offline page. **No offline queue yet;** its storage and sync contract is designed in the attendance step.
11. **Seed script:** `manage.py seed_dev` creates fictional users on `example.org`:
    - Nadia (Admin), Marcus (Director + Volunteer, a combined role), Andre (Assistant Director), Pastor Ruth, Elder Samuel (Board rep), Luis (Volunteer), Tom (Volunteer), Kevin (Volunteer), Bayside Plumbing (Contractor), Grace (Social Media Specialist).
    - Fixed dev-only TOTP secrets for the MFA roles.
    - It refuses to run when `HAM_ENV=production`.
    - `manage.py bootstrap_admin --email` creates the first production Administrator (audited with actor `system:bootstrap`); MFA enrollment is forced at first sign-in.
12. **CI (GitHub Actions):** `ruff check`, `ruff format --check`, `mypy` (django-stubs), `tsc --noEmit`, `manage.py makemigrations --check`, import-linter, `pytest` (Postgres service), `build_tokens.py --brand miami-temple --check`, a no-hard-coded-colour lint on templates/CSS, `pip-audit`, and the Playwright smoke suite (headless Chromium).

## 3. Data model (step 1)
All IDs are UUIDv7; all timestamps are `timestamptz` UTC. **S** = sensitive (§68: never in logs, calendar, AI prompts or aggregates).

**User** (`identity_user`)
- `id`, `email` (citext, unique, **S**), `is_active` (bool), `created_at`, `created_by_id` (null = system), `first_sign_in_at`, `last_sign_in_at`, `disabled_at`, `disabled_by_id`.
- No usable password.
- States: Invited (no `first_sign_in_at`) → Active ⇄ Disabled. Disabling ends all sessions and impersonations of that user.

**SharedIdentityProfile** (`identity_profile`, 1:1 with User; §36.1)
- `user_id` (PK), `full_name`, `mobile_phone` (E.164, optional, **S**), `notify_email` (bool, default true), `updated_at`.
- In-app notifications are always on (at least one channel). SMS is hidden (§75).
- The display name "Kevin T." is derived, not stored.

**RoleAssignment** (`identity_role_assignment`)
- `id`, `user_id`, `role` (enum), `scope_type` (null | `project` | `task`), `scope_id` (uuid, null), `granted_by_id`, `granted_at`, `grant_reason` (optional), `revoked_at`, `revoked_by_id`, `revoke_reason`.
- Roles: `ADMINISTRATOR`, `HAM_DIRECTOR`, `ASSISTANT_DIRECTOR`, `PASTOR`, `BOARD_REPRESENTATIVE`, `SOCIAL_MEDIA_SPECIALIST`, `VOLUNTEER`, `CONTRACTOR` (global, `scope_type` null); `PROJECT_LEADER` (scope `project`); `TASK_LEADER` (scope `task`).
- Invariants:
  - CHECK: the role's scope kind matches `scope_type`.
  - Partial unique `(user_id, role)` where global and not revoked.
  - Partial unique `(role, scope_type, scope_id)` where not revoked: one Project Leader per project and one Task Leader per task (Q-039).
  - Rows are never deleted; a re-grant is a new row.
  - The last active Administrator cannot be revoked or disabled (Q-035).
  - The Task Leader's primary-skill requirement (§17) is enforced in the tasks step.
  - Scope existence is validated by the scope-provider registry once projects/tasks exist.
- §66 names ProjectLeaderAssignment and TaskLeaderAssignment; these are rows of this table, exposed through `projects.services` / `tasks.services`.

**MFA** (allauth `mfa_authenticator`)
- TOTP secret and recovery codes are **S**, encrypted at rest through the allauth adapter with `HAM_FIELD_ENCRYPTION_KEY`.
- The trust cookie is allauth's; resetting MFA invalidates it.

**ImpersonationSession** (`identity_impersonation`)
- `id`, `admin_user_id`, `target_user_id`, `reason` (**S**: may mention a person), `started_at`, `last_activity_at`, `ended_at`, `end_reason` (`manual` | `idle_timeout` | `signed_out` | `target_disabled`).

**ChurchProfile** (`platform_church_profile`, singleton row)
- `ham_phone`, `ham_email`, `time_zone` (IANA, default `America/New_York`; Q-030), `website_url` (used later for the public-embed CSP allowlist), `updated_at`, `updated_by_id`.
- Brand fields live in `brand.json`.

**AuditEvent** (`audit_event`, append-only)
- `id`, `seq` (bigserial), `occurred_at`.
- `actor_type` (`user` | `system` | `requester`), `actor_user_id` (the real person; the Admin when impersonating), `acting_as_user_id` (null unless impersonating), `impersonation_id`.
- `actor_roles` (text[] snapshot, for the "role" filter).
- `action` (dotted code), `target_type`, `target_id`, `project_id` (nullable, for the filter).
- `before` / `after` (jsonb, changed fields only), `reason`, `context` (jsonb: request_id; IP and user agent only for `auth.*` events, **S**), `rules_version`.
- DB triggers: UPDATE is always refused. DELETE is refused unless the transaction ran `SET LOCAL ham.audit_purge = 'on'`, which only the retention job does, deleting rows older than `AUDIT_RETENTION` (Q-036).
- Never registered in any admin; no service exposes update/delete.
- Indexes: `(occurred_at)`, `(actor_user_id, occurred_at)`, `(project_id, occurred_at)`, `(action, occurred_at)`.

**OutboxEvent** (`outbox_event`) and **OutboxDelivery** (`outbox_delivery`)
- OutboxEvent: `id`, `seq`, `event_type`, `schema_version`, `occurred_at`, `aggregate_type`, `aggregate_id`, `payload` (jsonb: **IDs and codes only, never S fields**; subscribers fetch details through services under their own least privilege), `correlation_id`.
- OutboxDelivery: `event_id`, `subscriber`, `status` (`pending` | `delivered` | `failed` | `dead`), `attempts`, `next_attempt_at`, `last_error` (scrubbed), `delivered_at`.
- Emitted in the same transaction as the change. Adapter failures touch only `outbox_delivery` (§70.3).

## 4. Permission policy
- `authorize(ctx, action, resource=None) -> Decision(allowed, reason, step_up_required, blocked_by_impersonation)`.
- Deny if the action is unknown, the user is disabled or unauthenticated, or no role grants it.
- Roles are a **union**, so a higher privilege wins (§4.11). Exceptions: safety/legal rules are domain validations after authorization and are never permissions (§3.5); impersonation never adds privilege (§59).
- Scope rules: `ANY`, `SELF`, `LEADS_PROJECT(resource.project_id)`, `LEADS_TASK(resource.task_id)`, `ASSIGNED_PROJECT`, `INVITED_PROJECT` (the last two come from later modules through the scope-provider registry).
- The matrix is code (`ham/authz/matrix.py`), versioned with a changelog, and not Admin-editable (Q-038).
- A generated `docs/architecture/permission-matrix.md` is checked in CI for staleness, like `build_tokens --check`.
- Denied privileged actions (step-up actions, role changes, impersonation) write `authz.denied`. Ordinary denials are not logged, to avoid noise.
- Denied requests render the neutral "This page isn't available to your account" page with HTTP 404, so a project's existence is never revealed.

**Step-1 actions** (ADM Administrator, DIR Director, AD Assistant Director, PAS Pastor, BRD Board rep, SMS Social Media Specialist, VOL Volunteer, CON Contractor; SU = step-up; IB = blocked while impersonating)

| Action | Allowed | Flags | PRD |
|---|---|---|---|
| `shell.use` (Home, Inbox, sign out) | any active user | | §67 |
| `me.view`, `me.update` | SELF | | §67 Volunteer "own profile" |
| `me.security.manage` (recovery codes, forget trusted devices) | SELF | IB | §60 |
| `church_profile.update` | ADM | IB | §4.11, Q-007 |
| `user.list`, `user.view` | ADM | | §4.11 |
| `user.invite`, `user.update_identity` | ADM | | §4.11 |
| `user.disable`, `user.enable` | ADM (not self; not the last admin) | IB | §4.11 |
| `user.mfa_reset` | ADM (not self) | SU, IB | §60.1, Q-035 |
| `role.grant_global`, `role.revoke_global` | ADM | SU, IB | §4.11, §58, Q-010 |
| `leader.project.assign` / `.revoke` | ADM, DIR, AD | IB (Q-031) | §16 |
| `leader.task.assign` / `.revoke` | ADM, DIR, AD | IB (Q-031) | §17 |
| `audit.view` | ADM, DIR | | §58, §67, Q-021 |
| `audit.export` | ADM, DIR | SU, IB | §58, Q-010 |
| `audit.view_deleted_comment` (declared for later) | ADM, DIR | IB | §57 |
| `impersonation.start` | ADM | IB (no nesting) | §59, Q-034 |
| `impersonation.stop` | the impersonating Admin | | §59 |
| `integrations.view_status`, `rules.view` | ADM (DIR for `rules.view`) | | §4.11 |
| `outbox.retry` | ADM | IB | §70.3 |
| `requester_pii.reveal` (declared; used in step 2; reveal logged unless the effective actor is DIR and not impersonating) | per Q-009, Q-024 | | §68 |

Everything else (PAS, BRD, SMS, VOL, CON, PL, TL) gets only `shell.use` and `me.*` in step 1. Their V1 capabilities follow navigation.md §2 "Who reaches what", which is the oracle for later steps.

## 5. Rules module (`ham/rules/`)
- `RULES_VERSION = "2026.09.27-1"` plus `CHANGELOG.md`.
- A frozen dataclass `RULES` grouped by domain. No DB, no Admin UI.
- A test pins every value plus a hash; changing a value without bumping the version fails CI. `AuditEvent.rules_version` records which set applied.

| Constant | Value | Source |
|---|---|---|
| `INVITATION_RESPONSE_WINDOW` | 48 h | Q-002 |
| `WAITLIST_PROMOTION_CONFIRM_WINDOW` | 24 h | §29, §32 |
| `AUTO_STAFFING_CUTOFF_BEFORE_START` | 48 h | §29, §30, §76 |
| `UNDERSTAFFED_ALERT_BEFORE_START` | 96 h | Q-013 |
| `RECONFIRMATION_DAYS_BEFORE` | 7 | §32 |
| `RECONFIRMATION_REMINDER_DAYS_BEFORE` | (7, 6, 5) | Q-011 |
| `UNCONFIRMED_RELEASE_DAYS_BEFORE` | 5 | §32, §76 |
| `CANCELLATION_FREE_DAYS_BEFORE` | 7 | §33 |
| `AGREEMENT_UNACCEPTED_LEADER_ALERT_BEFORE_START` | 48 h | Q-014 |
| `LATE_GRACE_PERIOD` | 15 min | Q-020 |
| `LEADER_PHONE_VISIBLE_WINDOW` | day before + day of (church local days) | Q-023 |
| `CREDENTIAL_EXPIRY_ALERT_DAYS` | (60, 30, 7) | §24.1 |
| `REQUESTER_LINK_VALID_AFTER_COMPLETION` | 7 days | §7.3 |
| `REGENERATED_REQUESTER_LINK_LIFETIME` | 14 days | §7.3 |
| `SURVEY_LINK_LIFETIME` | 30 days | §54 |
| `SURVEY_REMINDER_AFTER_COMPLETION` | 7 days | §54, §76 |
| `REQUESTER_MEDIA_BATCH` | 10 photos, 3 videos, 2 min per video | §45, §46 |
| `VIDEO_RETENTION_AFTER_CLOSE` | 30 days | §47.1 |
| `PHOTO_RETENTION_AFTER_CLOSE` | 90 days | §47.2 |
| `AUDIT_RETENTION` | 365 days | §58 |
| `INCIDENT_RETENTION` | 7 years | §56 |
| `HOMEOWNER_AGREEMENT_RETENTION` | 7 years | §41 |
| `VOLUNTEER_AGREEMENT_RETENTION_AFTER_INACTIVE` | 7 years | §42 |
| `MFA_REQUIRED_ROLES` | ADM, DIR, AD, PAS, BRD | §60.1 |
| `MFA_TRUSTED_DEVICE_LIFETIME` | 30 days | Q-010 |
| `STEP_UP_ACTIONS` | audit.export, role.grant_global, role.revoke_global, user.mfa_reset | Q-010, Q-031 |
| `STEP_UP_FRESHNESS` | 5 min `// PRD-GAP Q-031` | Q-031 |
| `IMPERSONATION_IDLE_TIMEOUT` | 15 min | §59 |
| `SIGN_IN_CODE_LIFETIME`, `SIGN_IN_CODE_MAX_ATTEMPTS` | 15 min, 5 `// PRD-GAP Q-032` | Q-032 |
| `SESSION_IDLE_LIFETIME_STANDARD` / `_MFA_ROLES` | 30 days / 12 h `// PRD-GAP Q-032` | Q-032 |
| `OUTBOX_MAX_ATTEMPTS`, `OUTBOX_BACKOFF` | 8, exponential from 1 min to 6 h cap | §70.3 (engineering) |

Not added until decided: reliability numbers (Q-001), public-embed suppression threshold (Q-027), site-code fallback (Q-028).

## 6. State transitions and audit events (step 1)
| Transition | Who | Audit `action` | Outbox event |
|---|---|---|---|
| User created (invite) | ADM; system bootstrap | `user.created` | `UserCreated` |
| Invited → Active (first sign-in) | the user | `auth.sign_in.succeeded` (first flag) | — |
| Active → Disabled / Disabled → Active | ADM | `user.disabled` / `user.enabled` | `UserDisabled` / `UserEnabled` |
| Identity fields changed | ADM (other) / SELF | `user.identity_updated` / `profile.updated` | `UserProfileUpdated` (IDs only) |
| Global role granted / revoked | ADM + step-up | `role.granted` / `role.revoked` | `RoleGranted` / `RoleRevoked` |
| Project/Task Leader assigned / revoked | ADM, DIR, AD | `leader.project_assigned` / `_revoked`, `leader.task_assigned` / `_revoked` | `ProjectLeaderAssigned` …, `TaskLeaderAssigned` … |
| MFA enrolled / reset / recovery code used | SELF / ADM + step-up / SELF | `auth.mfa.enrolled` / `auth.mfa.reset` / `auth.mfa.recovery_code_used` | — |
| Sign-in failed (lockout), step-up ok/failed, sign-out | system / SELF | `auth.sign_in.locked`, `auth.step_up.succeeded` / `.failed`, `auth.sign_out` | — |
| Impersonation started / ended | ADM / ADM or system (idle) | `impersonation.started` (reason) / `impersonation.ended` (end_reason) | — |
| Blocked action while impersonating | system | `impersonation.action_blocked` | — |
| Church profile updated | ADM | `church_profile.updated` | — |
| Audit exported | ADM, DIR + step-up | `audit.exported` (filters, row count) | — |
| Outbox delivery retried | ADM | `outbox.retried` | — |

Each code sent is not audited (noise). Lockouts are.

## 7. API surface (step 1)
Server-rendered HTML routes plus a small JSON API. All POSTs are CSRF-protected; every route declares an action or is listed in `PUBLIC_ROUTES`.

| Method + path | Action | Notes |
|---|---|---|
| GET `/healthz` | public | DB + job-queue lag |
| GET, POST `/sign-in` | public | email → sends code + link; identical response for unknown emails; rate-limited |
| GET, POST `/sign-in/code` | public | 6-digit code |
| GET, POST `/sign-in/link/<token>` | public | GET shows a Continue button; POST consumes the link |
| GET, POST `/sign-in/mfa` | pending-login | TOTP or recovery code; "Trust this device for 30 days" |
| GET, POST `/mfa/setup` | pending-enrollment | QR code, confirm, show recovery codes once |
| GET, POST `/step-up?next=` | signed-in MFA role | refreshes step-up freshness |
| POST `/sign-out` | `shell.use` | |
| GET `/` | `shell.use` | Home placeholder for the highest role |
| GET `/inbox` | `shell.use` | placeholder |
| GET, POST `/me` | `me.view` / `me.update` | name, mobile, email notifications on/off |
| GET `/me/security`; POST `/me/security/recovery-codes`, `/me/security/forget-devices` | `me.security.manage` | |
| GET `/admin/users` (`?role=&q=&status=`), GET `/admin/users/<id>` | `user.list` / `user.view` | |
| GET, POST `/admin/users/new` | `user.invite` | sends a sign-in email |
| POST `/admin/users/<id>/identity` | `user.update_identity` | |
| POST `/admin/users/<id>/disable`, `/enable` | `user.disable` / `user.enable` | |
| POST `/admin/users/<id>/roles` (grant), `/admin/users/<id>/roles/<rid>/revoke` | `role.grant_global` / `role.revoke_global` | step-up; reason optional |
| POST `/admin/users/<id>/mfa-reset` | `user.mfa_reset` | step-up |
| POST `/admin/users/<id>/impersonate` | `impersonation.start` | reason required |
| POST `/impersonation/stop` | `impersonation.stop` | |
| GET, POST `/admin/settings/church` | `church_profile.update` | phone, email, time zone, website |
| GET `/admin/integrations`; POST `/admin/integrations/deliveries/<id>/retry` | `integrations.view_status` / `outbox.retry` | |
| GET `/admin/rules` | `rules.view` | read-only values + version |
| GET `/audit` (`?from=&to=&user=&project=&action=&role=`), GET `/audit/<id>` | `audit.view` | paginated by `seq` |
| POST `/audit/export` (same filters) | `audit.export` | step-up; CSV (UTF-8 with BOM for Excel) |
| GET `/api/v1/me` | `shell.use` | JSON: user id, display name, roles, nav, impersonation state, rules_version (used by the service worker/shell) |
| GET `/manifest.webmanifest`, `/sw.js`, `/offline` | public | from the church profile |

Service commands without routes yet: `assign_project_leader`, `revoke_project_leader`, `assign_task_leader`, `revoke_task_leader` (routes arrive with projects/tasks).

## 8. Slices
| # | Slice | Owner | Depends on | Parallel with |
|---|---|---|---|---|
| S1 | **Platform skeleton:** repo layout, settings, Docker, `render.yaml`, Postgres, Procrastinate worker + `ham.jobs`, Clock, UUIDv7, health check, logging scrubber, CI pipeline, church profile model/service + brand loader + token build step, `bootstrap_admin` | ham-backend-engineer | ADR accepted | S2 |
| S2 | **Rules module** + version/hash test + changelog + `rules.view` data provider | ham-rules-engineer | none (pure Python; lands in S1's tree) | S1, S3a, S4 |
| S3a | **Identity, roles, policy, audit:** User, Profile, RoleAssignment + invariants, authz matrix/engine/route guard/nav computation, `@command` pipeline, AuditEvent + triggers + viewer queries + CSV export, admin user/role services, `seed_dev` | ham-backend-engineer | S1 | S4, S5 (shell part) |
| S3b | **Auth:** allauth login-by-code + one-click link (spike; fallback codes only), MFA enforcement + enrollment gate, trusted device, step-up, MFA reset, impersonation + idle timeout + blocked actions | ham-backend-engineer | S3a, S4 (email adapter) | S5 |
| S4 | **Outbox + adapters:** outbox tables, `emit()`, subscriber registry, dispatcher job, backoff/dead-letter, email adapter (anymail; dev = console, test = locmem), stub adapters (calendar, fitness, drive), integration-status data | ham-integrations-engineer | S1 | S3a, S5 |
| S5 | **App shell and screens:** token-based layout (390/768/1280), nav from `nav_for`, Home placeholders, Me, sign-in/code/link/MFA/setup/step-up screens, Admin users/roles/settings/integrations/rules, Audit viewer + export, impersonation banner, neutral 404, PWA manifest + service worker (shell precache, offline page), self-hosted brand fonts | ham-frontend-engineer | S1 (shell against a stub nav); S3a/S3b for real screens | S3a, S3b, S4 |

Order: S1 ∥ S2 → S3a ∥ S4 ∥ S5-shell → S3b → S5-screens → ham-test-engineer → reviews (privacy-security, prd-guardian, UX, UI visual QA).

## 9. Test plan hooks (ham-test-engineer)
1. **Permission-matrix test (generated from §67).**
   - The test engineer writes an **independent oracle**, `tests/authz/expected_matrix.csv` (action, role, scope case, expected, PRD § / Q), from §67 + decided Qs, not from the code.
   - A generator parametrizes: every action × every single role × unauthenticated × disabled user × zero-role user × representative role pairs (union, e.g. VOL+DIR) × in-scope / out-of-scope for scoped roles × impersonating (the target's roles apply, and IB actions are denied).
   - Compare with `authz.authorize`; any mismatch fails.
   - Also: unknown action → deny; every URL declares an action (route-coverage test); `nav_for` per seeded persona matches the navigation.md §3.1 table for built destinations.
2. **Audit coverage:** every `@command` emits exactly one AuditEvent with actor, UTC `occurred_at` and `rules_version`. A forced exception rolls back the change, the audit event and the outbox event together. Raw SQL UPDATE/DELETE on `audit_event` raises; DELETE with the purge flag removes only rows past retention. Impersonated actions carry both identities. Export writes `audit.exported`.
3. **Auth:**
   - No account enumeration (identical responses and timing band); code expiry and max attempts via time-machine; the link survives a GET prefetch.
   - Every §60.1 role is forced into MFA setup; a role granted mid-session downgrades the session.
   - The trusted device skips TOTP until day 30 and is re-challenged on day 31; step-up freshness is enforced for each SU action; MFA reset invalidates trust.
   - Impersonation: reason required, returns after 15 min idle, IB actions refused and audited, no nesting, the Director reveal exemption is not applied under impersonation.
4. **Outbox:** the adapter raises → the domain row persists, delivery retries with backoff, becomes dead-letter after max attempts, and retry works. Payloads contain no email, phone or name (schema test).
5. **Rules:** pinned values + hash + version bump.
6. **Brand/tokens:** `build_tokens --check` passes; templates contain no literal church name (grep test); no hex colours outside `design-system/`.
7. **Playwright smoke** (`tests/e2e/`): each seeded persona signs in (the code is read from the captured mailbox) and sees the correct nav; the Director signs in with a seeded TOTP; audit export requires step-up; the Admin impersonates Kevin and the banner and blocked-action message appear; the offline page shows when the network is cut. Viewports 390/768/1280.
8. **§77 harness (skeleton only):** fixtures for the captured mailbox, fake calendar adapter, controllable Clock and job-runner "run due jobs now". `tests/e2e/test_acceptance_77.py` lists the 30 steps as pending tests, filled in as steps land.

## 10. Out of scope for step 1
- Requests, requester secure links, verification, Q-025.
- Projects, tasks, and leader-assignment UI.
- Volunteer profiles and self sign-up (Q-037).
- Staffing and reliability (Q-001).
- Attendance and the **offline check-in queue** (Q-006; only the service-worker shell now).
- In-app notification centre (Inbox is a placeholder); Google Calendar adapter (stub subscriber only).
- AI, media and object storage, comments, incidents, reports, scoreboard and public embed (Q-005, Q-027).
- PDF audit export (reporting step); audit retention purge job (retention step; the trigger escape hatch is built now).
- PII reveal logging (action declared; implemented with step 2).
- SMS, Drive, Fitness, background checks (§44: no field), multilingual, dark theme (Q-016).

## 11. New PRD gaps (for `docs/prd-open-questions.md`)
| ID | PRD § | Question | Options | Proposed default |
|---|---|---|---|---|
| Q-030 | §70.5 | Which time zone is "local time" for screens, emails and day-based rules (e.g. "day before", Q-023)? | Church time zone for everyone / each user's own / device time | One church time zone in the church profile (America/New_York for Miami Temple), used everywhere |
| Q-031 | §16, §17, §59, Q-010 | Do Project/Task Leader assignments count as "role changes" for step-up and the impersonation block? How fresh must a step-up be? | All role/leader changes need step-up / only global role changes; freshness: every time / 5 minutes | Step-up for global role changes, MFA reset and audit export, valid 5 minutes; leader assignments need no step-up (Directors already use MFA) but are blocked while impersonating |
| Q-032 | §60 | How long do sign-ins last, and how long is an emailed code valid? | Various | Volunteers, Project/Task Leaders, contractors, Social Media: 30 days of inactivity on a device. MFA roles: 12 hours of inactivity, then an email code again (a trusted device skips the authenticator step). Code/link valid 15 minutes, 5 tries |
| Q-033 | §35, §60.2, §68 | Should tapping a notification email sign the person in automatically? | Auto sign-in token in each email / normal sign-in, then return to the item | No sign-in tokens in notification emails (forwarded emails would leak access); long sessions mean most taps land signed in; otherwise sign-in returns to the item |
| Q-034 | §59 | Whom may an Administrator impersonate, and is the person told? | Anyone / not other Administrators / not any MFA role; notify or not | Anyone except another Administrator; no nesting; the person is not notified (it is in the audit log) |
| Q-035 | §4.11, §60.1 | What happens if a leader loses their authenticator, and can the last Administrator be removed? | Recovery codes only / Admin reset too; allow or block removing the last admin | 10 recovery codes at enrollment; an Administrator may reset someone else's MFA (step-up, audited); HAM refuses to remove or disable the last active Administrator; owner keeps two Administrators |
| Q-036 | §41, §56, §57, §58 | The audit log keeps 1 year, but some records keep 7 years. Do their audit events stay longer? | Purge all audit events at 1 year / keep events linked to 7-year records | Purge all audit events at 1 year. Incidents, amendments and agreement acceptances keep their own actor and timestamps for 7 years in their own tables. Deleted-comment content (kept in the audit event, §57) is gone after 1 year |
| Q-037 | §20, §42 | How does a volunteer get an account? | Self sign-up from a church link / invited by leadership / both | Both: self sign-up starts onboarding (no invitations until §42 is complete); Director, Assistant Director or Admin can invite by email. Step 1 ships Admin invite only |
| Q-038 | §4.11, §66, §67 | Can the Administrator edit what each role is allowed to do? | Fixed, versioned permission matrix in code; Admin assigns roles / Admin-editable permissions | Fixed matrix in code (like the rules module); Admin assigns roles. Changes ship as a release |
| Q-039 | §16, §17 | Can a project have more than one Project Leader, or a task more than one Task Leader? | Exactly one / allow co-leaders | Exactly one active leader per project and per task; reassigning replaces the previous one (audited) |
