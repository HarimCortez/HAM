# Step 3 (Approvals): UX usability review

Reviewer: ham-ux-designer · 2026-09-29 · branch `feature/step-3-approvals`
Spec: `docs/ux/approvals.md` (A1–A13, R13–R19, E8–E15, L-E5–L-E12). Where the two differ, the owner box in `docs/architecture/approvals.md` wins: 30-minute undo, a 14-day window, equal-weight buttons, category changes by the Director/AD only, and "the requester" in leadership copy.
Evidence: templates, `ham/web/views_requests.py`, `ham/web/views_requester.py`, `ham/requests/{attention,notifications,services_decisions}.py`, `ham/requester_portal/notifications.py`, and the screenshots in `docs/ux/screenshots/step3/`.
Personas: Pastor Ruth (phone), Elder Samuel (Board rep, laptop), Marcus (Director), Nadia (Administrator), Doris (390px, large text), Mrs. Hall (no email).

Totals: **2 Blockers, 15 Majors, 20+ Minors.**

---

## 1. Task completion and tap counts

| Flow | Target | Built | Verdict |
|---|---|---|---|
| Ruth approves an urgent request from the banner, email or Home card | 3 taps | Open → **Approve as urgent…** → **Certify and approve** = 3 | Met. The Decision card is on the first screen at 390 (`leader-decision-390.png`). |
| Ruth approves a normal request from Home | 3 taps | Home "Open" → list → row → Approve… → Approve = 4 | Missed by 1 tap. The summary card opens the list, not the request (Minor m1). |
| Doris: decline email → ask us to reconsider | 1 + 2 taps | "Open my request page" → **Ask us to reconsider** → **Send my request to reconsider** = 3 | Met. The note is optional and she types nothing. |
| Doris answers a question | 1 tap + typing + 1 tap | Same | Met on the happy path. If the send fails, her text is lost (M9). |
| Samuel records 5 Board decisions | 2 clicks each + "Next waiting request ›" | No "Next" link. Each save lands on the standalone detail page, and he goes Back to the list and picks the next row (about 4 clicks each) | Missed (Minor m2). |
| Marcus tells Mrs. Hall a reconsideration outcome | Home card → script → Mark as told | No card, the wrong script and a dead end | **Fails (B1).** |

---

## 2. Blockers

### B1. A no-email requester never hears the outcome of her reconsideration, and the phone script is wrong
- **Where:**
  - `ham/requests/attention.py:251-256`: `decision_phone_card` counts only `stage=INITIAL` approvals.
  - `ham/web/views_requests.py:1385-1391`: `request_decision_phoned` also loads only the INITIAL approval.
  - `ham/requests/services_decisions.py:694-696`: `record_decision_phoned` also works only on the INITIAL approval.
  - `_decision_panel` (`views_requests.py:376-413`) uses the **latest** approval, which is the reconsideration.
- **User impact:** Mrs. Hall asks by phone to reconsider (A12), and Pastor Ruth decides.
  - No "Call to share a decision" card appears on Home.
  - If Marcus happens to open the request, the Decision card says "Call to share a decision · not yet told". **Tell by phone…** then shows the script for the *first* decision ("we aren't able to help…"), even when the reconsideration approved it.
  - **Mark as told** then fails with "That's already been recorded, or didn't go through." The first decision was already marked as told, so the card never clears.
  - The most vulnerable requester either gets no news or gets the opposite news.
- **Fix:**
  - Drive the card, the script and the record from the latest live approval, whatever its stage.
  - Add the "I've already told them by phone" tick to A9 for no-email requests.
  - Add a test: no-email → declined → phoned reconsideration → approved → the card appears with the approval script → Mark as told clears it.

### B2. The "Call to share a decision" to-do appears during the 30-minute undo window
- **Where:**
  - `attention.py:251-256` doesn't filter on `effective_at <= now`.
  - `views_requests.py:404-413` builds the `tell_by_phone` block whether or not the window is still open.
- **User impact:** The owner decision (D4, Q-176) holds requester-facing effects for 30 minutes. Email honours this, but the phone path doesn't. Marcus sees the to-do the moment Ruth records a decision. He can call Mrs. Hall with "you're approved", and Ruth can undo 10 minutes later. For an older requester, hearing yes and then no is worse than waiting half an hour.
- **Fix:**
  - Show the card and the Decision-card line only when `effective_at <= now` and the decision isn't undone.
  - During the window, show Dir/AD a muted line instead: "Decision can still be undone until 2:45 PM. Wait to call."

---

## 3. Majors

### M1. Home and Inbox cards open the wrong tab
- **Where:**
  - `attention.py:241`: `?view=reconsideration`.
  - `attention.py:265` and `:286`: `?view=decided`.
  - `requests_list` reads only `?tab=` (`views_requests.py:190`), and nothing reads `view`.
  - The Dir/AD awareness card uses `?status=AWAITING_APPROVAL` (`attention.py:91`). The list honours `status` only on the "All" tab, so for the Director it opens **Needs a phone check** whenever that tab has items.
- **User impact:**
  - Ruth taps "Reconsideration for you (1)" and lands on **Awaiting approval**, where the request isn't listed.
  - The same happens to Marcus with "Call to share a decision" and to pastors with "Certify urgent · approved".
  - These look like dead ends on the exact cards that exist to prevent waiting.
- **Fix:**
  - Use `?tab=reconsideration`, `?tab=decided` and `?tab=awaiting`.
  - When a card has a count of 1, link straight to `/requests/{id}`. The spec asks for one card per reconsideration ("Asked to reconsider · HAM #046 · you declined it Oct 6").

### M2. During the undo window, other approvers see a settled decision; the "pending" state never renders
- **Where:** `views_requests.py:385-386` sets `pending = is_decider and …`. Anyone who isn't the decider gets `state="decided"`, so the "Decision pending (…) You can't decide while it can still be undone" branch (`_decision_card.html:124-129`) never runs.
- **What those viewers see instead:**
  - "Approved" and "Next: site assessment".
  - "What we told the requester" plus the message, though nothing has been sent yet (`_decision_card.html:132-136`).
  - **Ask a question** and **Change category** buttons.
- **User impact:**
  - Pastor David or Marcus acts on something that can vanish within 30 minutes. For example, Marcus starts arranging a visit or asks Doris a question on an approval that is then undone.
  - Even the decider reads "What we told the requester" next to "Nothing has been sent to the requester yet". The two lines contradict each other.
- **Fix:**
  - Compute `in_window` for every viewer. The decider keeps the Undo block.
  - Everyone else sees: "Pastor Ruth Alvarez approved this at 2:15 PM. It can be undone until 2:45 PM, so nothing has gone to the requester yet."
  - Hide "Next: site assessment" and the question and category actions until the window closes.
  - Use the label "What we'll tell the requester" while the email is held.

### M3. Real users see the sample names "Marcus and Andre"
- **Where:** `request_approve.html:65` and `:69`.
- **User impact:** The live consequence line names personas who don't exist. A pastor can't trust a line that names the wrong people.
- **Fix:** "The Director and Assistant Director are alerted right away…", or render the actual role holders' short names from data.

### M4. Dual-role users get a preselected route
- **Where:**
  - `request_approve.html:30` and `request_reject.html:27` check `default_route`.
  - `_default_route` (`views_requests.py:944-950`) returns `pastoral` for someone who holds both roles.
- **User impact:** The owner decision (Q-164) says nothing is preselected. The route decides who handles a later reconsideration. A pastor who is also the Board rep, recording the Board's decision after a meeting, can record it as a pastoral decision without noticing.
- **Fix:** For dual-role users, leave both radios unchecked and keep `required`. Show the "Date the Board decided" field only when "The Board's decision" is chosen.

### M5. Changing the decline reason silently overwrites the pastor's own words (S3.6 simplification: **rejected**)
- **Where:** `request_reject.html:95-105`.
- **User impact:** Ruth adds "We hope your son is home soon." and then taps another reason to compare the wording. Her sentence is gone, with no warning and no announcement. The build comment says "the field is empty until a reason is chosen the first time", but that is true only for the first choice.
- **Fix:**
  - Overwrite only when the field is empty or still equals the last prefill.
  - Otherwise show the spec's inline pair: "Replace your message with the suggested one? [Replace] [Keep mine]".
  - Add a polite status message: "Message filled in from the reason you chose. You can edit it."

### M6. The decline preview doesn't match the email Doris receives
- **Preview** (`request_reject.html:63-66`, `leader-decline-sheet-390.png`):
  - includes "We know this isn't the answer you hoped for";
  - says "ask us to reconsider, once, within the next 14 days".
- **Email E10** (`ham/requester_portal/notifications.py:393-399`):
  - has no sympathy line and no "once";
  - says "You can ask us to reconsider until Tue, Oct 20.";
  - has no "Or call us… We're glad to talk it through."
- **R10 page:** has a third wording.
- **User impact:** The preview promises "what the requester will read". This is the trust-sensitive moment (§8.3). Doris, who is older and may not click through, gets a colder email with no phone number.
- **Fix:**
  - Build the preview and the E10 body from one shared function, using the real deadline date.
  - Give E10 the sympathy line, "once", the date, a pointer ("Ask us to reconsider is on your request page") and the church phone line when it is set.
  - Apply the same to E13, adding "Your request page stays open until {date}."

### M7. Typed text is lost on validation, concurrency and refusal errors
- **Where:**
  - A9: `request_reconsideration_decide` re-renders without passing back `reason`, `reason_code` or `take_over` (`views_requests.py:1316-1332`, template `:56`, `:64` and `:72`). Forgetting the take-over tick wipes the reason.
  - A4: the question is lost when it is too long (`:1478-1489`).
  - A5: the answer is lost (`:1530-1542`).
  - A12: the note is lost (`:1367-1371`).
  - A3/A2: a refused POST (for example a Board date in the future, `services_decisions.py:122-123` and `:263-264`) raises `ValueError`. It redirects to the detail page with "That didn't go through… Try again." (`views_requests.py:936`), which discards the decline message.
  - Concurrency (A13): "Someone else already decided this request while you were looking." doesn't say who or when, and it doesn't offer "See what you wrote".
- **Fix:**
  - Re-render every sheet with the posted values on error.
  - Validate the Board date inline: "Enter the date the Board decided. It can't be in the future."
  - For A13, render the detail page with a `role="alert"` message ("Pastor Ruth Alvarez approved HAM #047 at 2:15 PM, while you were looking. Nothing was changed.") and a disclosure that holds the posted text.

### M8. Doris loses her answer when sending fails, and the page tells her it's still there
- **Where:**
  - `requester-questions.js:58-60` clears `sessionStorage` on submit, before the server replies.
  - `views_requester.py:1131-1133` redirects with `?answer_failed=`.
  - `r10_secure_page.html:105-108` then says "It's still here", but the box is empty.
  - An empty answer also takes this path. The textarea has no `required`, so a blank submit shows the same "couldn't send just now" message.
  - An answer over 1,000 characters isn't told it's too long.
- **User impact:** Doris dictated a long answer, it failed, and she is told it's still there. She has to redo it and may give up.
- **Fix:**
  - Clear storage only when the page loads with `?answered=` for that question.
  - Distinguish the three cases:
    - "Please write your answer before sending."
    - "That's a little long. Please keep it under 1,000 characters, or call us."
    - "We couldn't send your answer just now. It's still here. Please try again."

### M9. Urgent banners don't clear when they should
- **Where:**
  - `reject_request` (`services_decisions.py:247-322`) emits no urgency event, so `_clear_urgent_banner` (`ham/requests/notifications.py:248`) never runs.
  - `_build_decision_undone_notices` (`notifications.py:406-428`) adds an "undone" update. It doesn't clear the Director/AD must-acknowledge "Urgent request approved" banner.
  - Nothing restores the pastors' urgent banner after an urgent approval is undone.
- **User impact:**
  - Once Ruth declines urgent request HAM #048, every other pastor still sees "Urgent request needs a pastor · HAM #048" on every page. This causes alarm fatigue.
  - After an undo, Marcus still sees "Urgent request approved… Arrange the site visit." That is wrong.
- **Fix:**
  - Clear pastor banners on any recorded decision on an urgent request.
  - On undo of an urgent approval, clear the Director/AD banner and re-raise the pastors' banner. The request is urgent and awaiting a pastor again.

### M10. The reconsideration decline sheet (A9) is unfinished
- **Where:** `request_reconsideration_decide.html`.
- **Problems:**
  - Decline mode has no prefill, no helper text and no preview of the final (R18b) wording. This is the last and final message Doris gets.
  - The Board-route "Date the Board decided" is collected (`:45-50`), but the view never reads it (`views_requests.py:1277-1306`). The data is silently dropped.
  - Without take-over, the h1 renders as "approve HAM #046?" in lowercase (`:11-13`).
- **Fix:**
  - Reuse the A3 reason, prefill and preview pieces with the final wording and the attention-toned "This is final" line.
  - Pass `board_decided_on` to `decide_reconsideration`.
  - Capitalise the heading, for example "Approve HAM #046 on reconsideration?".

### M11. The undo sheet is wrong for no-email requesters and for "told by phone"
- **Where:** `request_decision_undo.html:20` always says "Nothing has been sent to the requester. Their email is cancelled."
- **User impact:** Ruth ticked "I've already told her by phone" and then undoes. The sheet doesn't warn her that Mrs. Hall now has wrong news.
- **Fix:**
  - For no-email requests: "Mrs. Hall doesn't use email, so nothing was sent."
  - If a phone record exists: "You told the requester by phone at 2:16 PM. Please call them back." Then clear the phone record, or ask the Director/AD to call back.

### M12. Deciding while a question is open gives no warning (partly the S3.6 "no marker on rows" simplification)
- **Where:**
  - `request_approve.html` and `request_reject.html` have no "Andre's question will be withdrawn" consequence line.
  - List rows (`requests_list.html:80-85`) have no `?` "Question open" or "Answered" marker.
- **User impact:** Ruth works through the Awaiting tab, approves or declines, and silently withdraws Andre's question. Doris's half-typed answer is then discarded. The Decision card marker is the only cue.
- **Fix:**
  - Add the consequence line to both sheets.
  - Add the row marker "Question open · 2 days", which is cheap because the data already exists in `waiting_on_requester`.
  - The row marker on its own would be a Minor; together with the missing sheet line this is a Major.

### M13. "Why it's urgent" is hidden in grey text
- **Where:** `_request_detail.html:100` renders it as `text-secondary` "Urgent: …" under What's needed.
- **User impact:** The spec (A1 item 5) puts it first, as an attention-toned block that shows the reason and the requester's own words separately. Ruth decides "Not urgent: leave for normal review" from this page, and that sheet doesn't repeat the reason (`request_decline_urgency`). Only A2u does.
- **Fix:** Render a "Why it's urgent" `attention` block before What's needed, with the reason label and the requester's words in a quote. Repeat it on the A2n sheet.

### M14. Opening "Ask a question" logs a contact reveal nobody asked for
- **Where:** `views_requests.py:1473-1476` calls `reveal_requester_pii(surface="ask_question")` on every GET, even when the requester has email and the result is thrown away (`:1485`). A5 and A11 also reveal on open.
- **User impact:** The reveal log fills with reveals nobody chose to make. That weakens its value for audits and can misrepresent leaders (Q-024, Q-125). For no-email sheets, revealing the number is arguably intended, but it should be a deliberate tap.
- **Fix:** Don't reveal on GET. Show a **Show number and call** button inside the sheet that performs the logged reveal. Flag this to ham-privacy-security-reviewer.

### M15. The decision screen doesn't lead with the decision at 390 and at 200% text (S3.6 "no sticky bar": accepted only with this fix)
- **Where:** `_request_detail.html:26-41` puts **Ask for more photos** and **Close request…** in the header, above the Decision card (`leader-decision-390.png`).
- **User impact:** At 100% text the card is still above the fold, so a single set of buttons is acceptable. At 200% text the header, the photos button and the card's own copy push Approve and Decline below the fold, and without a sticky bar Ruth has to scroll to find them.
- **Fix:**
  - Move the header actions into the Decision card's secondary row, or place them after it.
  - Check at 390 with 200% text that **Approve…** and **Decline…** are on the first screen. If they aren't, add the sticky pair back and mark the in-card copy `aria-hidden` only while the bar is visible.

---

## 4. Judgement on the reported simplifications

| Simplification | Verdict | Notes |
|---|---|---|
| S3.6: no right side sheet at ≥1024 | **Accept for V1 (Minor)** | Full-page sheets are clear and keep the HAM # in the h1. Two gaps remain. First, add a compact summary of the request (category, why it's urgent, photo count) at the top of A2 and A3 at ≥1024. Second, return to the split view with the next row selected after saving, which feeds m2. |
| S3.6: no second sticky decision bar | **Accept, with conditions (see M15)** | One set of buttons is better for assistive technology, but only if the card is the first thing after the header at every text size. |
| S3.6: reason change always refills the message | **Reject (M5)** | It destroys the pastor's own words. |
| S3.6: no "question open" marker on list rows | **Reject as part of M12** | On its own it would be Minor. Paired with sheets that don't warn, it's a Major. |
| S3.7: no first-visit check hero on R14 | **Accept (Minor)** | The chip and "Good news" sentence carry the moment. Add it later, reusing the existing `success-hero` from the welcome state (`r10_secure_page.html:12`). |
| S3.7: no R16 desktop aside | **Accept (Minor)** | R16 is short. At 1280 it should at least cap line length and repeat "Here's why" for context. |

---

## 5. Minors

**Flow and tap counts**
- **m1.** The pastor's "N requests are waiting" card opens the list. When N ≤ 2, list them as rows linking straight to each request (spec A8). The Home greeting also lacks "{n} things need you."
- **m2.** There's no "Next waiting request ›" after a decision (A2 result, §12.1 Board target). After a save, redirect to the list or split view with the next oldest request selected, or add the link to the toast.
- **m3.** Toasts read "Approved · HAM #047". The spec wants the time ("Approved · 2:15 PM") and mention of undo: "Approved · 2:15 PM · You can undo until 2:45 PM."
- **m4.** When a decline-urgency or certify link is stale because another pastor already acted, it returns the neutral not-found page (`views_requests.py:1046-1051`, `:1075-1079`). Use the A13 message instead: "Pastor David certified this at 8:03 PM. Nothing was changed."

**Undo**
- **m5.** "Can be undone until 10:37 PM EDT on Sep 28, 2026" doesn't say what happens then. Use: "Can be undone until 10:37 PM. The requester's email goes out then." Drop the year for today's times.
- **m6.** The Undo button renders whenever `pending` is true and ignores `can_undo` (`_decision_card.html:121`). An impersonator who maps to the decider sees it, then gets the wrong error ("The time to undo has passed…", `views_requests.py:1220-1224`). Hide it when `can_undo` is false, and use the impersonation line.
- **m7.** Copy hard-codes rule values: "30 minutes" (`request_approve.html:65`, `:69`; `request_reject.html:69`; `request_decision_undo.html:15`) and "14 days" (`request_reject.html:66`). Render them from the rules module.

**Decision card and detail**
- **m8.** "Elder {{ name }}" is hard-coded (`_decision_card.html:84`). Not every Board rep is an Elder, and the result could read "Elder Elder Samuel". Use the display name only.
- **m9.** On an awaiting request, the Administrator sees "Not shown to the Administrator role." where the buttons would be (`_decision_card.html:68-69`). That reads as hidden data. Use "View only. Pastors and the Board rep decide."
- **m10.** Change category is hidden while impersonating (`_decision_card.html:49`, `:180`), and an impersonation refusal says "Try again" (`views_requests.py:1580-1581`). Q-172 allows category changes while impersonating. Show the action. If it is ever refused, say why.
- **m11.** Leaders see "10:07 PM EDT on Sep 28, 2026" everywhere, including the reconsideration deadline, which shows as 11:59 PM. Use "until Thu, Oct 8" for the deadline and a short relative time for today.
- **m12.** A withdrawn question shows only "Withdrawn" (`_request_detail.html:166`). The spec wants "Withdrawn by Andre W." **Withdraw** posts instantly with no confirmation. Add an inline confirm, or a 5-second undo.
- **m13.** At 1280 the standalone detail is one stretched column (`leader-decision-1280.png`, `leader-undo-window-1280.png`). The spec wants a main column plus a side column holding the sticky Decision card, earlier requests and contact. Hand this to ham-ui-designer.
- **m14.** The copy stays "the requester" even after this viewer reveals contact details. That is acceptable for now, but the owner box allows the first name after a reveal. Log it as a follow-up.

**A2 and A3 sheets**
- **m15.** The Board route still labels the button "Decline HAM #…" and the heading "Decline". Use "Record Board decision" and "The Board didn't approve HAM #…".
- **m16.** For no-email requests the preview header says "What the requester will read". Use "What to tell them by phone".
- **m17.** A dual-role user can choose "The Board's decision" in urgent mode, which fails with a generic error. In urgent mode, hide the Board option or explain that only a pastor can certify.

**Home, Inbox and banner**
- **m18.** The pastor's empty Home shows "Your to-do list will appear here… once projects… are live" (`home.html:78-91`). For approvers, use "Nothing needs a decision right now. We'll let you know when a request comes in."
- **m19.** Every card button is labelled "Open". Add an `aria-label` such as "Open HAM #048, urgent". The spec's label is "Review".
- **m20.** "Answer received" exists only as an Inbox Update. There's no Home card for the person who asked (spec A8 group 3).

**Requester pages and emails**
- **m21.** The red "Urgent" chip stays on the requester page after a decline or "not urgent" (`r10_secure_page.html:37`). Show it only while the request is awaiting approval.
- **m22.** Declined and final pages still show "Photo uploads are closed for now. If HAM needs more, we'll ask." and "No longer need help? Call us and we'll close your request." (`r10_secure_page.html:175-179`, `:244-247`). Hide both once the request is declined. On the declined page, the photo line sits right under **Ask us to reconsider** and suggests photos would help.
- **m23.** The question page shows two Primary buttons, **Send answer** and **Add photos** (`requester-question-390.png`; `r10:127`, `:173`). Make Add photos Secondary while a question is open.
- **m24.** R16 shows **Not now** twice (`r16_reconsider.html:40`, `:44`). The heading gets focus on load and shows a heavy focus ring (`requester-reconsider-390.png`), which can look like an error to Doris. Keep one Not now, and use `:focus-visible` styling so the programmatic focus shows no ring.
- **m25.** Email wording:
  - `_first_name` falls back to "there", producing "Good news, there: …".
  - `Here's why: "{message}".` gives double punctuation when the message ends with a period.
  - E8 has no "Hi Doris" and no "Prefer to talk? Call…".
  - E9 lacks "You don't need to do anything right now."

---

## 6. Accessibility (WCAG 2.2 AA)
- **Duplicate error messages.** Sheets render `messages` themselves as `role="alert"` (`request_reject.html:13-17` and others). `base.html:49-57` renders them again as `role="status"`, so each error is shown and announced twice. Render them in one place.
- **Error focus.** Error blocks have `tabindex="-1"`, but nothing focuses them. There's no error summary linked to the fields, no `aria-invalid`, and radio groups have no `aria-describedby` on the legend. Only R16 does this properly. Apply the R16 pattern to every A sheet.
- **Concurrency and refusal messages** arrive as `messages.error`, which renders with `role="status"` and the class `inline-alert--error`. That class may not exist; the tone used elsewhere is `--danger`. The spec wants `role="alert"` with focus on the message.
- **After a decision,** focus isn't moved to the Decision heading, so a screen-reader user doesn't hear the new state. Focus it after the redirect.
- **The urgent banner** is `role="alert"` on every page load (`_urgent_banner.html:7`), so it re-announces on every navigation. Announce it once, then render it as a labelled `region` (step-2 Minor 22 again).
- **Undo block.** The `role="status"` on the static Undo block (`_decision_card.html:116`) is harmless but adds nothing on page load. Keep it, and make sure the toast carries the undo deadline (m3).
- **Target sizes and sticky bars.** The sticky action bar on sheets stacks Cancel above the Primary button, taking about 17% of the viewport at 390 (`leader-decline-sheet-390.png`). At 200% text, check that it stays under 22em and that `scroll-padding-bottom` keeps the focused textarea visible (2.4.11).
- **What's done well:**
  - The neutral "Not approved" chip always has an icon plus a word.
  - Captions sit on the quote blocks.
  - The R16 focus and error pattern is correct.
  - The soft character counter works.
  - Approve and Decline are equal-weight Secondary buttons, and the urgent request leads with a Primary button, as the owner decided.

---

## 7. What works
- Ruth's urgent path meets 3 taps, and the A2u sheet repeats the urgent reason and states the consequence.
- The Decision card copy is clear, and Approve and Decline carry equal visual weight.
- The requester decline page is warm and plain:
  - a neutral chip;
  - "Here's why" with the pastor's own words;
  - a sympathy line;
  - the reconsider block as a Secondary button with the real date.
- R16 has a double-send guard, an optional note, a microphone tip, and lands on R17 when she has already asked.
- Email subjects are neutral, and every requester email carries the page link.
- The Administrator sees the question text and "Answered on …" only, never the answer or reconsideration notes.

## 8. Hand-offs
- **ham-frontend-engineer / ham-backend-engineer:** B1, B2, M1–M15.
- **ham-privacy-security-reviewer:** M14 (automatic reveals), B2 (effects inside the undo window), m10 (impersonation and category change).
- **ham-prd-guardian:** M4 (Q-164), m10 (Q-172), M6 (D2 email body content), and M10 (the Board date dropped on reconsideration).
- **ham-ui-designer:** m13 (the two-column detail at 1280), M15 (the Decision card order at 200% text), m23 (two Primary buttons).

---

## Re-check at 089473e

Reviewer: ham-ux-designer · 2026-09-29 · after FIX-3A (logic) and FIX-3B (screens).
Walked again as Ruth, Samuel, Marcus, Doris and Mrs. Hall against the templates, views, email builders and `docs/ux/screenshots/step3/`.

**Screenshot caveat:** `leader-decline-sheet-390.png` still shows "ask us to reconsider, once, within the next 14 days". That string no longer exists in `request_reject.html`, so this screenshot was not regenerated. The other screenshots match the current templates.

**Result:** 1 Blocker is still open (B1, partly fixed). 6 Majors are fixed, 7 are partly fixed and 3 are not fixed. There are 2 new Majors.

### Blockers and Majors

| ID | Verdict | Evidence |
|---|---|---|
| B1 | **Partially fixed. Still a Blocker.** | Fixed: the card (`attention.py:246-263`), the service (`services_decisions.py:795-800`) and the Decision card (`views_requests.py:389-451`) now use the latest live approval at either stage. The A9 "already told by phone" tick exists (`request_reconsideration_decide.html:91-96`). **Still open:** the A11 view still loads only `stage=INITIAL` (`views_requests.py:1602-1608`). As a result, after a reconsideration *approves*, Marcus's script (`request_decision_phoned.html:18-24`) reads the first decline plus "You can ask us to reconsider once, until …". After a final decline, it reads the first message and an expired reconsider offer. Mark as told now succeeds, so he records that he gave Mrs. Hall the wrong news. |
| B2 | Fixed | `attention.py:262` (`effective_at <= now`); `views_requests.py:443` (`window_closed`); the service refuses inside the window (`services_decisions.py:808-809`). During the window, Dir/AD see the pending line (`_decision_card.html:143-146`). |
| M1 | Partially fixed | The tab keys are correct (`attention.py:91,125,137,241,272,304`), so the cards no longer land on the wrong tab. Not done: a card with a count of 1 still doesn't deep-link to the request. "Call to share a decision" lands on the whole Decided tab, and no row shows which request needs the call (see N2), so Marcus has to open each row to find it. |
| M2 | Fixed (Minor residue) | `pending` is now computed for every viewer (`views_requests.py:402`). Non-deciders see the read-only line (`_decision_card.html:138-146`). "Next: site assessment", Ask a question and Change category are hidden while the decision is pending (`:180`, `:204`; `views_requests.py:509-513`). Residue: the caption still reads "What we told the requester" while the email is held (`_decision_card.html:151`). |
| M3 | Fixed | `request_approve.html:82,86` now say "The HAM Director and Assistant Director". |
| M4 | Fixed | Nothing is preselected (`request_approve.html:39-40`, `request_reject.html:30-31`, `views_requests.py:1146`). A missing route is refused with a 422 (`:1074-1088`, `:1268-1270`). Minor: the Board date field still shows for both routes rather than only for "The Board's decision" (`request_approve.html:55-61`, `request_reject.html:34-37`). |
| M5 | Fixed | A "Replace or keep mine" prompt (`request_reject.html:59-64`), and the message is overwritten only when it is still clean (`:124-138`). Minor: after a 422 re-render, `lastPrefill` holds her own posted text (`:112`), so the next reason change overwrites it without asking. |
| M6 | Partially fixed | E10 now uses `decline_outcome_text` (`requester_portal/notifications.py:388-396`), which adds "once", the real date and the phone line (`presentation.py:211-223`). **However, the A3 preview is still hand-written** (`request_reject.html:75-82`) **and has already drifted:** it promises "We know this isn't the answer you hoped for.", and the email doesn't contain that line. Also still missing: the pointer "Ask us to reconsider is on your request page", E13's "Your request page stays open until {date}", and the fix for the double punctuation in `Here's why: "…".` (`presentation.py:208`, `:222`). **Judgement on FIX-3A's note:** not calling the shared builder is not a technicality. The drift it risks has already happened. Fix: have `decline_outcome_text` return parts (`opening`, `message`, `closing`), include the sympathy line in `closing`, and render the preview from those parts. JS then swaps only the message. |
| M7 | Partially fixed | Posted values now come back on A2 (`views_requests.py:1076-1088`), A3 (`:1308-1321`), A9 (`:1465-1546`), A4 (`:1702-1703`), A5 (`:1752`) and A12 (`:1587`). A3 validates the Board date inline (`:1283-1290`). Still open: A2 and A9 don't check for a future Board date inline (A9 only checks `is None`, `:1498`). The service refuses it, `_decision_error_redirect` (`:976-992`) runs, and the typed reason is lost. The A13 message still doesn't say who decided or when, and offers no "See what you wrote" (`:985-989`). A2 doesn't re-check `told_by_phone` on re-render (`request_approve.html:73`). |
| M8 | Not fixed | `requester-questions.js:58-60` still clears storage on submit. `views_requester.py:1136-1138` still sends empty, too-long and failed answers to the same "It's still here" message (`r10_secure_page.html:105-108`), and the textarea still has no `required` (`:114-116`). Doris is still told her answer is saved when the box is empty. |
| M9 | Partially fixed | Declining now clears the pastors' banner (`services_decisions.py:332-334`, `notifications.py:278-285`). Undoing an urgent approval clears the Dir/AD banner and restores the pastors' banner (`notifications.py:463,476,495,508,512-539`). Gap: undoing a **decline** of an urgent request restores nothing, because `_build_decision_undone_notices` returns early when `urgent_approval_emitted` is false (`:457`). The request is back to urgent and awaiting a pastor, but no pastor sees the banner. Fix: restore the pastors' banner on any undo that leaves the request `AWAITING_APPROVAL` + `AWAITING_CERTIFICATION`. |
| M10 | Partially fixed | The heading is fixed (`request_reconsideration_decide.html:18-24`). The Board date is now passed through (`views_requests.py:1497,1511`). The "This is final" line is present (`:86-88`). Still missing: decline mode has no reason prefill, no helper text and no preview of the final wording (`:70-89`). The prefills are in the context (`views_requests.py:1536`) but no script uses them. This is the last message Doris receives. |
| M11 | **Not fixed** | `request_decision_undo.html:22` still always says "Nothing has been sent to the requester. Their email is cancelled." **Judgement on FIX-3A's note:** this remains a Major. The "I've already told them by phone" tick now exists on A2, A3 and A9, so this path is real. If Ruth ticks it and then undoes, she is told nothing reached the requester, but Mrs. Hall already has the wrong news. The new decision's phone card won't appear until someone decides again, which could be days later. Fix: pass `has_email` and `approval.requester_phoned_at/by` to the sheet. No email and not phoned: "They don't use email, so nothing was sent." Phoned: "You told them by phone at 2:16 PM. Please call them back to say the decision is being looked at again." Also list the requester on the Dir/AD "Call to share a decision" card as needing a call-back. |
| M12 | Not fixed | Neither sheet says "{name}'s question will be withdrawn" (`request_approve.html`, `request_reject.html`). The row marker is not rendered (see N2). |
| M13 | Partially fixed | A "Why it's urgent" block exists (`_request_detail.html:67-75`), placed after the Decision card rather than first (acceptable). Still open: the A2n "Not urgent" sheet doesn't repeat the reason (`request_decline_urgency.html:12-16`; the view passes only `request_row`, `views_requests.py:1186`). The ≥1280 split view doesn't pass `urgency_line` into the include (`requests_list.html:135`), so at a desk Ruth can decide "Not urgent" without ever seeing why it was marked urgent. The label and the requester's words are still joined in one quote (`presentation.py:319-328`). |
| M14 | Fixed | No reveal on GET. `_reveal_on_post` (`views_requests.py:995-1007`) is used by A4 (`:1667-1669`), A5 (`:1725`) and A11 (`:1612`). This introduced N1. |
| M15 | Fixed | Header actions move after the Decision card below 1024 (`_request_detail.html:33-48,77-93`; `shell.css:3137-3149`). `leader-decision-390.png` shows Approve and Decline before "Ask for more photos". |

### New Majors

**N1. A4 (no-email): tapping "Show contact details" wipes the typed question, or is blocked by `required`.**
- **Where:** `request_question_ask.html:55` puts a submit button (`name="show_contact"`) inside the main form. The question field is `required` (`:34`). The view reads `question` and `phone_answer` only when `show_contact != "1"` (`views_requests.py:1672-1674`).
- **Impact:** Marcus types his question and then taps Show contact details to call. If the field is empty, the browser blocks the tap ("Please fill out this field"). If it's filled, the page reloads with the number and an empty question box, plus an empty "What did they say?" box.
- **Fix:** Always echo `question` and `phone_answer` from POST, add `formnovalidate` to the show-contact button, or move the reveal above the textarea as its own form, as A5 does (`request_question_record_answer.html:37-41`).

**N2. List-row markers never render: the template and the row object disagree.**
- **Where:** `requests_list.html:72` and `:91-102` read `row.line2_text` and `row.markers`. `RequestListRow` (`queries.py:94-118`) provides `undo_pending`, `question_open` and `reconsideration_deadline`, but no `markers` or `line2_text`. Django resolves missing attributes to an empty string, so nothing shows. `leader-requests-tabs-1280.png` confirms it: "Waiting on requester 5" appears next to 4 awaiting rows, and none of them shows "Question open".
- **Impact:** None of the step-3 row cues appear: Undo until, Question open, Can ask until, and Call to share a decision. This is the other half of M12, and it turns M1's "Call to share a decision" landing into a hunt through the Decided tab.
- **Fix:** Build `markers` (icon, label, attention) and `line2_text` in the list query or the view from the existing booleans. Add a `needs_phone_call` flag using the same predicate as `decision_phone_card`. Add a template test that renders a row with an open question and asserts "Question open".

### Minors spot-checked
- **Fixed:** m6 (`_decision_card.html:128`, `can_undo`), m13 (the two-column layout at 1280, `leader-undo-window-1280.png`), m16 (`request_reject.html:74`), m17 (`request_approve.html:40-42`).
- **Still open:**
  - m3: toasts lack the time and the undo deadline (`views_requests.py:1113`).
  - m7: "30 minutes" is still hard-coded (`request_decision_undo.html:17`).
  - m8: "Elder" is still hard-coded (`_decision_card.html:97`).
  - m9: "Not shown to the Administrator role." (`:69`, `:99`).
  - m15: the Board route still reads "Decline" (`request_reject.html:13,98`).
  - m21: the Urgent chip shows after a decision (`r10_secure_page.html:37`).
  - m22: the photo and close lines show on declined pages (`:182`, `:255`).
  - m25: `Good news, there:` (`requester_portal/notifications.py:50,339`).
- **New Minor:** after a standalone "Not urgent" review, the undo button reads "Undo certification" (`request_decision_undo.html:38`). Use "Undo" or "Undo 'not urgent'".

---

## Final re-check at 810210a

Reviewer: ham-ux-designer · 2026-09-29 · after FIX-3C, FIX-3D and FIX-3E.
Walked again as Ruth, Marcus, Doris and Mrs. Hall. I checked templates, views, JS and email builders; no code was run.

**Screenshots:** `leader-decline-sheet-390.png` has been regenerated and now matches the shared decline wording, so the earlier caveat is closed. `leader-requests-tabs-1280.png` and `leader-home-cards-1280.png` are also new, but the seed data has no open question, no no-email decision and no single-count card. They can't show N2, M1 or N-A below. No screenshot covers A4, A9, A11, the A2n sheet or the undo sheet after a phone call. The verdicts below rest on code.

**Result:** B1 is fixed. Of the other 12 open items, 11 are fixed, some with Minor residue. N1 is only partly fixed and is still a Major. There are 2 new Majors (N-A, N-B) and no new Blockers.

| ID | Verdict | Evidence |
|---|---|---|
| B1 | **Fixed** | A11 now reads the latest live approval at either stage, and only after its window closes (`views_requests.py:1722`; `queries.py:402-415`). The reconsider offer appears only for an open initial-stage decline (`views_requests.py:1754-1760`), and the approval script comes from the actual outcome (`request_decision_phoned.html:20-26`). Minor: a final decline's script has no "You're welcome to send a new request" closing. |
| N1 | **Partially fixed. Still a Major.** | Both fields are now echoed on every POST (`views_requests.py:1796-1801`; `request_question_ask.html:34,60`). The show-contact button still has no `formnovalidate` (`request_question_ask.html:55`), and the question is `required` (`:34`). The sheet itself tells Marcus to "Call them to ask, then record" (`:43`), so he taps Show contact details first, and the browser blocks him with "Please fill out this field." Fix: add `formnovalidate`, as A11 already does (`request_decision_phoned.html:42`). |
| N2 | Fixed (see N-B) | `RequestListRow.markers` / `line2_text` exist (`queries.py:132-164`) and are filled from the list query, including `needs_phone_call` (`:244-287`). The template renders them (`requests_list.html:72-78,100-102`). |
| M1 | Fixed | `_single_or` deep-links cards with a count of 1 (`attention.py:186-196,138,390`). Reconsideration, Call to share a decision and Certify urgent are now one card per request, linking straight to it (`:225-261,293-301,325-335,355-364`). Residue: see N-A (the new call-back card links to the wrong tab). |
| M2 | Fixed | The caption reads "What we'll tell the requester" while the decision is pending (`_decision_card.html:171`). |
| M6 | Fixed (Minor residue) | One source: `DeclineOutcomeParts` (`presentation.py:196-251`). E10/E13 use it (`requester_portal/notifications.py:389-398`), and so do the A3 preview (`views_requests.py:1411-1416`; `request_reject.html:75-78`) and the A9 preview (`views_requests.py:1660`; `request_reconsideration_decide.html:101-107`). Residue (Minor): no "Ask us to reconsider is on your request page" pointer and no E13 "Your request page stays open until {date}". The phone clause uses a literal `--` in the email (`presentation.py:240`); use a full stop. |
| M7 | Fixed (Minor residue) | A9 now checks for a future Board date inline and keeps the typed reason (`views_requests.py:1598-1609`). The A13 message now names who decided and when (`:1016-1029`). Residue (Minor): A2 still sends a future Board date to the generic redirect (`:1148-1151`), which loses the optional note. A2 doesn't re-tick `told_by_phone` on re-render (`request_approve.html:75`). A13 still has no "See what you wrote". |
| M8 | Fixed (Minor residue) | The draft is now cleared only on `?answered=` (`requester-questions.js:99-104`). Empty and too-long answers are told apart (`views_requester.py:1137-1146`; `r10_secure_page.html:105-113`). Residue (Minor): the empty-answer message still says "It's still here" (`:108`). The textarea has no `required` (`:120-122`). Any other `ValueError` is labelled "too long" (`views_requester.py:1140-1142`). |
| M9 | Fixed | A decline stores `banner_cleared` (`services_decisions.py:339`). Undoing it restores the pastors' banner from that stored fact (`notifications.py:503-507,546-578`). Undoing an urgent approval clears the Dir/AD banner (`:489-502`). |
| M10 | Fixed | Decline mode has reason radios, prefill with Replace / Keep mine, helper text, the live final-wording preview (which becomes "What to tell them by phone" when there's no email) and "This is final" (`request_reconsideration_decide.html:72-111,139-195`; `views_requests.py:1645,1660`). Minor: the preview opens with an empty quote until a reason is chosen. |
| M11 | Fixed (see N-A) | The sheet now branches on phoned / no email / email (`request_decision_undo.html:26-32`; `views_requests.py:1499-1524`). Minor: it says "You told them… (Marcus Reed)" when someone else made the call. Say "{name} told them" in that case. Minor: during the window, the Decision card still says "Nothing has been sent to the requester yet" after the phone tick (`_decision_card.html:151`). |
| M12 | Fixed (Minor residue) | Both sheets now say "The open question will be withdrawn." (`request_approve.html:93-95`; `request_reject.html:81-83`; `views_requests.py:1168-1174`). The row marker "Question open" renders (`queries.py:142-145`). Residue (Minor): the line is small grey text below the consequence block. Move it into the block and name the asker: "Andre's question to the requester will be withdrawn." |
| M13 | Fixed (Minor residue) | The A2n sheet repeats "Why it was marked urgent" (`request_decline_urgency.html:14-19`; `views_requests.py:1240-1245`). The split view gets `urgency_line` from `_build_detail_context` (`views_requests.py:624-626` → `requests_list.html:135`). Residue (Minor): the label and the requester's words are still one string (`presentation.py:347-356`). |

### New Majors

**N-A. The "Call them back · decision changed" card has no way to clear and links to the wrong tab.**
- **Where:** `attention.py:394-425`. The card clears only when a later `Approval` is marked phoned (`:411-415`). No screen or action records "called back". The only mention is on the undo sheet (`request_decision_undo.html:27`); the detail page and the Decision card say nothing. When there are two or more, the link goes to `?tab=decided` (`:424`), but after an undo the request is back in **Awaiting approval**.
- **Impact:** Marcus calls Mrs. Hall back and the card stays on Home for days, until someone decides again and marks the new decision as told. If the request is closed without a new decision, the card never clears. Opening it (count 1) shows a detail page with no call-back instruction. With two or more, he lands on a tab that doesn't list them. The same dead end M1 fixed has come back. "Decision changed" is also inaccurate: the decision was undone, not changed.
- **Fix:**
  - On the Decision card, for Dir/AD, show "{name} told the requester by phone at 2:16 PM, then the decision was undone. Call them back to say it's being looked at again." Add an action, **I've called them back**, that records actor + UTC + an audit event and clears the card.
  - Also clear the card when the request closes.
  - Link a card with two or more to `?tab=awaiting`.
  - Retitle the card "Call back · decision undone · HAM #NNN", one card per request, like the other phone cards.

**N-B. List rows lose their status chip and repeat each marker twice.**
- **Where:** `requests_list.html:72-78`. When `row.line2_text` is non-empty, line 2 shows the joined marker labels *instead of* the status chip and age. `requests_list.html:100-102` then renders the same labels again as marker chips. `line2_text` is just those labels (`queries.py:160-164`).
- **Impact:**
  - On the Decided tab, every open decline carries "Can ask to reconsider". Those rows lose the "Not approved" chip, so they can't be told apart from approvals. The rows needing a call lose it too.
  - On Awaiting, a row with an open question loses its age ("waiting 3 days").
  - Screen readers hear "Question open, Question open".
  - This breaks "make status obvious" (§52) on the list Ruth and Marcus scan most.
- **Fix:** Return `""` from `line2_text` until there is real tab-specific wording (for example "Pastor Ruth A. · Sep 28"), so line 2 always keeps the status chip and age and the markers appear once. Better still, add the time to the undo marker: "Can be undone until 2:45 PM". Add a template test: a declined row with an open question shows "Not approved" once and "Question open" once.

### Minors still open from earlier rounds (spot-checked, not re-verified in full)
m3, m8, m9, m15, m21, m22 and m25 were not in FIX-3C/3D/3E scope and are assumed still open. m7 is fixed (`undo_minutes` from the rules module, `request_decision_undo.html:17`; `views_requests.py:1525`). The earlier "Undo certification" Minor is fixed (`request_decision_undo.html:44`).
