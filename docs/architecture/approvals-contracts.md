# HAM step 3 (Approvals) — S3.0 contracts

Owner: ham-backend-engineer (S3.0). Built against `docs/architecture/approvals.md` (the plan;
its **Owner decisions and reconciliation** box overrides the body) and
`docs/prd-open-questions.md` Q-153-Q-176.

This file is the exact-names reference so S3.1-S3.7 (running in parallel) can code against
each other without waiting, mirroring `docs/architecture/intake-contracts.md`'s role for step
2. Nothing here is a new product decision — it is approvals.md's plan, as amended by its own
owner-decisions box, turned into literal model fields, function signatures and matrix action
names. Where the box and the plan body disagree, this file follows the box (noted at each such
spot below).

## 1. Models (`ham/requests/models.py`, migration `requests/0004`)

All three new models plus the `AssistanceRequest` additions and the two fixed CHECKs are in
**one** migration (`0004_approval_reconsideration_requestquestion_and_more`), so S3.1-S3.7
never collide on a `requests` migration of their own.

### 1.1 `AssistanceRequest` additions

| Field | Type | Notes |
|---|---|---|
| `urgency_reviewed_at` | `DateTimeField`, null | set by CERTIFY_URGENCY / DECLINE_URGENCY (S3.1/S3.2) |
| `urgency_reviewed_by_user_id` | `UUIDField`, null | ditto |
| `reconsideration_deadline_at` | `DateTimeField`, null | Q-155/Q-174: set once, on the first REJECT, in UTC; never recomputed later |

### 1.2 `Approval` (`requests_approval`) — the decision record

At most one **live** (not-undone) row per `(request, stage)` — `stage` is
`initial`/`reconsideration` (`ApprovalStage`), so at most two *live* rows per request ever
exist (D1/Q-153 "first decision settles it", §8.4 "the one reconsideration"). Enforced by
`approval_unique_live_stage`, a **partial** unique index:
`UniqueConstraint(fields=["request", "stage"], condition=Q(undone_at__isnull=True))` — **not**
a plain `UNIQUE(request, stage)`.

**Coordinator correction (2026-09-29), Q-156/Q-176:** undo's whole purpose is that the
request returns to its prior state and *any* eligible approver — including the same person —
may record a fresh decision for that stage; undo is not merely a marker on an otherwise
still-blocking row. A plain `UNIQUE(request, stage)` (what this slice originally shipped)
would have permanently blocked a second decision for a stage the instant its first row was
ever undone, which is backwards from what undo is for. The partial index above only
constrains rows where `undone_at IS NULL`, so an undone row frees its `(request, stage)` slot
for exactly one new live decision, while still refusing two *simultaneously live* decisions
for the same stage (Q-176 "other approvers can't decide during the window" — see §9 for how
this and §4's held-effects design interact).

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID7Field` (PK) | |
| `request` | FK → `AssistanceRequest`, `related_name="approvals"` | |
| `stage` | `ApprovalStage` | `initial` \| `reconsideration` |
| `outcome` | `ApprovalOutcome` | `approved` \| `rejected` |
| `route` | `ApprovalRoute` | `pastoral` \| `board` (Q-164: chosen at decision time, never preselected) |
| `decided_by_user_id` | `UUIDField` | |
| `decided_at` | `DateTimeField` | |
| `effective_at` | `DateTimeField` | `= decided_at + RULES.approvals.DECISION_UNDO_WINDOW`, computed **once** at write time and stored (never recomputed from the live rule) — see §4 "Held effects" |
| `board_decided_on` | `DateField`, null | Q-163; required when `route=board` |
| `reason_code` | `RejectionReason`, blank | required when `outcome=rejected` |
| `reason` | `TextField`, blank — **C** | the rejection message the requester reads, or the reconsideration-stage reason (required either way at that stage, shown to the requester only when `outcome=rejected`) |
| `approval_note` | `TextField`, blank — **C** | Q-169: optional one-line "Why approved (leaders only)", approval only |
| `urgent_approval` | `BooleanField` | requires `outcome=approved` |
| `took_over_from_user_id` | `UUIDField`, null | Q-157 |
| `unavailable_confirmed` | `BooleanField` | Q-157's required tick; must be true whenever `took_over_from_user_id` is set (set once, at insert — not a `ONCE_FIELDS` entry) |
| `requester_phoned_at` / `requester_phoned_by_user_id` | `DateTimeField`/`UUIDField`, null | Q-159; **`ONCE_FIELDS`**, set together, once, from null |
| `undone_at` / `undone_by_user_id` | `DateTimeField`/`UUIDField`, null | Q-156/Q-176; **`ONCE_FIELDS`**, set together, once, from null |
| `effects_ran_at` | `DateTimeField`, null | held-effects job idempotency marker (§4); **`ONCE_FIELDS`**, set once |

Constraints: `UNIQUE(request, stage) WHERE undone_at IS NULL` (partial, see above);
`outcome=rejected ⇒ reason_code≠'' AND reason≠''`;
`stage=reconsideration ⇒ reason≠''`; `urgent_approval ⇒ outcome=approved`;
`route=board ⇒ board_decided_on IS NOT NULL`; `took_over_from_user_id IS NOT NULL ⇒
unavailable_confirmed`; `undone_at`/`undone_by_user_id` set together; `requester_phoned_at`/
`requester_phoned_by_user_id` set together.

Append-only (`AppendOnlyOnceMixin`, generalizes `RequestContactVerification`'s single-field
guard): any `save()` after insert must pass `update_fields=[...]` naming only fields in
`Approval.ONCE_FIELDS` (`requester_phoned_at`, `requester_phoned_by_user_id`, `undone_at`,
`undone_by_user_id`, `effects_ran_at`), and each may only move from its empty/null default —
never back, never twice. `delete()` always raises.

Retention (Q-127/Q-145): `Approval.objects.erase_text_for_retention(request)` blanks
`reason`/`approval_note` only — `reason_code`/`outcome`/`route`/dates/ids are kept for
reporting. Declared here (S3.0); not yet called from `purge_expired_request` (S3.2 wires it).

### 1.3 `Reconsideration` (`requests_reconsideration`)

One row per request, ever (`OneToOneField` to `AssistanceRequest`, DB-enforced). Fully
immutable after insert (`ONCE_FIELDS` empty — any `save()` after insert raises). Its
*decision* is the separate `Approval(stage=reconsideration)` row, matched by
`request_id` — never linked by FK, so both rows stay independently immutable.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID7Field` (PK) | |
| `request` | `OneToOneField` → `AssistanceRequest`, `related_name="reconsideration"` | |
| `requested_at` | `DateTimeField` | |
| `requested_via` | `RequesterChannel` | `secure_page` \| `phone` |
| `recorded_by_user_id` | `UUIDField`, null | phone only; required when `requested_via=phone` |
| `requester_note` | `TextField`, blank — **C** | Q-158, ≤1000 chars (form-level) |
| `route` | `ApprovalRoute` | copied from the rejection being reconsidered |
| `original_decider_user_id` | `UUIDField` | |

Retention: `Reconsideration.objects.erase_text_for_retention(request)` blanks
`requester_note` only.

### 1.4 `RequestQuestion` (`requests_question`)

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID7Field` (PK) | |
| `request` | FK → `AssistanceRequest`, `related_name="questions"` | |
| `asked_by_user_id` / `asked_at` | | |
| `question` | `TextField` — **C** | ≤500 chars (form-level); **never edited**, not in `ONCE_FIELDS` |
| `answer` | `TextField`, blank — **C** | ≤1000 chars (form-level, owner box; `ANSWER_MAX_LENGTH`); `ONCE_FIELDS`, written once |
| `answered_at` / `answered_via` / `answer_recorded_by_user_id` | | `ONCE_FIELDS`, set together with `answer` |
| `closed_at` / `close_reason` / `closed_by_user_id` | | `ONCE_FIELDS`; `close_reason` is `QuestionCloseReason` (`withdrawn` \| `request_closed`) |

Status is derived, never stored: open = no answer and not closed; answered; closed. Index
`(request) WHERE answered_at IS NULL AND closed_at IS NULL` drives "Waiting on requester".
Constraints: `answer≠'' ⇔ answered_at IS NOT NULL`; never both `answered_at` and `closed_at`
set. Retention: `RequestQuestion.objects.erase_text_for_retention(request)` blanks
`question`/`answer` only.

### 1.5 Vocabularies (`ham/requests/models.py`)

`ApprovalStage`, `ApprovalOutcome`, `ApprovalRoute`, `RejectionReason` (the five Q-154 codes:
`family_or_others_can_help`, `owner_or_landlord_responsible`, `not_help_ham_offers`,
`couldnt_confirm`, `another_reason`), `RequesterChannel` (`secure_page`/`phone`, shared by
`Reconsideration.requested_via` and `RequestQuestion.answered_via`), `QuestionCloseReason`.

### 1.6 Fixed step-2 bugs (approvals.md §2.1)

- `req_closed_at_when_terminal` (was a tautology — always true, constrained nothing) is
  **removed**, replaced by two real `CHECK`s: `req_closed_at_set_when_cancelled` (`status =
  CANCELLED ⇒ closed_at IS NOT NULL`) and `req_closed_at_null_while_open` (`status IN
  (NEEDS_PHONE_CHECK, SUBMITTED, AWAITING_APPROVAL, RECONSIDERATION_PENDING, APPROVED) ⇒
  closed_at IS NULL`). `REJECTED` is the only status allowed either way (Q-116).
  `ham/requests/management/commands/seed_dev_requests.py` needed a matching fix (it used to
  `create()` a CANCELLED row open, then close it in a follow-up `.save()` — that now fails on
  the initial insert; fixed to pass `closed_at`/`cancel_reason_code` into the one `create()`
  call).
- `ham.requests.services.is_request_open(request_id)` now checks `closed_at IS NULL` directly
  instead of `not is_terminal(status)` (`TERMINAL_STATUSES` only ever named `CANCELLED`, so a
  *final* REJECTED request used to read as still "open").
- Regression tests: `tests/requests/test_step3_bug_fixes.py`.

## 2. Service seams (`NotImplementedError` stubs today)

`ham/requests/services_decisions.py` (S3.2 implements) and
`ham/requests/services_questions.py` (S3.3 implements) — new files, not appended to
`ham/requests/services.py`, so parallel edits to that file don't collide with either slice.
Every function below takes `ActorContext`/`RequesterContext`/`SystemContext` as documented
in `intake-contracts.md` §1 and is **not yet** `@command`-wrapped (the matching
`ham.authz.matrix` action codes are listed in `tests/audit/test_command_registry.py`'s
`PLACEHOLDER_ACTIONS` for this reason).

```python
# ham/requests/services_decisions.py
def approve_request(ctx, *, request_id, route, board_decided_on=None, certify_urgent=False) -> Approval: ...
def reject_request(ctx, *, request_id, route, reason_code, message, board_decided_on=None) -> Approval: ...
def review_urgency(ctx, *, request_id, certify: bool) -> AssistanceRequest: ...
def request_reconsideration(ctx: RequesterContext, *, note="") -> None: ...
def record_reconsideration_by_phone(ctx, *, request_id, note="") -> None: ...
def decide_reconsideration(ctx, *, request_id, approve: bool, reason, reason_code="", take_over=False) -> Approval: ...
def finalize_rejection(ctx: SystemContext, *, request_id) -> None: ...
def record_decision_phoned(ctx, *, request_id) -> None: ...
def change_category(ctx, *, request_id, need_category) -> None: ...
def undo_decision(ctx, *, approval_id) -> Approval: ...
```

```python
# ham/requests/services_questions.py
def ask_question(ctx, *, request_id, question, phone_answer="") -> RequestQuestion: ...
def answer_question(ctx: RequesterContext, *, question_id, answer) -> None: ...
def record_phone_answer(ctx, *, question_id, answer) -> None: ...
def withdraw_question(ctx, *, question_id) -> None: ...

# The one REAL (non-stub) function in this seam — see §4 "Auto-close on decision".
def close_open_questions(request_id, *, reason) -> int: ...
```

`close_open_questions` is implemented today (S3.0), not a stub: it is a **plain function**,
not `@command`-wrapped, always called from *inside* another command's own transaction (a
decision, a cancel) as one of that command's own side effects — never a standalone
consequential action of its own. It withdraws every open (unanswered, not yet closed)
question on `request_id`, setting `close_reason` to the `QuestionCloseReason` value passed in
(`request_closed` for the auto-close path) and leaving `closed_by_user_id` null (no single
human actor "did" this — the calling command's own audit event is the record of what caused
it). Returns the number of questions closed. Tested in
`tests/requests/test_services_questions_seam.py`.

## 3. Authorization (`ham/authz/matrix.py`)

Fourteen new matrix actions (thirteen from approvals.md §3, plus `request.decision.undo`).
**Owner box overrides applied** (not approvals.md §3's own table where they differ):
`request.category.change` is **Director/AD only** (not also Pastor/Board rep) and **not**
blocked while impersonating (Q-109). Every decision/undo/question/phone action **is** blocked
while impersonating (Q-172).

| Action | Allowed | Scope | Blocked while impersonating | Audited on denial |
|---|---|---|---|---|
| `request.approve` | PAS, BRD | ANY | yes | yes |
| `request.reject` | PAS, BRD | ANY | yes | yes |
| `request.decision.undo` | PAS, BRD | ANY | yes | yes |
| `request.urgency.review` | PAS | ANY | yes | yes |
| `request.reconsideration.decide` | PAS, BRD | ANY | yes | yes |
| `request.reconsideration.record_phone` | DIR, AD | ANY | yes | yes |
| `request.decision.record_phoned` | DIR, AD | ANY | yes | yes |
| `request.question.ask` | DIR, AD, PAS, BRD | ANY | yes | no |
| `request.question.record_answer` | DIR, AD, PAS, BRD | ANY | yes | no |
| `request.question.withdraw` | DIR, AD, PAS, BRD | ANY | yes | no |
| `request.category.change` | DIR, AD | ANY | **no** (Q-109) | no |
| `requester.question.answer` | REQUESTER | OWN_REQUEST | — | — |
| `requester.reconsideration.request` | REQUESTER | OWN_REQUEST | — | — |
| `system.request.finalize_rejection` | SYSTEM | ANY | — | — |

Finer rules the matrix can't express (enforced/tested in the service or `states.py`, per
approvals.md §3): route vs. held role; original pastor or explicit takeover
(`may_decide_reconsideration`, S3.1); only the asker/DIR/AD may withdraw a question; only the
person who *recorded* a decision may undo it, and only before `effective_at`; an
impersonating Administrator never unmasks (Q-151, unchanged from step 2).

`_AUDITED_ON_DENIAL` (`ham/authz/commands.py`) gained: `request.approve`, `request.reject`,
`request.decision.undo`, `request.urgency.review`, `request.reconsideration.decide`,
`request.reconsideration.record_phone`, `request.decision.record_phoned`. Question actions
and `request.category.change` are **not** added (approvals.md §3: "no" in that column).

**Independent oracle** (`tests/authz/generate_expected_matrix.py`): the fourteen rows above
added to `ORACLE`/`PSEUDO_ORACLE`, typed from PRD §4.2/§4.3/§8/§10/§67 and the decided Q-153–
Q-165/Q-172 rows, not copied from the matrix. Regenerate after any further change:
`PYTHONPATH=. python tests/authz/generate_expected_matrix.py`, then
`python manage.py build_permission_matrix` for `docs/architecture/permission-matrix.md`.

## 4. Held effects (undo, Q-156/Q-176)

**Design: a scheduled job, not an outbox/effects table.** Every decision command
(`approve_request`, `reject_request`, `decide_reconsideration`, and `review_urgency` when it
makes urgency "urgent approval") computes `effective_at = decided_at +
RULES.approvals.DECISION_UNDO_WINDOW` and stores it on the `Approval` row, then (S3.2) defers
one job — `run_held_decision_effects(approval_id)` — for `effective_at`, mirroring
`ham.requests.jobs.defer_complete_intake_checks`'s existing "defer a job for later, from
inside the same transaction as the row write" shape.

When that job runs, it:
1. re-fetches the `Approval` row;
2. if `undone_at` is **not** null, does nothing (the decision was undone before its effects
   ever ran) — write `effects_ran_at` anyway, so a retried/duplicate job invocation is
   provably a no-op either way (idempotency);
3. otherwise, if `effects_ran_at` is already set, does nothing (already ran — idempotency
   against a duplicate job invocation);
4. otherwise, runs the held effects and sets `effects_ran_at`:
   - the requester email (E8/E8r/E9/E9f, S3.5) — never sent before this point;
   - closes open media batches (`ham.media.subscribers`, S3.4) — via the existing
     `RequestApproved`/`RequestRejected` outbox subscriber, which S3.2's decision command
     only emits **at `effective_at`**, not at decision time (see below);
   - `close_open_questions(request_id, reason="request_closed")` (§2, S3.0);
   - the "decision" in-app update to other leaders (Q-168, S3.5).

**Consequence for outbox timing:** `RequestApproved`/`RequestRejected`/
`RequestReconsiderationDecided`-equivalent events that drive held effects are emitted by the
held-effects job at `effective_at`, **not** by the deciding command at `decided_at` — the
normal `@command` pattern ("outbox emits in the same transaction as the audit event") does
not apply to these specific events for this reason; the deciding command's own audit event
(`request.approved`/`request.rejected`/...) still fires immediately, at `decided_at` (§3.3:
every consequential action is audited when it happens, undo or not — only the *side effects*,
not the audit trail, are held).

**Not held (Q-176, safety, §3.5):** the urgent-approval alert to Director/AD
(`UrgencyCertified`/`RequestApproved` with `urgent_approval=True`) is emitted **immediately**,
at decision time, by the deciding command itself, through the normal `@command` outbox path —
never through the held-effects job. On undo, the deciding command's `undo_decision` (S3.2)
emits a *separate*, immediate `RequestDecisionUndone` event; S3.5's leadership notification
builder turns an undo of an already-alerted urgent approval into the Q-176 in-app "urgent
approval was undone" follow-up (a normal, unheld outbox subscriber reaction — not part of the
held-effects mechanism above).

**During the window:** while the pending `Approval` row is still live (`undone_at IS NULL`),
`decide_reconsideration`/`approve_request`/`reject_request` refuse a second decision on the
same `(request, stage)` — `approval_unique_live_stage`'s partial unique index already
enforces this at the DB level for any *live* row. Q-176's "other approvers can't decide
during the window" is therefore automatic, not a separate check. `undo_decision` does **not**
delete or blank the undone row — it only sets `undone_at`/`undone_by_user_id` (its
`ONCE_FIELDS`) — but doing so *does* free the `(request, stage)` slot: once undone, a fresh
`approve_request`/`reject_request`/`decide_reconsideration` call for that same stage is an
ordinary insert and succeeds (coordinator correction, 2026-09-29 — see §9). This is exactly
what makes undo a genuine "fix a mistake and let it be re-decided", not merely a "mark this
wrong" flag on an otherwise permanently-blocking row.

## 5. Audit (`ham/audit/labels.py`)

New `ACTION_GROUPS` entries "Approvals" (`request.approved`, `request.rejected`,
`request.decision_undone`, `request.reconsideration_requested`,
`request.reconsideration_decided`, `request.rejection_finalized`,
`request.urgency_certified`, `request.urgency_not_certified`, `request.category_changed`,
`request.decision_phoned`) and "HAM questions" (`request.question_asked`,
`request.question_answered`, `request.question_withdrawn`). Matching `ACTION_LABELS` entries
added. `request.approved`/`.rejected`'s `after` carries `route`, `stage`, `reason_code`,
`urgent_approval`, `approval_id` — **never** the message/note/reason text (Q-050, unchanged
convention from step 2's `requester_pii.reveal`).

## 6. Outbox events (IDs and codes only, `ham.outbox.validation` still applies)

| Event | Payload | Timing |
|---|---|---|
| `RequestApproved` | `request_id`, `stage`, `route`, `urgent_approval` | held (§4), except the urgent-approval alert path |
| `RequestRejected` | `request_id`, `stage`, `route`, `reason_code`, `final` | held (§4) |
| `RequestDecisionUndone` | `request_id`, `approval_id`, `stage` | immediate, at undo |
| `ReconsiderationRequested` | `request_id`, `reconsideration_id`, `route`, `via` | immediate |
| `RequestRejectionFinalized` | `request_id` | immediate (system job) |
| `UrgencyCertified` | `request_id`, `urgent_approval` | immediate (never held, §4) |
| `UrgencyNotCertified` | `request_id` | immediate |
| `RequestCategoryChanged` | `request_id`, `need_category` | immediate |
| `RequesterQuestionAsked` | `request_id`, `question_id` | immediate |
| `RequesterQuestionAnswered` | `request_id`, `question_id`, `via` | immediate |

## 7. Identity helper (`ham/identity/services.py`)

```python
def notification_recipients_for_users(user_ids: Iterable[uuid.UUID]) -> list[tuple[uuid.UUID, str, bool]]: ...
```

Same `(user_id, email, notify_email)` shape and "active, non-disabled only" rule as the
existing `notification_recipients(roles)`, but addressed by specific id (the original
decider, a question's asker, a batch's reopener) rather than by role set — for the step-3
notification builders (S3.5) that need to address *particular* people, not "everyone holding
role X". Unknown/inactive/disabled ids are silently skipped (never a recipient); input order
is preserved; duplicates collapse to one entry.

## 8. URL stubs (`ham/web/urls_requests_approvals.py`, `urls_requester_approvals.py`)

Two new, empty (`urlpatterns: list = []`) modules — not appended to the already-live
`urls_requests.py`/`urls_requester.py`, so a parallel edit to those files (S3.6/S3.7's own
screens) never collides with this one. Both are spliced into `ham/web/urls.py` already (a
no-op today, since both lists are empty). The exact names S3.2-S3.7 code against are
documented in each file's own module docstring (reproduced here as the single source of
truth — keep both in sync):

**Leadership** (`urls_requests_approvals.py`, S3.6 fills in against the existing
`views_requests.py`):

| URL name | Path | Screen(s) |
|---|---|---|
| `request_approve` | `requests/<uuid:request_id>/approve` | L12 |
| `request_reject` | `requests/<uuid:request_id>/reject` | L13 |
| `request_decision_undo` | `requests/<uuid:request_id>/decision/undo` | L2 |
| `request_certify_urgency` | `requests/<uuid:request_id>/urgency/certify` | L2 |
| `request_decline_urgency` | `requests/<uuid:request_id>/urgency/decline` | L2 |
| `request_reconsideration_decide` | `requests/<uuid:request_id>/reconsideration/decide` | L14 |
| `request_reconsideration_phone` | `requests/<uuid:request_id>/reconsideration/phone` | L18 |
| `request_decision_phoned` | `requests/<uuid:request_id>/decision/phoned` | L18 |
| `request_question_ask` | `requests/<uuid:request_id>/questions/ask` | L15 |
| `request_question_record_answer` | `requests/<uuid:request_id>/questions/<uuid:question_id>/answer` | L15, L16 |
| `request_question_withdraw` | `requests/<uuid:request_id>/questions/<uuid:question_id>/withdraw` | L16 |
| `request_category_change` | `requests/<uuid:request_id>/category` | L17 |

**Requester** (`urls_requester_approvals.py`, S3.7 fills in against the existing
`views_requester.py`; both sit under the existing token-scoped secure-page prefix):

| URL name | Path | Screen |
|---|---|---|
| `request_help_reconsider` | `request-help/r/<str:token>/reconsider` | R13 |
| `request_help_question_answer` | `request-help/r/<str:token>/questions/<uuid:question_id>/answer` | R14 |

## 9. Gaps found while building this seam (report to the orchestrator, not yet numbered)

- **RESOLVED (coordinator, 2026-09-29): undo + a genuine "decide again" after undo.** Was
  flagged here as a gap (the original `UNIQUE(request, stage)` blocked a second `Approval`
  row for the same stage forever once the first was ever undone). Ruling: undo's whole
  purpose is that the request returns to its prior state and any eligible approver, including
  the same person, may record a new decision for that stage. Fixed in §1.2 above:
  `approval_unique_live_stage` is a **partial** unique index
  (`condition=Q(undone_at__isnull=True)`), still in migration `requests/0004` (not a second
  migration, since it hadn't merged yet) — only *live* rows are unique per `(request, stage)`,
  so an undone row frees its slot for exactly one fresh live decision, while two
  simultaneously-live decisions for one stage are still refused. Regression test:
  `tests/requests/test_step3_models.py::TestApprovalConstraints::
  test_a_second_decision_is_allowed_once_the_first_is_undone` (confirmed to fail against the
  original plain `UNIQUE(request, stage)` and pass against the partial index) plus
  `test_two_live_decisions_for_one_stage_are_refused` (still refused). S3.2's `undo_decision`
  and the re-decide commands need no new mechanic beyond this constraint — a fresh
  `approve_request`/`reject_request`/`decide_reconsideration` call for the same stage after an
  undo is just an ordinary insert that now succeeds.
- **`RequestDecisionUndone`'s exact consumers.** approvals.md's own event table (§4) doesn't
  list an undo event at all (D4/"no undo" was the *plan's* original recommendation before the
  owner's Q-156 decision superseded it) — `RequestDecisionUndone` here is this slice's own
  naming, not copied from an existing table. S3.5 should treat the payload shape above as a
  proposal, confirmed at merge, not a locked contract.
