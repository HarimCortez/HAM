# HAM intake: build-order step 2

Owner: ham-architect. Status: plan. Built on `docs/architecture/foundation.md` (step 1) and the step-1 code in `ham/`.

PRD trace: §3.2–§3.4, §4.1, §5, §6, §6.1, §6.2, §7.1–§7.3, §9, §10 (capture and alerts only), §35 (requester "request received" and "additional information"; leadership in-app), §45, §46, §47 (retention anchor only), §52 (pre-approval states), §58, §60.3, §63/§68 (PII-free surfaces), §64 (requests awaiting approval), §66 (AssistanceRequest, Requester, Property, RequestContactVerification, RequestMedia, Notification), §67 Requester, §69, §70.2–§70.6, §71 (search by request ID only), §76 ("auto-flag duplicates", "auto-invalidate old requester access links"), §77 steps 1–3.

Decided Qs used: Q-004, Q-007, Q-009, Q-019, Q-024, Q-026, Q-029 (open; only matters for the secure page after scheduling, not in step 2), Q-030, Q-033, Q-048, Q-050, Q-070, Q-078, Q-080.
Closes or answers: Q-081 (step-2 part), Q-025 (default proposed below).

Out of scope (§73, §75): SMS codes (Q-019), a requester account system, background checks, Drive (seam only), multilingual.

---

## 0. Decisions for the product owner that are costly to change later

Everything else in this plan uses a sensible default. These seven are hard to undo once real requests are in the database, so each one needs your decision. Each has a Q-row in §13.

**D1. What a requester must give us (Q-099, Q-124).**
- Why it matters: a field that starts optional can't later become required for old requests, and extra required fields make people give up.
- Recommended required fields:
  - name;
  - email (theirs or a helper's);
  - one phone number (mobile preferred, but a landline is accepted);
  - service address;
  - relationship to the property;
  - property type;
  - what help they need;
  - the certifications in D3.
- Recommended optional fields: urgent flag (a reason is required only if they tick it), known hazards, preferred times, preferred way to reach them, photos and videos.
- Options: (a) as recommended; (b) require both email and a mobile phone, as §6.1 literally lists them. Option (b) shuts out people like Doris, who has no email and may have only a landline.

**D2. How strongly we check that a requester is who they say (Q-100, Q-025).**
- Recommended:
  - The request is only sent to leaders **after** the person types the 6-digit code we email them. This also blocks most spam.
  - "Email" can be a family member's or helper's address.
  - People with no email at all call the ministry phone. A Director, Assistant Director or pastor then enters the request for them and records "verified by phone call". Photos for those requests are taken at the site visit.
- Options: (a) as recommended; (b) accept requests without verifying first and verify only before photo upload, which means more spam and more work for leaders; (c) pay for an SMS provider now, which §75 excludes.
- Why it's costly: every stored request carries the method used to verify it, and changing the method later leaves old and new requests handled differently.

**D3. The legal certification wording (Q-101, Q-102).**
- The requester ticks short statements. HAM stores the exact version they agreed to, forever, with the request.
- Draft wording for review by you and ideally church counsel:
  - Everyone: "The information I've given is true to the best of my knowledge."
  - Owner: "I own this property and I give HAM permission to work there."
  - Family member: "The property owner, [owner name], has authorized me to make this request."
  - Tenant: "I will get written permission from the property owner or landlord before any work begins."
  - Everyone: "I'm responsible for any approval my HOA, condominium association, landlord or property manager requires."
- Why it's costly: once people accept wording, changing it creates a second version. Old requests keep the old words.

**D4. How long we keep request records and personal details (Q-116, Q-117).**
- The PRD sets retention for media, agreements, incidents and audit, but not for the request itself.
- Recommended:
  - Keep requests for 7 years after they close. After that, erase name, email, phone and street, and keep only the ZIP code, category and outcome, so reports and "families served" still work.
  - Requests closed as spam: erase after 90 days.
  - Unfinished forms that were never verified: erase after 24 hours.
- Options: keep forever / 7 years (recommended) / 3 years.
- Why it's costly: deleted data can't come back, and data we keep is data we must protect.

**D5. How personal details are protected on disk (Q-118).**
- Recommended: rely on the database's own disk encryption (Render) and encrypted off-site backups.
- Encrypt field by field only these: the short-lived unfinished forms, and the copy of each requester link that HAM needs in order to re-send it (see D6).
- Option: encrypt name, address and phone field by field. This protects better against a stolen backup, but leaders can't search by name or address (§71) without extra machinery. Switching later means rewriting every stored row.

**D6. Whether every email to a requester contains their private link (Q-105).**
- Recommended: yes. The link is Doris's only way back to her page.
- The cost: if she forwards an email, the person she forwards it to can open her page. They could see her status and add photos, but nothing more.
- To make this work, HAM stores the link encrypted so it can be re-sent. Only a scrambled fingerprint is used to look the link up.
- Option: never put the link in follow-up emails ("use the link from your first email or ask for a new one"). This is safer but harder for low-tech requesters.

**D7. Whether the Administrator can see requests (Q-112).**
- Recommended: no. The Administrator runs the system, not the ministry. Troubleshooting happens through impersonation, which is logged with both identities.
- This differs from `docs/ux/navigation.md`, whose table gives the Administrator view access to Requests.

---

## 1. Scope split: step 2 (Intake) vs step 3 (Approvals)

| Area | Step 2 builds | Step 3 builds | Seam |
|---|---|---|---|
| Public form (§6, §6.1) | Form, church-link codes (§6), draft, email-code verification, submission | — | — |
| Property authority (§6.2) | Relationship, owner name (family), certifications with version | Tenant's written permission is re-confirmed through the homeowner agreement (§41, compliance step) | `attestation_version` + statement codes stored on the request |
| Verification (§7.1) | Email code or link; staff phone verification (Q-025, gated) | — | `RequestContactVerification` rows |
| Secure page and links (§7.2, §7.3) | Initial link, page (status, summary, contact card, media card), expired page, regenerate, find my request, link lifecycle | Cards for decisions, reconsideration request; later steps add agreement, schedule, survey, cost approval | Page is built from "action card providers" registered by modules |
| Duplicates (§9) | Automatic matching job, alert panel (prior request, outcome, cancel reason, assistance history once it exists) | Approval/rejection reason appears in the panel automatically | `outcome_summary(request)` in `ham.requests` |
| Urgent (§10) | Urgent flag + justification; immediate alert to all pastors (email + in-app, ignoring preferences); awareness for Director/AD; urgent-first ordering | Pastor **certification** and urgent approval; alerts to Director/AD/PL after urgent approval | `urgency_status` enum already holds `certified` / `not_certified`; event `UrgencyCertified` reserved |
| Request states (§52) | Submitted → Awaiting Approval (automatic), → Cancelled (leadership) | → Approved (creates Project), Rejected, Reconsideration Pending, final Rejected | Full status enum from day 1; transition table in `ham/requests/states.py`; step 3 adds edges |
| Media (§45, §46) | Initial batch, reopen batch (Director, AD, pastor, Board rep), processing, viewing | Batches close when the request is decided | `media.services.close_open_batches(request_id)` |
| Requester notifications (§35) | Request received, additional photos requested, new-link notice, cancellation | Approval, rejection, reconsideration outcome | Requester email builders live in `ham/requester_portal/notifications.py`; step 3 adds builders there |
| Leadership triage | Requests list/detail, PII reveal with logging, Home attention cards, real Inbox | Decision buttons on the same detail page | Attention-provider registry |
| Project identity | Request number "HAM #047" | Project created with **the same UUID and number** as its request | Audit `project_id` = request id from intake onward, so the audit "project" filter shows the full history |

---

## 2. Module boundaries

```
ham/
  requester_portal/  NEW  public requester surface: IntakeDraft, verification challenges, access links,
                          RequesterContext building, requester email builders, purge jobs
  media/             NEW  (reserved in foundation §1; starts now) RequestMediaBatch, RequestMedia,
                          upload intents, processing job (Pillow, pillow-heif, ffmpeg), view/reopen/remove
  requests/          NEW  AssistanceRequest, Requester, Property, RequestContactVerification,
                          RequestMatch, IntakeSource; states.py (rules-owned), matching.py (rules-owned),
                          services, duplicate job, PII reveal, attention providers, leadership builders
  notifications/     NEW  (foundation said "with staffing"; needed now for Inbox/urgent)
                          Notification rows, in-app outbox subscriber + builder registry,
                          attention-provider registry
  platform/          + otp.py (hash/code/token helpers moved out of identity.authn),
                     + net.py (client_ip moved from web.auth_views), + storage.py (ObjectStore protocol + loader)
  integrations/      + storage/ (S3-compatible R2 adapter, local filesystem adapter)
  web/               + views_requests.py, views_requester.py, views_inbox.py,
                     + urls_requests.py, urls_requester.py, urls_inbox.py (included once from urls.py)
```

**Layers** (import-linter `layers` contract, top to bottom):
`ham.web` → `ham.requester_portal` → `ham.media` → `ham.requests` → `ham.notifications` → `ham.identity` → `ham.authz` → `ham.audit` → `ham.outbox` → `ham.platform` → `ham.rules`

Later steps insert `ham.projects` between `requester_portal` and `media`.

**Rules:**
- A module calls another only through its `services.py`, and only downward.
  - The portal orchestrates submission: it verifies the draft, calls `requests.services.submit_request`, then issues the link, all in one transaction.
  - `media` asks `requests.services` whether a request is open. `requests` never imports `media`.
- Only `ham.identity` reads auth tables. `ham.notifications` gets recipients from a new `identity.services.notification_recipients(roles) -> [(user_id, email, notify_email)]`.
- **Third parties:**
  - Email builders: add `ignore_imports` entries for `ham.requests.notifications`, `ham.media.notifications` and `ham.requester_portal.notifications` → `ham.integrations.email.notifications`.
  - Code emails: add an entry for `ham.requester_portal.verification` → `ham.integrations.email.service`. This is the same exception S3b uses for sign-in codes.
- **Object storage is the second documented exception to "integrations only through the outbox".**
  - Uploads are synchronous infrastructure, like the database.
  - Domain code uses `ham.platform.storage.get_object_store()`, which loads `settings.HAM_OBJECT_STORE_BACKEND` with `import_string`. Nothing imports `ham.integrations` statically.
- **Email builder registry change (integrations, S2.0):** `register_notification` keeps a **list** of builders per event type, and `handle_email_event` concatenates their results. One event can then email both the requester (portal builder) and leaders (requests builder).
- **Convention change:** `ham.notifications` registers its own `inapp` outbox subscriber in `NotificationsConfig.ready()`. This is internal, not a third party, and is recorded in the integrations conventions file.

---

## 3. Data model

All IDs are UUIDv7 and all timestamps are `timestamptz` UTC. Field classes:
- **P** (identity/contact): reveal-gated for leadership, never in lists, logs, outbox, calendar, AI or aggregates.
- **C** (circumstances): shown on the request detail page to `request.view` holders only, never in lists, notifications, logs, AI prompts or aggregates.
- **S**: other sensitive values (keys, IPs).

**AssistanceRequest** (`requests_request`)
- `id`, `reference_number` (int, unique, from a Postgres sequence; shown as "HAM #047").
- `status`: `SUBMITTED` | `AWAITING_APPROVAL` | `APPROVED` | `REJECTED` | `RECONSIDERATION_PENDING` | `CANCELLED`. Step 2 uses the first two and `CANCELLED`.
- `source`: `public_form` | `church_link` | `assisted`; `intake_source_id` (nullable); `created_by_user_id` (assisted only).
- `need_category` enum (Q-107).
- `description` **C**.
- `urgent_requested` (bool), `urgency_justification` **C** (required iff urgent), `urgency_status`: `none` | `awaiting_certification` | `certified` | `not_certified`.
- `known_hazards` **C** (optional), `preferred_availability` **C** (optional), `preferred_contact_method`: `email` | `phone_call` | `text_message` (Q-124).
- `relationship_to_property`: `owner` | `authorized_family_member` | `tenant`.
- `attestation_version` (code-versioned text id), `attested_statements` (text[] of statement codes), `attested_at`.
- `submitted_at`, `status_changed_at`, `closed_at` (retention anchor), `requester_access_ends_at` (null = open), `cancel_reason_code`, `cancel_note` **C**.
- Invariants:
  - CHECK: justification is non-empty iff `urgent_requested`.
  - CHECK: `closed_at` is set iff the status is terminal.
  - Required statement codes per relationship are checked in the service.
- Index: `(status, urgent_requested, submitted_at)`.

**Requester** (`requests_requester`, 1:1 with the request, not a User)
- `request_id` (PK/FK), `full_name` **P**, `email` (citext, nullable only when `source = assisted`) **P**, `phone` (E.164) **P**.
- `email_key`, `phone_key`, `name_zip_key` **S**: normalized match keys, indexed, used for duplicates and later search.
- `anonymized_at`.

**Property** (`requests_property`, 1:1)
- `request_id`, `line1` **P**, `line2` **P**, `city` **P**, `state`, `postal_code` **P**, `property_type` enum, `owner_name` **P** (required for `authorized_family_member`), `address_key` **S**.

**RequestContactVerification** (`requests_contact_verification`, append-only by a DB trigger, like audit)
- `id`, `request_id`, `channel` (`email` | `phone`), `method` (`email_code` | `email_link` | `staff_phone_call`), `value_key` **S** (HMAC of the verified value; a later contact change invalidates it), `purpose` (`intake` | `link_regeneration`), `verified_at`, `verified_by_user_id` (staff only), `challenge_id`.

**RequestMatch** (`requests_match`)
- `id`, `request_id`, `prior_request_id`, `reasons` (text[]: `address` | `phone` | `email` | `name_zip`), `detected_at`.
- Unique `(request_id, prior_request_id)`. No dismiss in V1 (Q-109).

**IntakeSource** (`requests_intake_source`, church-issued codes)
- `id`, `code` (6 characters, no ambiguous characters, unique), `label` (no PII), `created_by_user_id`, `created_at`, `deactivated_at`, `deactivated_by_user_id`.

**IntakeDraft** (`requester_portal_draft`)
- `id`, `payload_ciphertext` (Fernet: the whole form, including P/C), `email_key` **S**, `ip_address` **S**, `created_at`, `expires_at` (`INTAKE_DRAFT_LIFETIME`), `consumed_at`, `request_id`.
- Purged by a job after it expires. Never visible to leadership.

**RequesterVerificationChallenge** (`requester_portal_challenge`)
- `id`, `purpose` (`intake` | `link_regeneration`), `draft_id` | `request_id`, `email_key` **S**, `code_hash`, `link_token_hash`, `created_at`, `expires_at`, `failed_attempts`, `consumed_at`, `ip_address` **S**.
- Same shape and rules as `SignInChallenge`: reuses `RULES.auth.SIGN_IN_CODE_*`; purged after `SIGN_IN_CHALLENGE_RETENTION`.

**RequesterAccessLink** (`requester_portal_link`)
- `id`, `request_id`, `token_hash` (unique), `token_ciphertext` (D6), `kind` (`initial` | `regenerated`), `issued_at`, `expires_at` (null for initial), `revoked_at`, `revoke_reason` (`superseded` | `anonymized`), `verification_id`, `last_used_at` (written at most hourly).
- Partial unique `(request_id) WHERE revoked_at IS NULL`: one live link per request.
- Token: `secrets.token_urlsafe(32)`.
- Hash: HMAC-SHA256 with `HAM_TOKEN_HMAC_KEYS`. New hashes use the first key; lookups try every key. This is deliberately not `SECRET_KEY`, so rotating the secret key doesn't kill months-long links.

**RequestMediaBatch** (`media_request_batch`)
- `id`, `request_id`, `number`, `kind` (`initial` | `reopened`), `opened_by_user_id` (null for initial), `reason` **C** (required when reopened, §46), `opened_at`, `closed_at`.
- Snapshot of `max_photos`, `max_videos`, `max_video_seconds` and `rules_version` at opening.

**RequestMedia** (`media_request_item`)
- `id`, `request_id`, `batch_id`, `media_kind` (`photo` | `video`), `status` (`reserved` | `uploaded` | `processing` | `ready` | `rejected` | `removed` | `purged`).
- Storage: `quarantine_key` (original; deleted after processing), `storage_key`, `thumb_key` (random, non-guessable, contain no request id).
- Metadata: `detected_type`, `bytes`, `width`, `height`, `duration_ms`, `failure_code` (`too_long` | `too_large` | `unsupported` | `corrupt`).
- Uploader: `uploaded_by_type` (`requester` | `user`), `uploaded_by_user_id`.
- Timestamps: `reserved_at`, `uploaded_at`, `processed_at`, `removed_at`, `purged_at`.
- Slot counting: a slot is taken by `reserved`, `uploaded`, `processing` or `ready`. It is enforced under `select_for_update()` on the batch, so two phones can't both take the tenth photo.

**Notification** (`notifications_notification`)
- `id`, `recipient_user_id`, `outbox_event_id`, `kind`, `subject_type`, `subject_id`, `title` (PII-free, checked by the outbox payload validator), `urgent`, `created_at`, `read_at`, `acknowledged_at` (urgent banner).
- "Needs response" is **not** stored. It is computed live by attention providers, so resolving an item anywhere clears it everywhere (navigation.md §4).

---

## 4. State machines

**AssistanceRequest** (the table lives in `ham/requests/states.py`; rules-engineer owns it)

| From → To | Who | Audit | Outbox |
|---|---|---|---|
| (none) → SUBMITTED | REQUESTER after a verified code or link; staff via assisted entry (Q-025) | `request.submitted` (+ `request.contact_verified`) | `RequestSubmitted` |
| SUBMITTED → AWAITING_APPROVAL | SYSTEM, when the intake-checks job (duplicate scan) finishes | `request.status_changed` (+ `request.duplicates_flagged` if there are matches) | `RequestAwaitingApproval` |
| SUBMITTED / AWAITING_APPROVAL → CANCELLED | DIR, AD (reason code: `spam` / `requester_withdrew` / `duplicate_submission` / `other`, plus an optional note) | `request.cancelled` | `RequestCancelled` |
| Step 3 edges | Board rep, Pastor | — | — |

- Urgent is an attribute, not a state (§52).
- On submission, `urgency_status` becomes `awaiting_certification` if the requester ticked urgent.
- Entering a terminal state sets `closed_at` and `requester_access_ends_at = closed_at + REQUESTER_ACCESS_AFTER_CLOSE` (Q-104). Completion (step 10) uses `REQUESTER_LINK_VALID_AFTER_COMPLETION`.

**Access link validity** (a pure function, `ham/requester_portal/validity.py`)
- `initial`: valid while not revoked and (`requester_access_ends_at` is null or now < it).
- `regenerated`:
  - issued **after** normal access ended: valid for `REGENERATED_REQUESTER_LINK_LIFETIME` (14 days);
  - issued **before** normal access ended: same rule as initial (Q-103).
- Issuing any link revokes the previous one in the same transaction (`superseded`). This is §76 "auto-invalidate", computed when read, so no job is needed.

**IntakeDraft:** created → consumed (becomes a request) | expired (purged).

**Challenge:** pending → consumed | expired | locked (5 wrong codes).

**RequestMedia:** reserved → uploaded → processing → ready | rejected.
- An unconfirmed reservation is released after `MEDIA_UPLOAD_INTENT_LIFETIME`.
- ready → removed (requester, while the batch is open) | purged (retention).

**Batch:** open → closed (full, request decided in step 3, or request closed).

---

## 5. Permissions

**New principals** (S2.0, `ham/authz`):
- `RequesterContext`: roles `{"REQUESTER"}`, `request_id` (null only for `request.submit`), `link_id`, `verification_id`, `user_id=None`, `is_authenticated=True`, `is_impersonating=False`.
- `SystemContext`: roles `{"SYSTEM"}`.
- Neither role is in `GLOBAL_ROLES` or `ANY_STANDING_ROLE`, so neither reaches `shell.use` or `me.*`.
- New `Scope.OWN_REQUEST` checks `resource.request_id == ctx.request_id`.
- `audit.record` records `actor_type = requester` (with `context.link_id`) or `system` for these contexts.
- Result: requester and system writes go through the same `@command` pipeline and are covered by the step-1 audit-coverage tests.

| Action | Allowed | Scope | Flags | PRD |
|---|---|---|---|---|
| `request.submit` | REQUESTER (draft with a consumed challenge, checked in the service) | ANY | | §6, §7.1 |
| `requester.request.view` | REQUESTER | OWN_REQUEST | read | §7.2, §67 |
| `requester.media.upload` | REQUESTER | OWN_REQUEST | domain: contact verified, batch open, slot free, request not closed | §7.1, §45 |
| `requester.media.remove` | REQUESTER | OWN_REQUEST | domain: own item, batch open | §45 (Q-114) |
| `requester_link.regenerate` | REQUESTER (fresh verification) | OWN_REQUEST | | §7.3, §58 |
| `request.list` | DIR, AD, PAS, BRD | ANY (`scope_queryset` provider registered) | | §8, §64 |
| `request.view` | DIR, AD, PAS, BRD | ANY | | §8, §67 |
| `request.history.view` (duplicate panel) | DIR, AD, PAS, BRD | ANY | kept separate so later PL/TL `request.view` never includes it | §5, §9 |
| `requester_pii.reveal` | DIR, AD, PAS, BRD | ANY | audited on denial; reveal logged unless the effective roles include DIR **and** the actor is not impersonating | §68, Q-009, Q-024, Q-048 |
| `request_media.view` | DIR, AD, PAS, BRD | ANY | | §69 |
| `request_media.reopen` | DIR, AD, PAS, BRD | ANY | reason required | §46 |
| `request.cancel` | DIR, AD | ANY | IB, audited on denial, reason code required | §52, Q-111 |
| `request.create_assisted` | DIR, AD, PAS | ANY | IB (the actor vouches for a phone call), audited on denial | Q-025 |
| `intake_source.manage` | DIR, AD | ANY | | §6, Q-106 |
| `notification.acknowledge` | any standing role | SELF | IB | §10, §35 |
| `system.request.complete_intake_checks`, `system.media.process`, `system.media.purge`, `system.intake.purge` | SYSTEM | | | §9, §45, §47, §76 |

ADM, SMS, VOL, CON, PL and TL get no request actions in step 2 (D7, Q-112).

PL and TL reach `requester_pii.reveal`, `request.view` and `request_media.view` in steps 4–5 through `LEADS_PROJECT` / `LEADS_TASK`. That needs a small matrix extension then: a scope per role within one action. It is not built now.

**Q-081 wiring:** reveal happens in `requests.services.reveal_requester_pii(ctx, request_id, surface)`.
- It authorizes, loads the P fields, and writes `requester_pii.revealed` (field **names** and surface, never values) unless exempt. Revealing and logging happen in one transaction, so if the audit write fails, no PII is returned.
- Leadership pages never embed P fields. The detail panel and hover card fetch `/requests/<id>/requester` (an HTMX partial), and the client caches it for that page view. That gives one event per reveal per page view (navigation.md §8.6).
- Label shown: "Leadership only · viewing is logged" for everyone except a non-impersonating Director, who sees "Leadership only".

---

## 6. Audit, domain events, notifications

**Audit actions** (all added to `ham/audit/labels.py` in S2.0):
- `request.submitted`, `request.contact_verified`, `request.status_changed`, `request.duplicates_flagged`, `request.cancelled`, `request.created_assisted`
- `requester_link.issued`, `requester_link.regenerated` (verification method in `after`; §7.3, §58), `requester_verification.locked`
- `requester_pii.revealed`
- `request_media.batch_opened` (reason), `request_media.uploaded`, `request_media.rejected`, `request_media.removed`, `request_media.purged`
- `intake_source.created`, `intake_source.deactivated`

`project_id` is set to the request id on every request-scoped event. Page views, drafts and each code sent are not audited; lockouts are.

**Outbox events** (IDs and codes only; the step-1 validator enforces this):

| Event | Payload |
|---|---|
| `RequestSubmitted` | `request_id`, `source`, `urgent` |
| `RequestAwaitingApproval` | `request_id`, `urgent` |
| `RequestCancelled` | `request_id`, `reason_code` |
| `RequesterAccessLinkIssued` | `request_id`, `link_id`, `kind` |
| `RequestMediaBatchOpened` | `request_id`, `batch_id` |
| `RequestMediaStored` | `request_id`, `media_id`, `media_kind` (Drive seam, §50) |
| `RequestMediaDeleted` | `request_id`, `media_id`, `reason_code` (Drive seam, §47.3) |

Reserved for step 3: `RequestApproved`, `RequestRejected`, `ReconsiderationRequested`, `UrgencyCertified`.

**Who is notified** (builders registered with `register_notification` / `register_inapp`):

| Event | Requester (email; link included per D6) | Leadership |
|---|---|---|
| Code emails (intake, regeneration) | transactional, immediate | — |
| `RequestSubmitted` | "We received your request (HAM #047)" + link + what happens next | — |
| `RequestAwaitingApproval`, normal | — | In-app update to DIR, AD, PAS, BRD; email follows each person's `notify_email` (Q-108) |
| `RequestAwaitingApproval`, urgent | — | All pastors: email + in-app urgent banner **regardless of preference** (§10, §35); DIR, AD: in-app update (Q-121) |
| `RequestCancelled` | Kind closure note, unless `reason_code = spam` (Q-111) | In-app update to DIR, AD |
| `RequesterAccessLinkIssued` (regenerated) | "Here's your new link; the old one no longer works" | — |
| `RequestMediaBatchOpened` | "We'd like a few more photos" + reason in plain words (§35 "request for additional information") | — |
| `RequestMediaStored` (first item of a reopened batch) | — | In-app update to the person who reopened the batch |

Leadership subjects and bodies contain only HAM #, category, the urgent flag and a deep link. Never a name, address, description or ZIP.

**Attention providers** (Home cards and Inbox "Needs response"):
- PAS, BRD: "Waiting for a decision (n)", urgent first. Actionable (step 3 adds the buttons).
- DIR, AD: the same rows, muted as "owner: pastors/Board", excluded from counts (navigation.md §8.3 group 4).

---

## 7. Routes

Public routes are listed in `PUBLIC_ROUTES`. Every requester page sends:
- `Cache-Control: no-store`
- `Referrer-Policy: no-referrer`
- `X-Robots-Tag: noindex` (except the form page itself)
- the step-1 CSP (no third-party origins except the storage origin in `connect-src` for uploads).

| Method + path | Action | Notes |
|---|---|---|
| GET, POST `/request-help` (`?c=CODE`) | public | Form (Django Form in `ham/requester_portal/forms.py`). POST creates the draft and challenge; the draft id goes in the anonymous session, never the URL. An unknown or deactivated code is treated as public (never blocks a person) |
| GET, POST `/request-help/verify`; POST `/request-help/verify/resend` | public | Code entry; POST success → `request.submit` → redirect to `/r/<token>?welcome=1` |
| GET, POST `/request-help/verify/link/<token>` | public | GET shows Continue; POST consumes (scanner-safe; works in another browser) |
| GET `/r/<token>` | `requester.request.view` | Valid: secure page. Real but expired: "This link has expired. We can send you a new one." Unknown: the same neutral "This link isn't valid" page as any bad token |
| POST `/r/<token>/new-link`; GET, POST `/r/<token>/new-link/verify`; GET, POST `/request-help/new-link/<token>` | public → `requester_link.regenerate` | Code and link go to the email **on file** (shown masked), so there is no enumeration |
| GET, POST `/request-help/find`; GET, POST `/request-help/find/link/<token>` | public → `requester_link.regenerate` | Enter email; identical response either way. One link-only verification email per matching request |
| POST `/r/<token>/media/intents` (JSON) | `requester.media.upload` | Reserves slots; returns presigned PUT URLs signed for exact length and type |
| POST `/r/<token>/media/<id>/complete`, `/remove` | `requester.media.upload` / `.remove` | Complete checks the object size and enqueues processing |
| GET `/r/<token>/media/<id>/thumb` | `requester.request.view` | 302 to a presigned GET (`PRESIGNED_VIEW_URL_LIFETIME`) |
| GET `/r/<token>/media` (HTMX partial) | `requester.request.view` | Processing status, polled while anything is processing |
| GET `/requests` (`?status=&urgent=&ref=`) | `request.list` | ID, category, urgent, status, age, media count, "possible earlier request" flag. **No P or C fields** |
| GET `/requests/<uuid>` | `request.view` | C fields, relationship, property type, media gallery, status history; duplicate panel if `request.history.view` |
| GET `/requests/<uuid>/requester` (partial) | `requester_pii.reveal` | Logged per Q-024 |
| GET `/requests/<uuid>/media/<mid>/(thumb\|view)` | `request_media.view` | 302 to a presigned GET |
| POST `/requests/<uuid>/media/batches` | `request_media.reopen` | Reason required |
| GET, POST `/requests/<uuid>/cancel` | `request.cancel` | Confirmation page first |
| GET, POST `/requests/new-by-phone` | `request.create_assisted` | Gated on Q-025 |
| GET, POST `/requests/intake-links`; POST `/requests/intake-links/<id>/deactivate` | `intake_source.manage` | |
| GET `/inbox`; POST `/inbox/<id>/read`; POST `/inbox/<id>/acknowledge` | `shell.use` / `notification.acknowledge` | |
| GET `/` | `shell.use` | Home renders attention providers |

**Nav:**
- Add `NavItem("requests", "Requests", "web:requests", ..., action="request.list")`.
- `bottom_nav_for`:
  - Pastor/Board: Home · Requests · Inbox · Me (Projects appears in step 4).
  - Director/AD: Home · Requests · Inbox · More.
- Update `tests/authz/test_nav_mobile.py` to match.

---

## 8. Rules-module additions

**Values the PRD gives are already present:**
- `REQUESTER_LINK_VALID_AFTER_COMPLETION` 7 d
- `REGENERATED_REQUESTER_LINK_LIFETIME` 14 d
- `REQUESTER_MEDIA_BATCH_MAX_PHOTOS` 10, `_MAX_VIDEOS` 3, `REQUESTER_MEDIA_MAX_VIDEO_DURATION` 2 min

§5 "no fixed limit" means there must be **no** per-household request limit rule.

**Reuse without new values:** requester codes use `RULES.auth.SIGN_IN_CODE_LENGTH/_LIFETIME/_MAX_ATTEMPTS`, `SIGN_IN_EMAILS_PER_ADDRESS_PER_HOUR`, `SIGN_IN_RESEND_COOLDOWN`, `SIGN_IN_FAILED_ATTEMPTS_PER_ADDRESS_PER_DAY` and `SIGN_IN_CHALLENGE_RETENTION`. Only their `sources` metadata gets the requester citations; the content hash covers values only, so there is no version bump for that.

**New values (all gaps; running as provisional or Pending):**

| Group | Constant | Value | Status |
|---|---|---|---|
| requester_access | `INTAKE_DRAFT_LIFETIME` | 24 h | provisional Q-117 |
| requester_access | `INTAKE_DRAFTS_PER_IP_PER_HOUR` | 10 | provisional Q-120 |
| requester_access | `INTAKE_SUBMISSIONS_PER_EMAIL_PER_DAY` | 3 | provisional Q-120 |
| requester_access | `INTAKE_MIN_FILL_TIME` | 3 s | engineering (anti-bot) |
| requester_access | `FIND_REQUEST_PER_IP_PER_HOUR` | 20 | provisional Q-120 |
| requester_access | `REQUESTER_ACCESS_AFTER_CLOSE` (cancelled / rejected-final / not executable) | 7 d | provisional Q-104 |
| media | `REQUESTER_PHOTO_MAX_BYTES` / `REQUESTER_VIDEO_MAX_BYTES` | 25 MB / 500 MB | provisional Q-115 |
| media | `REQUESTER_MEDIA_ACCEPTED_TYPES` | JPEG, PNG, HEIC/HEIF, WebP; MP4, MOV | provisional Q-115 |
| media | `MEDIA_UPLOAD_INTENT_LIFETIME`, `PRESIGNED_UPLOAD_URL_LIFETIME`, `PRESIGNED_VIEW_URL_LIFETIME` | 1 h, 15 min, 60 s | engineering |
| media | `VIDEO/PHOTO_RETENTION_AFTER_CLOSE` also apply to Cancelled | (existing values) | sources + Q-117 |
| retention | `REQUEST_RECORD_RETENTION_AFTER_CLOSE` | `Pending("Q-116", "7 years, then anonymize")` | Pending (used in step 10) |
| retention | `SPAM_REQUEST_RETENTION` | `Pending("Q-116", "90 days")` | Pending |

**Add invariants:**
- `INTAKE_DRAFT_LIFETIME` > `SIGN_IN_CODE_LIFETIME`
- `PRESIGNED_UPLOAD_URL_LIFETIME` ≤ `MEDIA_UPLOAD_INTENT_LIFETIME`

Image derivative size and quality (long edge 2560 px, thumbnail 480 px, JPEG q80, video 720p H.264) are technical settings in `ham/media/processing.py`, not business rules.

---

## 9. Anti-abuse on the public form (no third-party trackers or CAPTCHAs; the PRD doesn't allow sharing requester data, §3.4)

1. **Verify before it counts.** Nothing reaches leaders until the emailed code or link is used. Unverified drafts are encrypted and erased after 24 h.
2. **Honeypot field + minimum fill time.** A hidden field, plus an HMAC-signed timestamp that must be at least 3 s old. A failed check gets the **same** "Check your email" page, and nothing is sent, so bots learn nothing.
3. **Rate limits** (rules module): drafts per IP per hour; code emails per address per hour plus a 30 s cooldown; 5 wrong codes per challenge and 20 per address per day; submissions per email per day; find-my-request per IP per hour.
   - The IP comes from `ham.platform.net.client_ip` (moved from `web.auth_views`), which honours `HAM_TRUSTED_PROXY_COUNT`.
4. **No enumeration.**
   - Find-my-request returns an identical response, and all emails are sent from a job, so response timing doesn't leak.
   - Regeneration sends only to the address on file.
   - Tokens are 256-bit. Unknown and invalid tokens get the same page. Draft ids never appear in URLs.
5. **Email bombing.** The per-address cap applies, and the code email says "If you didn't ask for this, ignore it".
6. **Uploads.**
   - Presigned PUTs are signed for exact length and type, and go to a private `quarantine/` prefix (a bucket lifecycle rule deletes it after 1 day).
   - Size is re-checked on completion. Type is detected from magic bytes.
   - Pillow runs with a pixel cap (decompression bombs). `ffprobe` checks duration before transcoding.
   - Images are **re-encoded** with EXIF, including GPS, removed. Videos are transcoded. Originals are deleted. Only derivatives are ever served.
   - This meets §69 "scan where technically appropriate" without an antivirus service (Q-119).
7. Spam that gets past verification is cancelled by a leader as `spam` (no email sent) and erased on the spam schedule (Q-116).
8. Logs carry request and draft IDs only (the step-1 scrubber). There is no analytics script on any public page.

---

## 10. Slices

| # | Slice | Owner | Depends on | Parallel with | Owns files |
|---|---|---|---|---|---|
| S2.0 | **Seams and contracts** (keep it short: it prevents collisions). | ham-backend-engineer | — | S2.1 | shared files (see list below) |
| S2.1 | **Pure rules and logic.** Rules additions with changelog, version and hash; `ham/requests/states.py` transition table and guards; `ham/requests/matching.py` (address/phone/email/name normalization, USPS suffixes and directionals, unit designators, ZIP5, `phonenumbers`); `ham/requester_portal/validity.py`; unit tests. | ham-rules-engineer | — | S2.0 | `ham/rules/*`, the three pure files, `tests/rules`, `tests/requests/unit` |
| S2.2 | **Requests core.** Models and migrations; `submit_request`, `complete_intake_checks` (duplicate job via `ham.jobs`), `cancel_request`, `reveal_requester_pii`, list/detail queries, `scope_queryset` provider, attention providers, `outcome_summary`, `seed_dev_requests` command. | ham-backend-engineer | S2.0, S2.1 (the table can be stubbed) | S2.3, S2.4, S2.5 | `ham/requests/*` except the rules-owned files |
| S2.3 | **Requester portal.** Draft, form validation, challenges (code + link), transactional code emails, `issue_link` / `resolve_token → RequesterContext` / regenerate / find, rate limits, honeypot, purge jobs. | ham-backend-engineer (second worktree) | S2.0 | S2.2, S2.4, S2.5 | `ham/requester_portal/*` |
| S2.4a | **Object storage adapter.** S3-compatible (R2) and local-filesystem implementations of `ObjectStore` (presign put/get, head, delete, copy); settings; bucket CORS and lifecycle runbook in `docs/dev-environment.md`. | ham-integrations-engineer | S2.0 | all | `ham/integrations/storage/*` |
| S2.4b | **Media domain.** Models, batch reservation under lock, complete/remove/reopen/view services, processing job (Pillow + pillow-heif + ffmpeg/ffprobe, EXIF removal, originals deleted), retention sweep for closed requests. Dockerfile adds ffmpeg and libheif. | ham-backend-engineer | S2.0; S2.4a (the local adapter is enough to start) | S2.2, S2.3 | `ham/media/*`, `Dockerfile` |
| S2.5 | **Notifications module.** `Notification`, `inapp` subscriber, `register_inapp`, attention registry, Inbox queries, read/acknowledge, urgent banner data; `identity.services.notification_recipients`. | ham-backend-engineer | S2.0 | S2.2–S2.4 | `ham/notifications/*`, one function in identity services |
| S2.6 | **Notification builders.** Requester emails (`ham/requester_portal/notifications.py`); leadership email and in-app (`ham/requests/notifications.py`, `ham/media/notifications.py`); urgent overrides preference; PII-free subject test. | ham-integrations-engineer | S2.2, S2.3, S2.5 | S2.7, S2.8 | the three `notifications.py` files |
| S2.7 | **Public screens (390 first).** Form (church code), verify code/link, secure page (status wording from navigation.md §5, summary, contact card, media card), TypeScript upload module (client-side duration check, presigned PUT, progress, retry), expired / new-link / find / invalid pages. | ham-frontend-engineer | S2.3; S2.4 for upload; UX specs | S2.8 | `views_requester.py`, `urls_requester.py`, `templates/requester/*`, `frontend/src/upload.ts` |
| S2.8 | **Leadership screens.** Nav + bottom nav, Requests list (urgent first, ref search), detail with right panel at ≥1024 px, PII hover card and panel with logged/not-logged labels, media gallery, reopen and cancel forms, duplicate panel, Home attention cards, Inbox (Needs response / Updates), urgent banner + acknowledge, intake-links screen. | ham-frontend-engineer | S2.2, S2.5; S2.4b for the gallery | S2.7 | `views_requests.py`, `views_inbox.py`, `urls_requests.py`, `urls_inbox.py`, `templates/requests/*`, `templates/inbox/*`, `web/nav.py` |
| S2.9 | **Assisted intake** (only if Q-025 is accepted). Staff form reusing the public form class, `staff_phone_call` verification, no link issued until an email is added. | ham-backend-engineer + ham-frontend-engineer | S2.2, S2.7 | — | `requests/services_assisted.py`, one template |
| S2.10 | **Jobs.** Draft purge, challenge purge, release of expired upload reservations, closed-request media retention (periodic, `ham.jobs.periodic_job`). | ham-rules-engineer | S2.3, S2.4b | S2.6–S2.8 | `ham/*/jobs.py` |

**S2.0 contents:**
- authz: `RequesterContext`, `SystemContext`, `Scope.OWN_REQUEST`, **every** new matrix action, `_AUDITED_ON_DENIAL` additions, regenerated `permission-matrix.md`.
- audit: `audit.record` principal branch and all new `labels.py` entries.
- platform: `ham.platform.otp` (move `_hash` / `_generate_code`; identity switches over; keys from `HAM_TOKEN_HMAC_KEYS`), `ham.platform.net.client_ip`, `ham.platform.storage` protocol and loader.
- integrations: `register_notification` becomes a list.
- empty apps with `apps.py`, `INSTALLED_APPS` and import-linter layers + `ignore_imports`.
- `web/urls.py` includes the three new `urls_*.py` stubs.
- the `requests` nav item with `built=False`.
- `submit_request` / `issue_link` signatures as stubs raising `NotImplementedError`, so S2.2 and S2.3 can code against each other.

**Order:**
1. S2.0 ∥ S2.1
2. S2.2 ∥ S2.3 ∥ S2.4a/b ∥ S2.5 (the UX designer's intake specs run in parallel with these)
3. S2.6 ∥ S2.7 ∥ S2.8 ∥ S2.10
4. S2.9 (if Q-025 is accepted)
5. ham-test-engineer
6. Reviews: privacy-security (reveal logging, token handling, uploads), prd-guardian, UX usability (Doris at 390 px with large font), UI visual QA.

Each slice uses its own database (e.g. `ham_s22`) per the backend conventions.

---

## 11. Test plan hooks (ham-test-engineer)

1. **Matrix oracle.** Add every new action to `tests/authz/generate_expected_matrix.py`, re-derived from §67/§68 + Q-009/Q-024/Q-048/Q-112 (not from code). Cases to add:
   - REQUESTER: own request vs another request (denied);
   - SYSTEM;
   - REQUESTER and SYSTEM denied `shell.use`;
   - ADM denied every `request.*`;
   - PL/TL denied (no projects yet);
   - IB cases for `request.cancel`, `request.create_assisted`, `notification.acknowledge`.
2. **Reveal logging:**
   - Director: no event;
   - Admin impersonating the Director: event with both identities;
   - AD, PAS, BRD: one event with field names and **no values**;
   - an audit-write failure returns no PII;
   - denied reveal is audited;
   - list and detail HTML never contain the seeded requester name, email, phone or street (grep assertion).
3. **Links:**
   - lookup by hash only (the DB holds no raw token; the ciphertext decrypts only with the key);
   - regenerating revokes the old link in the same transaction;
   - the partial-unique constraint holds;
   - validity boundaries with a time machine: open request; close + 7 d exactly / +1 s; regenerated after the end is 14 d; regenerated before the end follows the normal rule;
   - HMAC key rotation still resolves old links.
4. **Intake and anti-abuse:**
   - an unverified draft creates no request and no leadership notification;
   - honeypot and too-fast submissions get the identical response with no email;
   - each rate limit at N and N+1;
   - find-my-request responds identically (body and status) for known and unknown emails;
   - code lockout after 5 tries is audited;
   - drafts are purged at 24 h;
   - relationship-specific certification codes are required;
   - urgent without a justification is rejected.
5. **Duplicates:** table-driven normalization cases ("1400 N.W. Example Avenue Apt 2" = "1400 NW EXAMPLE AVE #2"); the job flags address, phone and email matches; a match never changes status except the normal move to Awaiting Approval; the panel is hidden without `request.history.view`.
6. **State machine:** every allowed edge, every forbidden edge, and the actor for each; terminal states set `closed_at` and `requester_access_ends_at`.
7. **Media:**
   - the 11th photo is refused, including two concurrent reservations (a threaded test);
   - a video over 2:00 is rejected with `too_long`;
   - output JPEGs have no EXIF or GPS;
   - the original is deleted after processing;
   - an HEIC fixture converts;
   - an expired presigned URL is refused;
   - a storage outage leaves the request intact and shows the friendly error (§70.3);
   - a reopened batch records who, the reason and when (§46).
8. **Outbox and notifications:**
   - payload schema test for each new event (no PII keys or values);
   - an urgent request emails every pastor even with `notify_email = false`;
   - leadership subjects contain only HAM #, category and the urgent flag;
   - a spam cancellation sends no requester email;
   - Inbox "Needs response" empties when the request leaves Awaiting Approval (computed, no stale rows).
9. **Audit coverage:** requester and system commands appear in `tests/audit/test_command_registry.py`; each writes exactly one event with `actor_type` requester or system and `project_id` = request id; a forced failure rolls back the change, the audit event and the outbox event together.
10. **Playwright** (390 / 768 / 1280):
    - Doris: opens the form → code read from the captured mailbox → secure page → uploads 2 photos + 1 video → status.
    - Pastor Ruth: signs in with TOTP → urgent banner → Requests → detail → reveal shows "viewing is logged" and writes an event.
    - Marcus: reveals with the "Leadership only" label and no event.
    - Expired link → new link.
11. **§77 harness:**
    - Steps 1, 2 and 3 become real tests. Step 3's "with photos/video" means uploading into the initial batch right after verification.
    - Step 28 gains a request-scoped assertion (requester actor recorded).
    - Step 30 gains a partial assertion (no requester PII in outbox, emails to leaders, logs or the audit CSV).
    - Step 4 stays skipped until step 3.

---

## 12. Out of scope for step 2

- Approvals, rejection, reconsideration, urgency certification and urgent-approval alerts (step 3).
- Answering HAM questions on the secure page (step 3, as a card provider).
- Search by requester name or address (§71; later, and it will count as a logged reveal).
- AI "substantially similar" text matching (step 11, as a suggestion only).
- Editing requester contact details, and requester self-withdrawal (leaders cancel with `requester_withdrew`).
- Public-use media consent (§48).
- Geocoding for area and distance (staffing step; third party, needs its own privacy review).
- The request-record retention job (step 10; the values stay Pending).
- Drive and SMS (seams only).

---

## 13. New PRD gaps (ready to paste)

Replacement proposed-default text for the existing Q-025 row:

| Q-025 | §7.1, §7.3 | With email-only verification (Q-019), how does a requester with no email verify for media upload or regenerate an expired link? | Leadership verifies by phone and records it / use a family member's email / SMS provider for codes only | The form accepts a helper's or family member's email ("yours or someone helping you"). With no email at all, the person calls the ministry phone; a Director, Assistant Director or pastor enters the request and records "verified by phone call" (audited, blocked while impersonating). These requests get no secure link until an email is added; photos are taken at the site assessment; updates are given by phone | Open |

| ID | PRD § | Question | Options | Proposed default | Status |
|---|---|---|---|---|---|
| Q-099 | §6.1 | Which intake fields are required? §6.1 lists email and mobile "at minimum", but some requesters have no email or no mobile | Everything in §6.1 required / core required, rest optional | Required: name, email (own or a helper's), one phone (mobile preferred, landline accepted), service address, relationship, property type, description, certifications. Optional: urgent (justification required if ticked), hazards, availability, contact preference, media | Open |
| Q-100 | §6, §7.1 | Must the requester verify their email before the request is submitted, or only before uploading media? | Verify before submitting / submit, verify later | Verify before submitting: nothing unverified reaches leaders (spam protection, §3.1) | Open |
| Q-101 | §6.2 | How is a tenant's "written authorization from the owner/landlord before work begins" confirmed? | Requester certifies / upload required / leader records seeing it | At intake the tenant acknowledges the duty; before work, the homeowner service agreement (§41) includes the tenant's certification that written permission was obtained. No upload (§6.2 "certification is sufficient") | Open |
| Q-102 | §6.2, §41 | Exact wording of the intake certifications and how it's versioned | Draft in plan §0 D3 / church counsel wording | Short statements in plan §0 D3, reviewed by the owner (ideally counsel); versioned in code; each request stores the version and the statement codes accepted | Open |
| Q-103 | §7.3 | If a requester asks for a new link *before* normal access ends (lost link), how long does it last? | Always 14 days / same as the normal link | Same as the normal link (until 7 days after completion); the 14-day lifetime applies to links regenerated after normal access ended. Either way the old link dies and it's logged | Open |
| Q-104 | §7.3, §52 | When does link access end for requests that close without completing (Cancelled, final Rejected, Not Executable)? | Immediately / 7 days after closing / never | 7 days after closing (mirrors completion), then self-regenerate for 14 days | Open |
| Q-105 | §7.2, §35, Q-033 | Should every email to a requester include their secure link? | Yes (link stored encrypted so it can be re-sent) / only the first email | Yes; subjects stay neutral; the link is looked up by keyed hash and kept encrypted for re-sending | Open |
| Q-106 | §6 | What are "church-issued links/codes"? | The same form URL / a short code recording who shared it / codes that skip verification | The same form with an optional 6-character code recording the source (e.g. "Outreach flyer"); codes grant nothing extra; Director/AD create and deactivate them | Open |
| Q-107 | §6.1, §51.1, §65 | Should the form ask what kind of help is needed (a category), since lists, emails and calendar titles identify work by "HAM # + category"? | No / one required select | One required select: Plumbing, Electrical, Roof, Carpentry & repairs, Accessibility, Painting, Yard & outdoor, Other; leaders can change it at assessment | Open |
| Q-108 | §8, §35, §64 | Who is notified of a new (non-urgent) request, and how? | Approvers only / all leadership; in-app / email | In-app to Director, AD, pastors and Board rep; email follows each person's email preference | Open |
| Q-109 | §9 | What counts as a possible duplicate, and can leaders dismiss the alert? | Address/phone/email/name matches; dismiss / no dismiss | Flag same address (with unit), phone, email, or name + ZIP against all earlier requests; show outcome, reason and history; no dismiss in V1 | Open |
| Q-110 | §52 | What's the difference between Submitted and Awaiting Approval? | Automatic after intake checks / a leader screens first | Automatic: Submitted while the duplicate check runs (seconds), then Awaiting Approval; no manual screening step | Open |
| Q-111 | §52 | Who may close (Cancel) a request before approval, e.g. spam or a phone withdrawal, and is the requester told? | Director/AD / approvers too; always notify / not for spam | Director and AD, with a reason code (spam, requester withdrew, duplicate submission, other); requester gets a kind note except for spam; blocked while impersonating | Open |
| Q-112 | §4.11, §67, §68 | Can the Administrator see requests? (navigation.md's table shows "View") | No / list without personal details / full | No request access; troubleshooting through impersonation (logged with both identities) | Open |
| Q-113 | §67, §68, Q-009, Q-024 | Can pastors and the Board rep reveal requester details on every request, or only ones awaiting a decision? | All requests (logged) / only pre-decision | All requests, every reveal logged (Q-024); revisit if the log shows misuse | Open |
| Q-114 | §45, §46, §7.2 | When does the initial photo batch close, and can a requester remove a photo they uploaded by mistake? | When full / at decision / never; remove yes/no | Stays open until full or until the request is decided or closed; requesters may remove their own items while the batch is open (the slot is freed) | Open |
| Q-115 | §69, §45 | Per-file size limits and accepted formats for requester uploads | Various | Photos up to 25 MB (JPEG, PNG, HEIC, WebP); videos up to 500 MB (MP4, MOV), still at most 2 minutes | Open |
| Q-116 | §68, §47, §58 | How long are request records and requester personal details kept? | Forever / 7 years / 3 years after closing; spam sooner | 7 years after closing, then erase name, email, phone and street (keep ZIP, category, outcome); requests closed as spam are erased after 90 days | Open |
| Q-117 | §47, §68 | Retention for unfinished (unverified) forms and for media on Cancelled requests | Various | Unverified forms erased after 24 h; media on Cancelled requests follows the §47 photo (90 d) / video (30 d) clock from cancellation | Open |
| Q-118 | §68, §78 | How is requester personal data protected at rest? | Database/disk encryption + encrypted backups / also per-field encryption | Disk encryption (Render) + encrypted off-site backups; per-field encryption only for unfinished forms and stored link copies (keeps §71 search possible) | Open |
| Q-119 | §69 | Must uploads be virus-scanned? | Antivirus service / re-encode and never serve originals | Re-encode every photo and video, strip metadata (including GPS), delete originals, and serve only HAM-made copies; no antivirus service in V1 | Open |
| Q-120 | §6, §70 | Public-form abuse limits | Various | 10 new forms per IP per hour; 3 submitted requests per email per day; 20 find-my-request tries per IP per hour; code limits as for sign-in (Q-070) | Open |
| Q-121 | §10, §35, §4.3 | Who is alerted when an urgent request arrives (before a pastor certifies it), and does it override preferences? | Pastors only / pastors + Director/AD; override or not | All pastors by email + in-app urgent banner regardless of preference (§35); Director and AD get an in-app update. Certification and urgent-approval alerts come with step 3 | Open |
| Q-122 | §67, Q-081 | Q-081 exact scope wiring for `requester_pii.reveal` | — | Step 2: Director, AD, pastors, Board rep on any request (Director not logged unless impersonated); Project/Task Leaders are added through `LEADS_PROJECT`/`LEADS_TASK` when projects and tasks exist (steps 4–5) | Open (closes Q-081 on acceptance) |
| Q-123 | §66, §52, §58 | Should an approved project reuse its request's ID and number (one "HAM #047" from intake to completion)? | Same ID and number / separate project number | Same UUID and number, so the audit "project" filter shows the full history from intake | Open |
| Q-124 | §6.1, §35, §75 | What does "preferred communication method" mean when HAM itself sends only email in V1? | Email / phone call / text (text = a leader texts personally) | Store email, phone call or text as a preference for leaders; HAM's automatic messages go by email, or by phone call from a leader for phone-only requests | Open |

---

**Notes for the caller**
- I have no file-write access, so nothing was written. Please save this as `docs/architecture/intake.md`, and paste the Q-025 replacement text plus rows Q-099 to Q-124 into `docs/prd-open-questions.md`.
- Please also save these lines to `.claude/agent-memory/ham-architect/decisions.md`:
  - Step 2 (intake) plan is `docs/architecture/intake.md`. New modules: `ham/requester_portal`, `ham/media`, `ham/requests`, `ham/notifications`. Layers: web > requester_portal > (projects later) > media > requests > notifications > identity > authz > audit > outbox > platform > rules.
  - Requester and system writes use `@command` with `RequesterContext` / `SystemContext` (pseudo-roles REQUESTER/SYSTEM, `Scope.OWN_REQUEST`); `audit.record` sets `actor_type`.
  - Requester links: lookup by HMAC hash (`HAM_TOKEN_HMAC_KEYS`, not `SECRET_KEY`), plus a Fernet ciphertext so emails can re-send the link; one live link per request (partial unique).
  - PII reveal goes only through `requests.services.reveal_requester_pii` (HTMX partial), logged unless Director and not impersonating. Leadership pages never embed requester name, address or contact.
  - Home/Inbox "Needs response" is computed by attention providers; Notification rows are only the Updates log and urgent acknowledgements.
  - Project id = request id; audit `project_id` = request id from intake onward.
  - Object storage goes through `ham.platform.storage` (backend loaded from settings; second exception to "integrations only through the outbox"). Email builder registry allows several builders per event type.
- Step-1 files this plan changes, all in slice S2.0:
  - `/home/user/HAM/ham/authz/matrix.py`, `context.py`, `commands.py`
  - `/home/user/HAM/ham/audit/services.py`, `labels.py`
  - `/home/user/HAM/ham/identity/authn.py` (moves its hash and code helpers to `ham/platform/otp.py`)
  - `/home/user/HAM/ham/integrations/email/notifications.py`
  - `/home/user/HAM/ham/authz/nav.py`
  - `/home/user/HAM/ham/web/urls.py`
  - `/home/user/HAM/pyproject.toml`
  - `/home/user/HAM/config/settings/base.py`
- The ADR said object storage is "needed from step 2". Media processing on the worker needs ffmpeg in the Docker image and probably a bigger worker instance (about 2 GB RAM) for 2-minute videos. That is a small hosting cost the owner should know about.