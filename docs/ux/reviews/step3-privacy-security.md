# Step 3 (Approvals): privacy and security review (ham-privacy-security-reviewer)

Scope: `git diff origin/main...HEAD` on `feature/step-3-approvals` at `7f43fb4`. The review was read-only. Proofs of concept ran from the reviewer's scratchpad, and the orchestrator saved this report.

**Summary:** Critical: none. High: 1. Medium: 4. Low: 9.

Four findings (H1, M1–M3) share one cause. The 30-minute undo window is enforced for the decider and on the requester page, but not for other leaders' follow-up actions or on the notification side.

## High
- **H1. Certifying urgency after a Board approval auto-acknowledges the Director/AD "Urgent request approved" alert** (§10, §35, Q-160/Q-161).
  - **Where:** `ham/requests/notifications.py:248-262` (`_clear_urgent_banner`). It acknowledges every unacknowledged `requires_ack` notice for the request, for every recipient and every kind. `review_urgency` emits `RequestUrgentApproval` before `UrgencyCertified`, so in normal delivery order the alert is cleared as soon as it's created. PoC confirmed.
  - **Fix:**
    - Clear only the pastors' urgent-request banner kind, for pastor recipients.
    - Never clear `request_urgent_approval`.
    - Add a regression test for both emit orders.

## Medium
- **M1. A reconsideration can be recorded by phone during the decider's undo window.**
  - **Where:** `services_decisions.py:435-443` and `:487-496` don't pass `decision_undo_open`. The view gates on the decider-only `pending`.
  - **Effect:** it blocks the undo (`state_changed_since_decision`), and the E11 email goes out before the held rejection email. PoC confirmed.
  - **Fix:** compute `decision_undo_open` from the latest live Approval in both services. Use the same predicate in the views for every viewer.
- **M2. The "urgent approval undone" follow-up can be suppressed.**
  - **How:** a pastor certifies inside a Board approval's undo window, then the Board rep undoes. The request ends up Awaiting Approval, still certified, with the Director's urgent alert auto-acknowledged and no "undone" notice. The builders also read live status at dispatch time.
  - **Fix:**
    - Refuse `review_urgency` while the live approval is undoable, and filter the pastor card the same way.
    - Key the undo follow-up on a stored `urgent_approval_emitted` fact on the Approval and the UrgencyReview.
    - Put the needed facts (ids and codes) in the payload rather than re-reading status.
- **M3. "Call to share a decision" is live during the undo window.**
  - **Where:** `attention.py:246`, `views_requests.py:404-413`, `record_decision_phoned`.
  - **Fix:** filter on `effective_at <= now`, and have the service refuse before then. See also the PRD finding that phone tasks read only the initial stage.
- **M4. Contact details are revealed automatically on GET** (A4 Ask, A5, A11: `views_requests.py:1408-1411`, `:1473-1476`, `:1525-1528`).
  - **Effect:** a misleading `requester_pii.revealed` audit row is written, even for email requesters where nothing is shown, and again on every re-render.
  - **Fix:** never reveal on A4 when the requester has email. Use an explicit POST "Show contact details / Call" control through `request_reveal_contact`.

## Low
- **L1. Held effects don't check `now >= effective_at`, and undo ignores `effects_ran_at`.**
  - **Fix:** re-defer an early job, and refuse the undo after the effects have run.
- **L2. Early signals during the window.**
  - Reconsider-decline sets `closed_at` at decide time, and the requester's `can_add_photos` uses the raw status.
  - **Fix:** use the effective status; consider setting `closed_at` at `effective_at`.
- **L3. The undo view gives a 500 on a malformed `approval_id`.**
- **L4. No server-side length limits** on the decline message, approval note or reconsideration reason.
- **L5. `finalize_rejections` stops at the first `ValueError`.**
  - **Fix:** catch errors per item.
- **L6. The dual-role route is preselected, with a silent server default** (Q-164).
- **L7. `requester-questions.js` sessionStorage.**
  - Acceptable overall.
  - But it clears the draft before the server confirms, and stale drafts linger.
  - **Fix:** clear on `?answered`, keep on `?answer_failed`, and prune on load.
- **L8. Internal refusal strings are shown to users** (the ask view).
- **L9. Questions asked during the window get auto-withdrawn soon after.**
  - **Fix:** hide or refuse Ask for everyone during the window.

## Checked and OK
- **Route guards:** `@requires_action` plus scoped lookup on every new leadership route. A NEEDS_PHONE_CHECK UUID gives 404.
- **Impersonation (Q-172):** blocked on GET and POST, and category change is allowed.
- **CSRF and caching:** CSRF is global, and sheets are `never_cache`.
- **Undo:** decider only, never while impersonating, only within the window; the state must be unchanged; the record is kept and audited.
- **Two deciders:** both lock the request, and the second gets "already decided".
- **Finalize vs reconsideration:** complementary predicates, so no double transition.
- **Requester routes:** token-scoped; single-use reconsideration; one answer per question; ids only in redirects.
- **Masking:** the Administrator's view is masked (including while impersonating), and the requester never sees the decider.
- **Payloads and audit:** subjects, titles and payloads are PII-free, and every command is audited with actor and UTC.
- **Retention:** the Q-145 purge blanks all new free text.

## Re-check at `089473e`

All proofs of concept were re-run.

| Item | Status |
|---|---|
| H1, M1, M2, M4, L1–L6, L8, L9 | Fixed |
| M3 | Partly fixed: the `request_decision_phoned` view has no window gate |
| L7 (requester-questions.js) | Not fixed |

New findings, each confirmed by a proof of concept:
- **N1 (High):** the "Tell by phone" sheet loads only the initial-stage decision, so after a reconsideration it reads out the wrong outcome and marks the requester as told.
- **N2 (High):** undoing a decline or a "Not urgent" never restores the pastors' urgent banner.
- **N3 (High):** approve/reject is allowed while a standalone urgency review is still undoable. The review's undo then leaves an urgent approval without certification. Fix: refuse decisions during the review's window, and have the review undo check a stored `prior_status`.

Mediums and Lows:
- **M-a:** migration 0007 has no backfill for the take-over basis.
- **L-a:** the re-defer has no clock floor.
- **L-b:** the banner restore reads live state and can create duplicates.
- **L-c:** per-request queries on Home.
- **L-d:** the undo GET is not decider-gated.
- **Accessibility:** a new must-acknowledge alert is no longer announced.

The FIX-3B banner and messages overrides are OK, and `need_category_label` is OK.

**Resolution note (orchestrator):** the owner's Q-176 rule allows urgency certification during another decision's undo window. M2's "refuse review_urgency during any window" is reverted to that rule. The undo follow-up instead keys on stored `urgent_approval_emitted` facts across the request, so undoing a Board approval after a later certification still sends the Director/AD "urgent approval was undone" follow-up.
