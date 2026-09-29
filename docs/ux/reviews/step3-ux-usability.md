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
