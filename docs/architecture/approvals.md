# HAM approvals: build-order step 3

Owner: ham-architect. Status: plan. Built on `docs/architecture/foundation.md` (step 1), `docs/architecture/intake.md` and `intake-contracts.md` (step 2), and the step-2 code now on `main`.

PRD trace: §3.2, §3.3, §4.2, §4.3, §5, §7.2 ("responses to HAM questions"), §8 (§8.1 Board route, §8.2 pastoral route, §8.3 rejection, §8.4 reconsideration), §9 (the approval or rejection reason now shows in the duplicate panel), §10 (certification, urgent approval, urgent-approval alerts), §35 (requester approval, rejection and additional-information emails; leadership in-app and email), §46 (batches close when a decision is made), §47 (the retention clock for rejected requests), §52 (the edges into Approved, Rejected and Reconsideration Pending), §58 (approvals, rejections, reconsiderations and status changes are audited), §59 and Q-048 (decisions are blocked while impersonating), §64 ("requests awaiting approval", "approved requests awaiting assessment"), §66 (Approval, Reconsideration), §67 (Pastor: "approval, urgent certification"; Board rep: "records Board decisions"), §68, §70.3, §70.6, §73 ("approval/rejection/reconsideration", "urgent approvals"), §76 ("auto-log administrative events"), §77 step 4.

Section mapping: the brief says "§11 rejection/reconsideration". In the PRD those are **§8.3/§8.4**. §11 is the mandatory site assessment, which belongs to step 4. §11's rule "approval authorizes assessment; it does not guarantee execution" appears in the approval copy below.

Decided Qs this plan relies on (final): Q-009, Q-024, Q-025, Q-030, Q-033, Q-048 (approval and decision actions blocked while impersonating), Q-050, Q-099, Q-100, Q-124 (Administrator: view-only, masked), Q-127.
Open Qs running on proposed defaults that this plan relies on: Q-101, Q-102, Q-106, Q-107, Q-109 (category change deferred to step 3), Q-116 (7-day access after a *final* close), Q-123, Q-126 (one ID/number for life), Q-128, Q-137, Q-138, Q-145, Q-150 (deferred to step 3), Q-151.

Out of scope (§73, §75): SMS, a requester account, background checks, AI suggestions for decisions, an automated Board budget workflow (§75), Drive, multilingual.

---

## 0. Decisions for the product owner that are costly to change later

Everything else here uses a sensible default logged as a Q-row in §9. These four shape stored records, so changing them after real decisions exist is expensive. **You make the final call on each.**

**D1. Does the first recorded decision settle the request, including a rejection? (Q-153)**
- The PRD says "only one authorized final approval is required" (§8.2). It says nothing about a pastor *rejecting* while the Board has the same request.
- Recommended: **the first decision recorded by any approver decides**, whether it's an approval or a rejection. Everyone else then sees "Decided by Pastor Ruth, Oct 3". If someone disagrees, the path is the one reconsideration (§8.4).
- Option (b): a rejection by one route doesn't close the request while the other route could still approve. That needs a "who else still has to weigh in" concept, which is the routing step the owner already dropped (Q-106).
- Why it's costly: every stored decision is either "the" decision or one of several. Switching later changes how old records read and what the requester was told.

**D2. What a rejected requester reads (Q-154)**
- §8.3 needs a "polite and compassionate explanation" plus "the rejection reason".
- Recommended: the approver picks **one reason from a short list** and HAM pre-fills a kind message for that reason. The approver may edit the message before sending, and it is required. The requester reads the message. Leaders and reports use the reason code.
- Draft reasons:
  - "It looks like this need can be met another way" (§5);
  - "This isn't the kind of work HAM can do";
  - "This work needs a licensed professional HAM can't provide";
  - "The home is outside the area HAM serves";
  - "Another reason".
- Options: (a) as recommended; (b) free text only (no reasons for reporting, and wording quality varies); (c) a code only, with fixed wording (not personal enough for §8.3).
- Why it's costly: reason codes are stored forever on decisions and feed the duplicate panel (§9) and reports. Renaming or merging codes later splits the history.

**D3. How long a requester can ask for reconsideration, and when a rejection becomes final (Q-155)**
- The PRD allows exactly one reconsideration but sets no deadline.
- Recommended: **30 days after the rejection.** After that HAM automatically marks the rejection final. That starts the 7-day link clock (Q-116) and the §47 photo (90-day) and video (30-day) deletion clocks. Until then the request stays open and nothing is deleted.
- Options: 14 / 30 / 60 days / no limit. With no limit, a rejected request never closes: photos are never deleted and retention never starts.
- Why it's costly: the deadline is printed in the rejection email ("you can ask until Nov 2"). HAM stores that date on the request, so changing the rule later only affects new rejections and the two sets of promises must both be honored.

**D4. Decisions can't be undone (Q-156)**
- Recommended: decisions are **permanent records**. There's a confirmation step before every decision, and no "undo".
  - A mistaken rejection is fixed through reconsideration.
  - A mistaken approval is caught at the mandatory site visit, where the Director can decide the work isn't feasible (§11, §12, step 4).
- Option: an "undo" within a few minutes by the same person. But the requester's email may already have gone out, and an undo button on an approval record weakens the audit story (§3.3).
- Why it's costly: once we promise decision records are permanent, adding undo later means rewriting the permanence rules and tests.

---

## 1. Scope

| Area | Step 3 builds | Later steps | Seam |
|---|---|---|---|
| Approve / reject (§8) | Pastor (pastoral route) and Board rep (Board route) decide on the existing detail page. First decision wins (D1). Confirmation step | — | `requests_approval` rows, append-only |
| Urgent (§10) | Pastor certifies or declines urgency. One-tap "Certify urgent and approve". Urgent-approval alerts go to Director/AD regardless of preference | Project Leader alerted "when assigned" (step 5) | `RequestApproved.urgent_approval`, `UrgencyCertified` |
| Rejection (§8.3) | Reason code + kind message (D2), requester email with the link, reconsideration deadline | — | `RequestRejected` |
| Reconsideration (§8.4) | Requester asks once on the secure page (or a Director/AD records a phone request). Routed to the Board rep or the original pastor, and another pastor may take over. Decision with a required reason. Window expiry job (D3) | — | `requests_reconsideration` (one per request, enforced by a unique constraint) |
| HAM questions (§7.2) | "Ask a question" (leaders), requester answers on the secure page, "Record an answer from a phone call", "Waiting on requester" list view, withdraw | PL/TL ask questions in steps 4–5 (add their roles then) | `requests_question` |
| No-email requesters (Q-025) | Director/AD "Call to share the decision" card + "Told them by phone"; reconsideration requested by phone | — | `Approval.requester_phoned_at/by` |
| Change category (Q-109) | Director, AD, pastor, Board rep; audited | Calendar title uses it (step 7+) | `RequestCategoryChanged` |
| Media (§46) | Open batches close on approve/reject. Reopen only allowed in Awaiting Approval, Reconsideration Pending or Approved. Q-150 "new photos arrived" notice | PL reopens (step 5) | media subscriber |
| Duplicate panel (§9) | Shows the prior decision outcome, reason and message | Assistance history (step 10) | `outcome_summary` |
| **Project creation** | **No `Project` table in step 3.** An approved request stays `APPROVED`, which is the last *request* status. Director/AD get the Home card "Approved: needs a site visit (n)" (§64) | **Step 4** adds `ham.projects` (layer between `requester_portal` and `media`) with `Project(id = request.id, reference_number = same, status = ASSESSMENT_REQUIRED, ...)`. It is created by (a) a data migration for every `APPROVED` request without a project, and (b) an internal outbox subscriber on `RequestApproved` using idempotent `get_or_create(pk=request_id)`. From then on the requester page reads the project status when one exists | `RequestApproved` (`stage`, `urgent_approval`). Audit `project_id` has been the request id since intake (Q-126) |

Why no Project now:
- A Project with no fields or behavior would be migrated twice.
- Step 4 knows what it needs: assessment, leader and schedule.
- Q-126 already fixes the identity, so the history lines up with no rework.
- `leader.project.assign` already takes a `project_id` and gets its first real target in step 4.

**Non-goals for step 3:**
- Site assessment scheduling.
- Project statuses beyond Approved.
- A Board batch-entry screen: Board decisions are recorded per request from the detail page. The UX designer may add a desktop list with a per-row "Record decision" link; there is no bulk action.
- Reminders or escalation for slow decisions (Q-166).
- Undo (D4).
- Pastors marking a request urgent that the requester didn't flag (Q-160).
- Requester self-withdrawal (Q-108 unchanged).
- AI.
- Comments (§57).

---

## 2. Domain model, state machines and rules of the flow

### 2.1 Data model (all ids UUIDv7, all timestamps timestamptz UTC; field classes P/C/S as in intake.md §3)

**AssistanceRequest** (`requests_request`), additions:
- `urgency_reviewed_at`, `urgency_reviewed_by_user_id`: set by certify or decline.
- `reconsideration_deadline_at`: set when the request is first rejected (decided_at + `RECONSIDERATION_REQUEST_WINDOW`), otherwise null. It is stored so the date printed in the email never shifts if the rule changes (D3).
- `closed_at` meaning is extended: `REJECTED` with `closed_at IS NULL` means the rejection can still be reconsidered; `REJECTED` with `closed_at` set means final (Q-116).
- **Fix a constraint bug.** `req_closed_at_when_terminal` is currently a tautology: `closed_at IS NULL OR status <> CANCELLED OR closed_at IS NOT NULL` is always true. Replace it with two CHECKs:
  - `status = CANCELLED ⇒ closed_at IS NOT NULL`;
  - `status IN (NEEDS_PHONE_CHECK, SUBMITTED, AWAITING_APPROVAL, RECONSIDERATION_PENDING, APPROVED) ⇒ closed_at IS NULL`.
  - `REJECTED` may be either.
- **Fix a service bug.** `ham.requests.services.is_request_open` uses `is_terminal(status)`, which will say a *final* rejection is still open. Switch it to `closed_at IS NULL`. Also add `states.is_closed(status, closed_at)` and use it everywhere "terminal" was used for access, media or retention.

**Approval** (`requests_approval`, §66). Append-only by a Python-level guard, the same pattern as `RequestContactVerification` (no DB trigger, per backend memory). Fields:
- `id`, `request_id` (FK).
- `stage`: `initial` | `reconsideration`.
- `outcome`: `approved` | `rejected`.
- `route`: `pastoral` | `board`.
- `decided_by_user_id`, `decided_at`.
- `board_decided_on` (date; Board route only, Q-163).
- `reason_code`: a `RejectionReason` code (D2); required when rejected, otherwise empty.
- `reason` **C**:
  - when rejected, the message the requester reads (required);
  - at the reconsideration stage, the "simple reason" (required either way, §8.4; shown to the requester only when the outcome is rejected);
  - otherwise empty.
- `urgent_approval` (bool, see §2.3).
- `took_over_from_user_id` (reconsideration takeover, Q-157).
- `requester_phoned_at`, `requester_phoned_by_user_id` (Q-159): the **only** columns the guard lets change, and only once, from null.
- Constraints:
  - UNIQUE `(request_id, stage)`: one first decision and at most one reconsideration decision, by design (§8.2, §8.4).
  - CHECK `outcome = rejected ⇒ reason_code <> '' AND reason <> ''`.
  - CHECK `stage = reconsideration ⇒ reason <> ''`.
  - CHECK `urgent_approval ⇒ outcome = approved`.
  - CHECK `route = board ⇒ board_decided_on IS NOT NULL`.
- The `RejectionReason` TextChoices live in `ham/requests/models.py` (the one vocabulary, like `NeedCategory`). Kind message templates per code live in `ham/requests/presentation.py`.

**Reconsideration** (`requests_reconsideration`, §66). Append-only, immutable after insert. Fields:
- `id`, `request_id` (UNIQUE: only one reconsideration, §8.4, enforced by the database).
- `requested_at`, `requested_via`: `secure_page` | `phone`.
- `recorded_by_user_id` (phone only).
- `requester_note` **C** (optional, ≤1000 characters, Q-158).
- `route` (copied from the initial rejection) and `original_decider_user_id`.
- Its decision is the `Approval` row with `stage = reconsideration` (derived, not linked, so both rows stay immutable).

**RequestQuestion** (`requests_question`, §7.2). Fields:
- `id`, `request_id`, `asked_by_user_id`, `asked_at`, `question` **C** (≤1000, immutable).
- `answer` **C** (≤2000), `answered_at`, `answered_via` (`secure_page` | `phone`), `answer_recorded_by_user_id` (phone).
- `closed_at`, `close_reason` (`withdrawn` | `request_closed`), `closed_by_user_id`.
- Status is derived:
  - open = no answer and not closed;
  - answered;
  - closed.
- Constraints:
  - CHECK `(answer = '' AND answered_at IS NULL) OR (answer <> '' AND answered_at IS NOT NULL)`;
  - CHECK `NOT (answered_at IS NOT NULL AND closed_at IS NOT NULL)`.
- Service guards: the answer is written once, and the question text is never edited.
- Index: `(request_id) WHERE answered_at IS NULL AND closed_at IS NULL`, which drives the "Waiting on requester" view.

**Retention (Q-127, Q-145).**
- `purge_expired_request` also blanks `Approval.reason`, `Reconsideration.requester_note`, `RequestQuestion.question` and `RequestQuestion.answer`.
- Each goes through one named manager method (`erase_text_for_retention`), the escape-hatch pattern from `RequestContactVerification`.
- Reason codes, outcomes, routes and dates are kept (outcome reporting).
- Spam purge deletes by cascade as today.

Text length limits are form validation constants in `ham/requests/forms` or services, not business rules. They don't go in the rules module.

### 2.2 Request state machine (edges added to `ham/requests/states.py`, rules-engineer)

| Action | From | To | Actor | Blocked while impersonating | Guard | Audit | Outbox |
|---|---|---|---|---|---|---|---|
| APPROVE | AWAITING_APPROVAL | APPROVED | PAS (route `pastoral`), BRD (route `board`) | yes (Q-048) | route matches a held role (Q-164) | `request.approved` | `RequestApproved` |
| REJECT | AWAITING_APPROVAL | REJECTED (open) | PAS, BRD | yes | reason code + message | `request.rejected` | `RequestRejected` (`final=false`) |
| REQUEST_RECONSIDERATION | REJECTED, `closed_at` null, now < deadline, no reconsideration yet | RECONSIDERATION_PENDING | REQUESTER (secure page); DIR, AD (by phone, Q-159) | yes (staff) | — | `request.reconsideration_requested` | `ReconsiderationRequested` |
| RECONSIDER_APPROVE | RECONSIDERATION_PENDING | APPROVED | Board route: BRD. Pastoral route: the original pastor, or another PAS with `take_over=True` (Q-157) | yes | reason required | `request.reconsideration_decided` | `RequestApproved` (`stage=reconsideration`) |
| RECONSIDER_REJECT | RECONSIDERATION_PENDING | REJECTED (**closes**: `closed_at`, access end) | same as above | yes | reason code + message | `request.reconsideration_decided` | `RequestRejected` (`final=true`) |
| FINALIZE_REJECTION | REJECTED, `closed_at` null, now ≥ deadline, no reconsideration | REJECTED (**closes**) | SYSTEM (hourly job) | — | — | `request.rejection_finalized` | `RequestRejectionFinalized` |
| CANCEL (extended) | + RECONSIDERATION_PENDING, APPROVED | CANCELLED | DIR, AD | yes | from these two states only the reason `requester_withdrew` (Q-165) | `request.cancelled` | `RequestCancelled` |

- `check_transition` gains inputs: `route`, `now`, `reconsideration_deadline_at`, `closed_at`, `has_reconsideration`, `is_original_decider`, `take_over`.
- It also gains refusals: `ROUTE_NOT_HELD`, `DEADLINE_PASSED`, `RECONSIDERATION_ALREADY_USED`, `NOT_YOUR_RECONSIDERATION` (only when `take_over` is false), `ALREADY_FINAL`.
- `TransitionDecision.closes_request` becomes true for RECONSIDER_REJECT and FINALIZE_REJECTION.
- A second approver acting at the same moment: every decision command does `select_for_update()` on the request, so the loser gets `WRONG_STATE`. The UI turns that into "Already decided by {name} at {time}" (D1).
- SUBMITTED (duplicate check running) can't be decided. That window is seconds.
- Entering a closing edge sets `closed_at` and `requester_access_ends_at = closed_at + REQUESTER_ACCESS_AFTER_CLOSE`, and auto-closes open questions (`close_reason = request_closed`) in the same transaction.

**Urgency sub-machine** (an attribute, §52; also in `states.py`)

| Action | Urgency from | Request status | To | Actor | Blocked while impersonating | Audit | Outbox |
|---|---|---|---|---|---|---|---|
| CERTIFY_URGENCY | AWAITING_CERTIFICATION, NOT_CERTIFIED | AWAITING_APPROVAL, APPROVED | CERTIFIED | PAS only (§10, §67) | yes | `request.urgency_certified` | `UrgencyCertified` |
| DECLINE_URGENCY | AWAITING_CERTIFICATION | AWAITING_APPROVAL | NOT_CERTIFIED | PAS only | yes | `request.urgency_not_certified` | `UrgencyNotCertified` |

**Urgent approval** is a pure function, `is_urgent_approval(status, urgency_status)`: true when the request is `APPROVED` **and** urgency is `CERTIFIED`, whichever happened second.
- The command that makes it true sets `Approval.urgent_approval = true` (approval path) or emits `UrgencyCertified` with `urgent_approval: true` (certify-after-approval path).
- Either way the §10 alerts fire exactly once.
- "Certify urgent and approve" is **one** command (`approve_request(..., certify_urgent=True)`, pastor only). It writes `request.urgency_certified` and emits `UrgencyCertified` by hand inside the same atomic block (the `complete_intake_checks` precedent, via `ham.outbox.api.emit`), then returns the `request.approved` result.

### 2.3 Approval rules
- **Who decides:** any pastor (pastoral route) or the Board rep recording the Board's decision (Board route) (§4.2, §4.3, §8). One decision is enough, and the first recorded one wins (D1).
- **Who does not decide:**
  - the Director and AD, who own feasibility, not eligibility (§5, §4.4, §12);
  - the Administrator (Q-124);
  - anyone while impersonating (Q-048).
- **A person holding both Pastor and Board rep** picks the route explicitly; the default is pastoral (Q-164). A Director who is also a pastor decides as a pastor.
- **History** (duplicate panel) is shown as information, never as an automatic "no" (§5, §9).
- **Reconsideration routing** (a pure function in `states.py`, `may_decide_reconsideration(route, actor_roles, actor_id, original_decider_id, take_over)`):
  - Board route: any Board rep.
  - Pastoral route: the original pastor.
  - Another pastor may decide only with an explicit "Take over from Pastor Ruth". This is recorded in `took_over_from_user_id`, and the original pastor gets an in-app update.
  - If the original pastor no longer holds an active Pastor role, every pastor sees it as theirs, and it still records `took_over_from_user_id` (Q-157).
- **Rejection message:** required, pre-filled per reason, and shown with the label "{First name} will read this" (D2).

### 2.4 Reconsideration flow
1. On rejection, the requester email and secure page show the message and an **Ask us to take another look** button, with "You can ask until {deadline, church time zone}".
2. The requester opens R13, adds an optional note ("Anything you'd like us to know?") and presses Send. The request moves to RECONSIDERATION_PENDING. The page says "We're taking another look at your request."
   - No extra code (Q-158: the forwarded-link risk is accepted).
   - No new photos unless a leader reopens uploads (§46).
3. No-email requester: they call, and a Director/AD records "Asked to reconsider by phone", with an optional note (Q-159).
4. The decider sees the reconsideration panel on the detail page (original decision, the requester's note, dates) and decides with a required reason.
   - Approve: APPROVED. The requester gets the "approved after taking another look" email.
   - Keep the rejection: final. The requester gets the kind "final" email with "You're welcome to send a new request in the future" (§8.4).
5. No request by the deadline: the hourly job finalizes. No email (the page simply drops the button).

### 2.5 HAM questions
- **Ask** (DIR, AD, PAS, BRD; any request that isn't closed, not NEEDS_PHONE_CHECK):
  - A question text of up to 1000 characters, with the hint "{First name}, and anyone they share their link with, will read this."
  - Email on file: the requester gets an "Update on your HAM #047" email with the question text and the link.
  - No email: the sheet says "Call {masked phone} to ask. Record their answer below." It creates the question and records the phone answer in one step, or leaves it open for a callback.
- **Answer:**
  - The requester answers once per question on the secure page (R14).
  - Staff can use **Record an answer from a phone call** (`answered_via = phone`).
  - The asker gets an in-app update "Answer received · HAM #047", plus email if their preference allows.
- **Withdraw:** the asker, Director or AD may withdraw an open question. The requester's card disappears and no email is sent.
- **Waiting on requester:** a list view (a filter in `/requests?view=waiting`) of requests with at least one open question, plus a chip on list rows and on the detail page.
  - It does not pause anything and does not block a decision. Approvers may decide anyway.
- **Reminders:** none in V1 (Q-162).
- **Administrator (masked view):** sees the question text and "Answered on {date}", but **not** answer text or reconsideration notes. Answers can carry contact details, the same reasoning as the step-2 masking of `contact_note` (Q-162, Q-151 pattern).

### 2.6 Change category (Q-109, closing its step-3 deferral)
- Who: DIR, AD, PAS, BRD, on any request that isn't closed.
- It's a select in the summary card's "Change" sheet. Audited `request.category_changed` with before and after codes. Emits `RequestCategoryChanged`.
- No requester notice. Not blocked while impersonating: it's an operational correction, not a decision (§59).

### 2.7 Media batches on decision
- `ham/media/subscribers.py` handles `RequestApproved` and `RequestRejected` by calling `close_open_batches(request_id, reason_code="request_decided")`. This is the existing `RequestCancelled` pattern.
- `reopen_batch` guard: the request must be in `AWAITING_APPROVAL`, `RECONSIDERATION_PENDING` or `APPROVED` and not closed. A rejection that can still be reconsidered can't be reopened until the requester asks. Implemented as `states.accepts_media_reopen(status, closed_at)`.
- Retention: the existing sweep already keys on `closed_at` for `REJECTED`, so the §47 clock starts at the **final** rejection (Q-155). Update only the metadata and sources on the rule; no value change.
- Q-150 (build now): a `ham/media/notifications.py` in-app builder on `RequestMediaStored`. When the item is the first one in a `reopened` batch, it sends "New photos arrived · HAM #047" to `batch.opened_by_user_id`.

---

## 3. Authorization

New matrix actions (`ham/authz/matrix.py`). None needs step-up: Q-046's list doesn't include them, and every actor already signed in with MFA (§60.1).

| Action | Allowed | Scope | Blocked while impersonating | Audited on denial | PRD / Q |
|---|---|---|---|---|---|
| `request.approve` | PAS, BRD | ANY | yes | yes | §4.2, §4.3, §8, §10, §67, Q-048, Q-153 |
| `request.reject` | PAS, BRD | ANY | yes | yes | §8.3, Q-048, Q-154 |
| `request.urgency.review` (certify / decline) | PAS | ANY | yes | yes | §10, §67, Q-048, Q-160 |
| `request.reconsideration.decide` | PAS, BRD (route and takeover checked in the service) | ANY | yes | yes | §8.4, Q-048, Q-157 |
| `request.reconsideration.record_phone` | DIR, AD | ANY | yes | yes | §8.4, Q-025, Q-159 |
| `request.decision.record_phoned` | DIR, AD | ANY | yes | yes | §8.3, Q-025, Q-159 |
| `request.question.ask` | DIR, AD, PAS, BRD | ANY | yes (it emails the requester in the target's name) | no | §7.2, Q-162 |
| `request.question.record_answer` | DIR, AD, PAS, BRD | ANY | yes | no | §7.2, Q-162 |
| `request.question.withdraw` | DIR, AD, PAS, BRD (service: the asker, or DIR/AD) | ANY | yes | no | §7.2, Q-162 |
| `request.category.change` | DIR, AD, PAS, BRD | ANY | no | no | Q-109 |
| `requester.question.answer` | REQUESTER | OWN_REQUEST | — | — | §7.2, Q-162 |
| `requester.reconsideration.request` | REQUESTER | OWN_REQUEST | — | — | §8.3, §8.4, Q-155, Q-158 |
| `system.request.finalize_rejection` | SYSTEM | ANY | — | — | §8.4, Q-155 |

- ADM, SMS, VOL, CON, PL and TL get none of these.
- The Administrator still sees decisions read-only through `request.view`, with masking as in §2.5.
- Six actions are added to `_AUDITED_ON_DENIAL`: approve, reject, urgency.review, reconsideration.decide, reconsideration.record_phone, decision.record_phoned.

Finer rules the matrix can't express are enforced in the service or `states.py` and tested there:
- route vs held role;
- original pastor or takeover;
- only the asker, Director or AD may withdraw;
- an Administrator who is impersonating gets the masked view, never unmasking answers (Q-151).

**Independent oracle.** Add the thirteen rows above to `ORACLE` / `PSEUDO_ORACLE` in `tests/authz/generate_expected_matrix.py`, typed from §4.2, §4.3, §8, §10, §67 and the Q-048/Q-153–Q-165 defaults, **not** copied from the matrix. Then regenerate `expected_matrix.csv` and `docs/architecture/permission-matrix.md`. Cases:
- PAS vs BRD split on `urgency.review` (§10 "a pastor must ... certify");
- DIR/AD denied approve and reject (§5);
- ADM denied everything except view;
- IB rows for every decision action;
- REQUESTER own vs other request for the two requester actions.

---

## 4. Audit, outbox events, notifications, attention

**Audit actions** (all added to `ham/audit/labels.py`; `project_id` = request id):
- Decisions: `request.approved`, `request.rejected`.
  - `after`: `route`, `stage`, `reason_code`, `urgent_approval`, `approval_id`.
  - **Never** the message text (Q-050).
- Reconsideration: `request.reconsideration_requested` (actor requester or staff; `via`), `request.reconsideration_decided` (`outcome`, `route`, `took_over`), `request.rejection_finalized` (system).
- Urgency: `request.urgency_certified`, `request.urgency_not_certified`.
- `request.category_changed` (before and after codes).
- Questions: `request.question_asked`, `request.question_answered` (actor requester, or staff with `via=phone`), `request.question_withdrawn`.
- `request.decision_phoned`.

**Outbox events** (IDs and codes only):

| Event | Payload |
|---|---|
| `RequestApproved` | `request_id`, `stage`, `route`, `urgent_approval` |
| `RequestRejected` | `request_id`, `stage`, `route`, `reason_code`, `final` |
| `ReconsiderationRequested` | `request_id`, `reconsideration_id`, `route`, `via` |
| `RequestRejectionFinalized` | `request_id` |
| `UrgencyCertified` | `request_id`, `urgent_approval` |
| `UrgencyNotCertified` | `request_id` |
| `RequestCategoryChanged` | `request_id`, `need_category` |
| `RequesterQuestionAsked` | `request_id`, `question_id` |
| `RequesterQuestionAnswered` | `request_id`, `question_id`, `via` |

The seams: step 4 project creation subscribes to `RequestApproved`, and step 5 PL alerts subscribe to `RequestApproved`/`UrgencyCertified`.

**Requester emails** (`ham/requester_portal/notifications.py`):
- Every one uses the subject "Update on your HAM #047" (neutral, Q-102), carries the link, and ends with the church contact line.
- None is sent when there's no email on file. Those requesters are handled by the Director/AD phone card below.

| Code | Event | Body gist |
|---|---|---|
| E8 | `RequestApproved` (initial) | "Good news: your request is approved. Next, someone from HAM will call you to arrange a visit to look at the work. The visit helps us plan; it doesn't yet promise the work can be done" (§11). Urgent: "...will contact you quickly." |
| E8r | `RequestApproved` (reconsideration) | "We took another look, and your request is now approved..." |
| E9 | `RequestRejected` (`final=false`) | Compassionate opener + the approver's message + "If you'd like us to take another look, open your page and choose *Ask us to take another look* by {deadline}." |
| E9f | `RequestRejected` (`final=true`) | "We took another look. We're very sorry, we aren't able to help with this request. {message}. You're welcome to send a new request in the future." |
| E10 | `RequesterQuestionAsked` | "We have a question about your request: {question}. Open your page to answer." |

No acknowledgement email for a reconsideration request (the page confirms it), and none for finalization.

**Leadership notifications** (`ham/requests/notifications.py`). Titles carry only HAM # + category (+ Urgent); never a name, message or answer.

| Event | In-app | Email |
|---|---|---|
| `RequestApproved`, not urgent | DIR, AD, and the other approvers except the decider: "Approved · HAM #047 Roof" | DIR, AD per preference (Q-168) |
| `RequestApproved` with `urgent_approval`, or `UrgencyCertified` with `urgent_approval` | DIR, AD: **urgent, must-acknowledge** banner "Urgent approval · HAM #048" | DIR, AD **regardless of preference** (§10, §35, Q-161). PL: step 5 |
| `RequestRejected` | DIR, AD, other approvers | none (Q-168) |
| `ReconsiderationRequested` | Board route: every BRD. Pastoral route: the original pastor (all pastors if the original no longer holds the role). DIR/AD: awareness | the addressed decider(s), per preference |
| Reconsideration takeover | the original pastor: "Pastor Ken took over HAM #047's reconsideration" | — |
| `UrgencyCertified` (not yet approved) / `UrgencyNotCertified` | DIR, AD update | — |
| `RequesterQuestionAnswered` | the asker: "Answer received · HAM #047" | the asker, per preference |
| `RequestMediaStored`, first item of a reopened batch (Q-150) | the reopener: "New photos arrived · HAM #047" | — |

A new identity service is needed for this: `identity.services.notification_recipients_for_users(user_ids) -> [(user_id, email, notify_email)]`, so the requests and media modules can address the original pastor, the asker and the reopener without reading auth tables.

**Attention providers** (computed live, never stored):
- **PAS:**
  - "Waiting for a decision" (existing). Urgent cards now say "Certify and decide".
  - "Reconsideration for you (n)" (theirs only).
- **BRD:**
  - "Waiting for a decision" (existing).
  - "Board reconsideration (n)".
- **DIR, AD:**
  - existing muted awareness row;
  - **"Approved: needs a site visit (n)"** (§64). It's actionable in step 4 and awareness only until then;
  - **"Call to share a decision (n)"** for no-email requests whose `Approval.requester_phoned_at` is null;
  - "Waiting on requester (n)" as a muted row.
- Everyone: the rows drop out the moment the underlying state changes (existing registry behavior).

---

## 5. Rules-module values

| Group | Constant | Value | Status |
|---|---|---|---|
| `approvals` (new group, "Approvals and reconsideration") | `RECONSIDERATION_REQUEST_WINDOW` | 30 days | provisional Q-155 (version bump + changelog + hash) |
| `requester_access` | `REQUESTER_ACCESS_AFTER_CLOSE` | unchanged (7 d) | sources += Q-155 (metadata only) |
| `media` | `PHOTO_/VIDEO_RETENTION_AFTER_CLOSE` | unchanged | note: "for Rejected, the clock starts at the final rejection" (Q-155); metadata only |

- No other new numbers: the design adds no reminders, no takeover delay and no SLA (Q-157, Q-162, Q-166).
- New invariant: `RECONSIDERATION_REQUEST_WINDOW > 0`.
- The finalize job runs hourly; that is an engineering cadence, not a rule.
- The deadline is shown in the church time zone (Q-030). Arithmetic is elapsed UTC time.

---

## 6. Screens (for ham-ux-designer, then ham-ui-designer)

**Leadership (existing L2 detail; right panel at ≥1280, sticky bottom action bar at 390):**
- **L2 decision panel** (varies by role and state):
  - Pastor, normal request: **Approve** (primary) · **Not approved…** · More ▸ Ask a question · Ask for more photos · Change category.
  - Pastor, urgent awaiting certification: a banner with the requester's urgency reason and justification, then **Certify urgent and approve** (primary) · Approve, not urgent · Not urgent (keep in queue) · Not approved…
  - Target: **3 taps or fewer** from the notification: open → Certify and approve → Confirm.
  - Board rep: **Record Board decision** → "Board decided on [today ▾]" → Approved / Not approved…
  - Already decided: a read-only card "Approved by Pastor Ruth · Oct 3 · pastoral route". If the request is urgent and uncertified, pastors also see "Certify urgent".
- **L12 approve confirm** (sheet): "Approve HAM #047? {first name} will be emailed. Approval means a site visit next; it doesn't promise the work." · Approve.
- **L13 not-approved sheet:** reason (radio, D2) → pre-filled message (editable, required) under a "{First name} will read this" label → a short preview → Send.
- **L14 reconsideration panel:** the original decision, "Asked on {date} · by secure page/phone", the requester's note, then **Decide** (approve / keep "not approved" + required reason). Other pastors see **Take over from Pastor Ruth** (confirm sheet).
- **L15 ask a question** (sheet) with the forwarding hint. For no-email requests it becomes **Call and record** (masked phone, question + answer fields).
- **L16 questions card** on L2: open and answered questions, asker, dates; Withdraw; Record an answer from a phone call.
- **L17 change category** (sheet): one select.
- **L18 Director/AD phone follow-up:** the card "Call {first name} to share the decision" + **Told them by phone**. Also **Asked to reconsider by phone** on a rejection that can still be reconsidered.
- **L1 list:** views Awaiting approval · Waiting on requester · Reconsideration · Decided · Closed. New status chips Approved / Not approved / Taking another look; "Waiting on requester" chip. Rows still show HAM # + category only (Q-132).
- **Home and Inbox:** the §4 attention cards; the urgent-approval banner for DIR/AD.

**Requester (R10 secure page, 390 first, large text):**
- **Decision card:**
  - Approved: "Good news..." + what happens next.
  - Not approved: the message + deadline + **Ask us to take another look**.
  - Taking another look.
  - Final: message + "You're welcome to send a new request" (links to the form).
- **R13 reconsider:** optional note → Send → confirmation. The button is hidden after the deadline or once used.
- **R14 question card(s):** "HAM has a question", the question, an answer box (≤2000) and Send. The answered state shows "Thanks, we got your answer" with the answer read-only. No card once the request is closed.
- **Status wording and chips:** add APPROVED, REJECTED (open and final) and RECONSIDERATION_PENDING to `projection.py` from the navigation.md §5 table, plus `STATUS_NEXT_STEPS`.
- No new pages for no-email requesters (updates are by phone).

---

## 7. Test plan (ham-test-engineer)

1. **States (pure, table-driven):**
   - every new edge, allowed and forbidden, with each actor;
   - deadline boundaries (exactly at the deadline is too late);
   - one reconsideration only;
   - takeover rules;
   - `is_urgent_approval` in both orders;
   - `closes_request` on final edges;
   - cancel from APPROVED and RECONSIDERATION_PENDING only with `requester_withdrew`.
2. **Oracle:** the 13 new rows as in §3; `build_permission_matrix --check`.
3. **Concurrency:** two pastors, or a pastor and the Board rep, approve or reject at once in threads. Exactly one `Approval`, one audit event and one outbox event; the loser gets "Already decided".
4. **Commands and audit:**
   - each command writes exactly one primary audit event with correct `before`/`after`;
   - certify-and-approve writes two audit events and two outbox events atomically;
   - a forced failure rolls back all of them;
   - the rejection message never appears in audit, outbox, logs or leadership emails;
   - denied decision attempts are audited;
   - impersonating: every decision action → `impersonation.action_blocked`, and category change is allowed.
5. **Append-only:**
   - updating or deleting `Approval`, `Reconsideration`, or a question's text raises;
   - `requester_phoned_*` can be set once only;
   - the second reconsideration insert violates UNIQUE.
6. **Constraints:** the fixed `closed_at` CHECKs (a regression test that the old tautology is gone); `is_request_open` is false for a final rejection.
7. **Jobs:** finalize at deadline + 1 s closes the request, sets the access end and closes open questions; before the deadline it's a no-op; it's idempotent.
8. **Media:**
   - approve and reject close open batches (subscriber);
   - reopen is refused on a rejection that can still be reconsidered and on closed requests, and allowed in reconsideration and Approved;
   - the retention sweep ignores a rejection that can still be reconsidered and purges on schedule after a final one;
   - the Q-150 notice fires once per reopened batch.
9. **Portal:**
   - an answer is accepted once; another request's token is denied (OWN_REQUEST);
   - reconsider is hidden and refused after the deadline or when used;
   - the page never shows another request's data;
   - the masked view hides answers and notes from the Administrator (including when impersonating, Q-151).
10. **Notifications:**
    - E8/E8r/E9/E9f/E10 bodies contain the link, and subjects are neutral;
    - no email when there's no email on file;
    - the urgent approval emails DIR/AD even with `notify_email=false`, exactly once, in both orders;
    - the reconsideration notice goes to the original pastor only, or to all pastors when that pastor lost the role;
    - leadership titles are PII-free (existing validator).
11. **Duplicate panel:** a prior rejected request shows the outcome, reason label and message to `request.history.view` holders only.
12. **Retention:** the 7-year purge blanks decision, reconsideration and question text and keeps codes and dates.
13. **Playwright** (390 / 768 / 1280 + 200% text):
    - Ruth: urgent banner → Certify and approve in ≤3 taps → Marcus gets the urgent banner.
    - Samuel: records a Board "not approved" with a reason.
    - Doris: rejection email → R13 reconsider → Ruth unavailable → Pastor Ken takes over → approves → Doris sees Approved.
    - A question asked and answered on R14.
    - A no-email request: Andre records a phone answer and "Told them by phone".
14. **§77 harness:**
    - **Step 4 becomes a real test** (both routes, plus the urgent path).
    - Step 28 adds decision, reconsideration and question actors.
    - Step 30 adds "no decision message, answer or note in outbox, leadership email, logs or audit CSV".

---

## 8. Slices (parallel worktrees, own DB each, e.g. `ham_s32`)

| # | Slice | Owner | Depends on | Owns files |
|---|---|---|---|---|
| S3.0 | **Seams and contracts.** All three new models, the new request fields, the **fixed CHECK constraints** and **one migration** (`requests` 0004), so parallel slices never collide on migrations. Also: every matrix action + `_AUDITED_ON_DENIAL`; oracle rows; permission-matrix doc; audit labels; outbox event names; service signatures as `NotImplementedError` stubs (§8.1); `is_request_open` → `closed_at`; `identity.services.notification_recipients_for_users`; URL stubs; `docs/architecture/approvals-contracts.md` | ham-backend-engineer | — | `ham/requests/models.py`, migration, `ham/authz/*`, `ham/audit/labels.py`, `tests/authz/generate_expected_matrix.py`, one identity function, url stub files |
| S3.1 | **Pure rules.** `states.py` edges, urgency sub-machine, `is_urgent_approval`, `may_decide_reconsideration`, `accepts_media_reopen`, `is_closed`; `RECONSIDERATION_REQUEST_WINDOW` (+ version, changelog, hash, invariants); unit tests | ham-rules-engineer | — (parallel with S3.0) | `ham/requests/states.py`, `ham/rules/*`, `docs/rules-changelog.md`, `tests/rules`, `tests/requests/unit` |
| S3.2 | **Decisions core.** approve / reject / certify / decline / certify-and-approve, reconsideration request (both actors) / decide / finalize command + hourly job, decision phoned, category change, cancel extension, retention text erasure, `outcome_summary` + `request_history` + detail/list queries (views, chips, masked answers), attention providers | ham-backend-engineer | S3.0, S3.1 | `ham/requests/services.py`, `services_decisions.py`, `queries.py`, `attention.py`, `jobs.py` |
| S3.3 | **Questions.** ask / answer (requester) / record phone answer / withdraw, auto-close on close (called by S3.2 through the `close_open_questions(request_id)` function stubbed in S3.0), "Waiting on requester" query | ham-backend-engineer (second worktree) | S3.0 | `ham/requests/services_questions.py`, `queries_questions.py` |
| S3.4 | **Media + portal backend.** Media subscriber for approved/rejected, reopen guard, Q-150 in-app builder; `projection.py` wording/chips/next steps; secure-page card data (`requester_portal/page.py`: decision card, reconsider eligibility, question cards) | ham-backend-engineer (third worktree) | S3.0, S3.1 | `ham/media/subscribers.py`, `services.py` (guard only), `notifications.py`; `ham/requester_portal/projection.py`, `page.py` |
| S3.5 | **Notification builders.** E8–E10 requester emails; leadership email + in-app; urgent-approval override and exactly-once; reconsideration addressing; PII-free tests | ham-integrations-engineer | S3.2, S3.3 (the stubs are enough to start) | `ham/requester_portal/notifications.py`, `ham/requests/notifications.py` |
| S3.6 | **Leadership screens.** L1 views, L2 decision panel, L12–L18 sheets, Home cards, urgent banner for DIR/AD | ham-frontend-engineer | S3.2, S3.3; UX + UI specs | `views_requests.py`, `urls_requests.py`, `templates/web/request_*` |
| S3.7 | **Requester screens.** R10 decision and question cards, R13 reconsider + confirmation, R14 answer | ham-frontend-engineer (second worktree) | S3.3, S3.4 | `views_requester.py`, `urls_requester.py`, `templates/web/requester/*` |

**8.1 Signatures for S3.0 stubs:**
- In `ham/requests/services.py` (or `services_decisions.py` re-exported):
  - `approve_request(ctx, *, request_id, route, board_decided_on=None, certify_urgent=False) -> Approval`
  - `reject_request(ctx, *, request_id, route, reason_code, message, board_decided_on=None) -> Approval`
  - `review_urgency(ctx, *, request_id, certify: bool) -> AssistanceRequest`
  - `request_reconsideration(ctx: RequesterContext, *, note="")`
  - `record_reconsideration_by_phone(ctx, *, request_id, note="")`
  - `decide_reconsideration(ctx, *, request_id, approve: bool, reason, reason_code="", take_over=False) -> Approval`
  - `finalize_rejection(ctx: SystemContext, *, request_id)`
  - `record_decision_phoned(ctx, *, request_id)`
  - `change_category(ctx, *, request_id, need_category)`
- Questions:
  - `ask_question(ctx, *, request_id, question, phone_answer="") -> RequestQuestion`
  - `answer_question(ctx: RequesterContext, *, question_id, answer)`
  - `record_phone_answer(ctx, *, question_id, answer)`
  - `withdraw_question(ctx, *, question_id)`
  - `close_open_questions(request_id, *, reason)` (plain function, runs inside the caller's transaction)

**Order:**
1. S3.0 ∥ S3.1, with ham-ux-designer (approvals UX spec) and then ham-ui-designer in parallel.
2. S3.2 ∥ S3.3 ∥ S3.4.
3. S3.5 ∥ S3.6 ∥ S3.7.
4. ham-test-engineer (§7).
5. Reviews: privacy-security (masked answers, forwarded-link scope, message leakage, impersonation blocks), prd-guardian, UX usability (Ruth ≤3 taps; Doris at 390 px with large text reading a rejection), UI visual QA.
6. Fixes, then the PR to `main`.

---

## 9. New PRD gaps (ready to paste, Q-153 onward)

Amend existing rows:
- **Q-109** append: "Step 3: Director, AD, pastors and Board rep may change the category on any request that isn't closed; audited (`request.category_changed`); no requester notice; emits `RequestCategoryChanged`."
- **Q-150** change to: "Build in step 3: in-app 'New photos arrived · HAM #' to the leader who reopened uploads, once per reopened batch."

| ID | PRD § | Question | Options | Proposed default | Status |
|---|---|---|---|---|---|
| Q-153 | §8, §8.1, §8.2 | Does the first recorded decision settle the request, including a rejection, while the other route hasn't acted? | First decision (approve or reject) decides / a rejection doesn't close while the other route could still approve | First recorded decision decides; others see who decided; disagreement goes through the one reconsideration (§8.4). Concurrent decisions: the first wins, the second sees "Already decided" | Open (owner decision D1) |
| Q-154 | §8.3, §9 | What rejection reason and explanation does the requester receive? | Reason list + editable kind message / free text / fixed text per code | Required reason (need can be met another way · not work HAM does · needs a licensed professional HAM can't provide · outside the area HAM serves · another reason) + required message pre-filled per reason, editable, labelled "{first name} will read this". Codes kept for reports and the duplicate panel; message erased at the 7-year purge (Q-145) | Open (owner decision D2) |
| Q-155 | §8.4, §7.3, §47 | How long may a requester ask for reconsideration, and when does a rejection become final? | 14 / 30 / 60 days / no limit | 30 days after rejection (deadline stored and shown in the email). Then HAM finalizes automatically: the request closes, the 7-day link clock (Q-116) and the §47 photo/video clocks start. Media clocks for Rejected always start at the final rejection | Open (owner decision D3) |
| Q-156 | §8, §3.3, §58 | Can an approver undo a decision recorded by mistake? | No undo, confirm first / undo within minutes by the same person | No undo; confirmation step before every decision; mistaken rejection → reconsideration; mistaken approval → the Director's feasibility decision after the site visit (§11, §12) | Open (owner decision D4) |
| Q-157 | §8.4 | When may another pastor take over a reconsideration from "unavailable" original pastor? | Any time with explicit takeover / after N days / only if original lost the role | Any time, by an explicit "Take over from Pastor X" (recorded, original pastor told in-app); if the original pastor no longer holds an active Pastor role, every pastor sees it as theirs | Open |
| Q-158 | §8.4, §7.2, Q-102 | What does the requester give when asking for reconsideration; must they re-verify (a forwarded link could ask)? | Button only / optional note / note + photos; extra code or not | Button + optional note (≤1000 characters); no new photos unless a leader reopens uploads (§46); no extra code (a reconsideration only asks for another look) | Open |
| Q-159 | §8.3, §8.4, Q-025 | How are no-email requesters told about decisions and how do they ask for reconsideration? | Phone by Director/AD, recorded / nothing recorded | Director/AD get a "Call to share a decision" card and record "Told them by phone" (audited, blocked while impersonating); a phone request for reconsideration is recorded by Director/AD with an optional note | Open |
| Q-160 | §10 | Details of urgent certification | Various | Pastors only. "Certify urgent and approve" in one step; "Not urgent" keeps it in the normal queue with no requester email; certification possible while Awaiting Approval or Approved (a declined urgency may later be certified); the Board rep can approve an urgent request but not certify it; pastors can't mark urgent a request the requester didn't flag (V1) | Open |
| Q-161 | §10, §35 | What counts as "urgent approval", and who is alerted how? | Pastor approval only / approved + certified in any order | Urgent approval = the request is Approved and urgency is Certified, whichever happens second; alerts fire once: Director and AD by email + must-acknowledge in-app banner regardless of preference; the Project Leader "when assigned" arrives with project leaders (step 5) | Open |
| Q-162 | §7.2, §35, §68, Q-124 | Rules for HAM questions to the requester | Various | Director, AD, pastors and Board rep may ask on any request that isn't closed; one answer per question on the secure page or recorded from a phone call; the asker is told (in-app, email per preference); the asker or Director/AD may withdraw; no reminders; open questions close when the request closes; "Waiting on requester" is a list view, not a status, and doesn't block a decision; the Administrator sees questions but not answer text or reconsideration notes | Open |
| Q-163 | §4.2, §8.1 | Should the Board rep record when the Board decided (vs when it was entered)? | Yes, a date prefilled with today / no | Yes: "Board decided on" date, prefilled today, not in the future | Open |
| Q-164 | §4.11, §8 | Someone holding both Pastor and Board rep: which route is recorded? | Always pastoral / chosen each time | Chosen at decision time, defaulting to pastoral; reconsideration follows the recorded route | Open |
| Q-165 | §52, Q-107, Q-108 | Can a request be closed after approval or while reconsideration is pending (e.g. the requester says they no longer need help) before project cancellation exists (step 4)? | No / Director/AD with "requester withdrew" only | Director/AD may close as "requester withdrew" only (audited, blocked while impersonating); step 4 moves this to project cancellation | Open |
| Q-166 | §64, §35, Q-130 | Should HAM nudge approvers or escalate when a request waits too long? | No / reminder after N days / escalate to Director | No automatic reminders or escalation in V1; Home cards show how long each request has waited | Open |
| Q-167 | §9, §68 | What does the duplicate panel show about a prior decision? | Outcome only / + reason / + message | Outcome, reason label and the message, to `request.history.view` holders only (not the Administrator) | Open |
| Q-168 | §35, §64 | Which leaders hear about a decision? | Director/AD only / all leadership | In-app update to Director, AD and the other approvers (not the decider); email to Director/AD per preference for approvals only; urgent approvals per Q-161 | Open |

