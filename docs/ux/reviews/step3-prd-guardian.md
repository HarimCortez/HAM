# Step 3 (Approvals): PRD conformance review (ham-prd-guardian)

Scope: `git diff origin/main...HEAD` on `feature/step-3-approvals` (after wave 3). The review was read-only, and the orchestrator saved this report.

**Verdict:** the core design is right, but the branch is not ready to merge. Two Board-route paths crash or are refused, and several owner decisions are only partly carried into the screens.

## Conforms
- **Roles (§4.2, §4.3, §5, §67):**
  - Approve and reject: pastor and Board rep. Urgent certification: pastor only.
  - Director, AD and Administrator can't decide.
  - Category change is Director/AD only and allowed while impersonating.
  - Every decision action is audited on denial.
- **D1/Q-153 (first decision settles it):** `select_for_update`; the loser sees "Someone else already decided".
- **D2/Q-154 (reason and message):**
  - the five reason codes are grounded in §5;
  - the message is required, prefilled and editable;
  - it goes in the email body, and the subject stays neutral;
  - no reason code or message in audit or outbox payloads.
- **D3/Q-155/Q-174 (window and cutoff):**
  - 14 days, in the rules module;
  - the cutoff is the end of the church-local day, stored on the request;
  - an hourly job finalizes.
- **D4/Q-156/Q-176 (undo):**
  - 30 minutes, in the rules module;
  - only the decider, never while impersonating, and only once;
  - the record is kept and audited;
  - the requester email, batch close, question withdrawal and leader updates are held until `effective_at`;
  - the urgent alert is immediate, with an undo follow-up;
  - the requester page keeps showing the earlier state during the window.
- **§8.3/§8.4:**
  - one reconsideration per request, with an optional note of up to 1,000 characters;
  - routing to the original pastor (with the take-over tick) or to the Board rep;
  - a reason is required, and a second "no" is final;
  - the requester gets a confirmation email (Q-175).
- **§10:** "Approve as urgent" in one step; certify after a Board approval; the alert fires exactly once. **§11:** the approval email carries the line "The visit helps us plan…". **§7.2:** questions and answers, including phone answers.
- **§46/§47:**
  - batches close on the held events;
  - reopening follows Q-173;
  - the clocks key on `closed_at`;
  - the 7-year purge blanks all new free text.
- **§52 states.**
- **§58:** every action audited.
- **§59/Q-048/Q-172:** the impersonation blocks.
- **§68/Q-170/Q-171:** HAM # plus category only; the requester never sees the decider; the Administrator's view is masked.
- **Scope (§73/§75) is clean:** no Project table, assessment, SMS, AI or Drive.
- Every PRD-GAP marker resolves to a real Q row.

## Blockers
- **B1. A Board rep can't approve an urgent-flagged request.**
  - `request_approve.html:23` posts `mode=not_urgent` for every non-urgent-mode viewer, and `views_requests.py:1000-1001` passes that on as `decline_urgency=True`.
  - `states.py:567-571` then refuses, because the route isn't pastoral.
  - **Fix:** send `mode=not_urgent` only for a pastor on the pastoral route; the Board route sends no urgency flag. Add a screen test.
- **B2. A Board-route reconsideration can never be recorded.**
  - `decide_reconsideration` (`services_decisions.py:585-598`) never sets `board_decided_on`, so the `approval_board_decided_on_required_for_board_route` constraint rejects the row.
  - The view catches only `ValueError`, so the user gets a 500.
  - **Fix:** thread `board_decided_on` (prefilled today, not in the future) through the service and view. Add tests (Q-180).

## Majors
- **M1.** The dual-role route comes preselected, and the server silently defaults it (Q-164 says nothing may be preselected).
- **M2.** Persona names ("Marcus and Andre") are hard-coded in production copy (`request_approve.html:65,69`, `request_certify_urgency.html:20`).
- **M3.** The §9 duplicate panel doesn't render the prior decision, reason, message or Q-169 note (`_request_detail.html:76-83`).
- **M4.** The §64 "approved, waiting for a site visit" awareness card for Director/AD is missing.
- **M5.** A no-email requester is never phoned about a reconsideration decision. The phone card, record and tick only read `stage=initial` (Q-182).
- **M6.** Other leaders ignore the undo window:
  - `pending` is computed for the decider only;
  - phone actions and cards appear during the window;
  - the reconsideration services don't pass `decision_undo_open`;
  - `record_decision_phoned` doesn't check `effective_at` (Q-181).
- **M7.** A standalone "Not urgent" or "Certify" can't be undone from the screens: there's no UI for `undo_decision(review_id=…)`.
- **M8.** An in-app "Not urgent" update is sent, against the owner box.
- **M9.** The §77 step-4 harness is still a placeholder.

## Minors
1. The decline preview wording doesn't match the email, and "14 days" and "30 minutes" are typed straight into templates. Both should come from `RULES.approvals`.
2. Auto-withdrawn questions use close reason `request_closed`. Add `request_decided` (Q-162).
3. Q-177 isn't reachable from the screens: there's no "Not urgent" after a Board approval.
4. The service accepts `told_by_phone=True` for requesters with email. Refuse it (Q-159).
5. A take-over after the original pastor's role ended stores `unavailable_confirmed=True`, and the audit lacks the tick or basis (Q-183).
6. The finalize job selects `deadline__lte=now` (use `__lt`), and one error stops the whole batch (catch errors per request).
7. The text limits aren't logged: decline message 600, note 200 (Q-179).

## New gaps
Q-179 to Q-183 are logged in `docs/prd-open-questions.md`.

## §77 progress
| Step | Status |
|---|---|
| 4 | Partly advanced: the pastoral route works end to end; the Board route fails for urgent requests and reconsideration; the harness is still a placeholder |
| 28 | Advanced |
| 30 | Advanced |
