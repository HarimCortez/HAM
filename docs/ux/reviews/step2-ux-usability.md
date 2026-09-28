# Step 2 (Intake) usability review

Reviewer: ham-ux-designer · 2026-09-28 · branch `feature/step-2-intake`
Spec: `docs/ux/intake.md` (R1–R12, L1–L11, §7 emails). Where they differ, the owner box in `docs/architecture/intake.md` wins.
Method: I walked each flow as Doris (older requester on a phone, large text), Mrs. Hall with Deacon James (no email, landline), Angela (laptop plus phone), Marcus (Director, desktop and phone), Pastor Ruth and Elder Samuel (approvers), and the Administrator. I read the templates, views and email builders and checked the screenshots in `docs/ux/screenshots/step2/`. I did not run the app, so findings about focus and the 200% text reflow come from reading code and CSS.

Severity: **Blocker**: the job can't be done, or the result is wrong or unsafe. **Major**: real friction, lost or garbled data, a misleading message, or an a11y failure. **Minor**: polish.

## Summary

| # | Sev | Area | Finding |
|---|---|---|---|
| B1 | Blocker | L2 photos | Leaders and approvers can't see requester photos. The detail page lists only "photo · ready" as text. |
| M1 | Major | R6, L2 | Hazards and visit days show as raw codes (`none_known`, `dogs_or_other_animals`, `0, 3, any_time`). |
| M2 | Major | Category and home type | The requester's 9 categories collapse into 8 different backend categories ("Carpentry & repairs", "Accessibility"). The requester sees "Roof" and "Single family home". |
| M3 | Major | R5 → L2/L9 | The optional "Anything else about reaching you" note is silently thrown away. The phone-check helper note never reaches Marcus. |
| M4 | Major | R2 | The urgent-reason label is added to the start of the requester's own text, and added again on every re-save ("Label. Label. text"). |
| M5 | Major | R3 | State is a blank, required, 2-character free-text box. It should be prefilled "Florida · Change". |
| M6 | Major | R8 (new link) | The code screen and code email use intake wording ("To send your request…", "Your answers are saved") when Doris is only asking for a new link. |
| M7 | Major | R11b | "Check on your request" sends a code email that has no screen to type the code into. The confirm page then says "finish sending your request". |
| M8 | Major | R8 across devices | After confirming by the email button on another device, the original tab says "couldn't find a pending code… Please start again", which invites a duplicate request. |
| M9 | Major | Form errors (a11y) | No `aria-invalid` or `aria-describedby`. The error summary is never focused. R6 summary links point at fields that aren't on the page. The certification ticks get no inline error. |
| M10 | Major | L9 phone check | The number shows as `+13055550177`, not a Call button. The checkbox is a small native box. The bottom nav covers the close links. |
| M11 | Major | L1 list | Clicking a row leaves the split view. Category and number filters are ignored on the phone-check and Awaiting tabs. Rows show a timestamp instead of an age. At 390 the filters push the list below the fold. |
| M12 | Major | L5 panel | The Earlier-request panel shows for the Administrator, and it shows pastors a request that is still waiting for a phone check (with a dead "Open"). No category or date is shown. |
| M13 | Major | Inbox | Updates aren't links. A pastor can't open "Request waiting for review · HAM #047" from the Inbox. |
| M14 | Major | R10 status | No status chip ("Being reviewed"), no "What happens next" line, and the greeting uses the full name. The Cancelled wording invites a new request even after a duplicate close. |

There are 22 Minor items after these (section 3).

---

## 1. Blocker

### B1. Leaders can't view request photos (L2)
- **Where:** `ham/web/templates/web/_request_detail.html:99-102`, which renders `{{ item.media_kind }} · {{ item.status }}` for each item.
- **Who:** Marcus, Pastor Ruth, Elder Samuel.
- **Impact:** §77 steps 1–3 exist so photos are there *before* approval (§45). We push Doris to add photos (R7 primary action, and the ≥60% uptake target). But the people deciding see "photo · ready" and nothing else. The job "understand the need" (L2 purpose) fails, and "Ask for more photos" (L11) makes no sense if leaders can't see the first set.
- **Fix:** Show a thumbnail grid (3-up at 390, 5-up in the detail pane) using the media service's view URLs. Each thumbnail opens a viewer with alt text "Photo 1 of 4, HAM #047". Show processing and failed states per item ("Getting this video ready…"). The Administrator keeps the count-only line (G6).

## 2. Major

### M1. Raw codes shown to requesters and leaders
- **Where:**
  - `requester/r6_review.html:38` joins `payload.hazards` directly. The screenshot `request-review-390.png` shows "none_known".
  - `_request_detail.html:89` prints `detail.known_hazards`, which stores codes plus the note (`requester_portal/services.py:329-331`).
  - `_request_detail.html:118` prints `preferred_availability` (for example "0, 3, any_time").
- **Impact:**
  - Doris sees jargon on the one screen where she checks her answers, right before she certifies them as true.
  - Marcus sees `none_known` in "Safety at the home", the safety-critical section. The template's "None that they know of." text only appears when the field is empty, so it never shows for real requests.
  - Weekday numbers mean nothing to anyone who reads them.
  - This repeats the step-1 lesson "no raw codes in copy".
- **Fix:** Use one label helper for hazards, availability, category, property type and relationship in all three places (R6, R10, L2). Store hazards and availability as structured values, or at least as codes with a separate note field, and render labels at display time. Show `none_known` as "None that they know of". Show the hazard note on its own line, "Note: …", in quotes. The current parenthesis parsing on R10 (`views_requester.py:693-714`) breaks when the note contains a comma.

### M2. Category and home type vocabulary mismatch loses the requester's answer
- **Where:**
  - `requester_portal/services.py:297-315` maps 9 portal categories onto the model's 8. *Doors, windows or locks* and *Floors or stairs* both become "carpentry".
  - `requests/models.py:30-40` uses different labels.
  - `views_requester.py:682-690` shows the stored code with underscores replaced.
- **Impact:**
  - Doris picks "Ramps, rails or grab bars". Her page says "Accessibility", and the leaders' list, email subject and detail say "Accessibility". The spec (L1 rows, L8, L-E1 subjects) uses her words.
  - Two categories collapse into one, so leaders lose information (doors vs floors).
  - Doris sees "Single family home" when she tapped "House". She sees "Yard outdoor" and "Carpentry" for choices she never made.
  - Q-109 decided the 9 plain-language categories.
- **Fix:** One vocabulary. Change `AssistanceRequest.NeedCategory` and `PropertyType` to the Q-109 and Q-110 codes and labels, and delete the translation tables. That needs a migration, but there are no production rows yet. Until then, never show a derived label to the requester. If the model must keep the old set, log it as a PRD-GAP and let the ham-prd-guardian decide.

### M3. The contact note is dropped (R5 "Anything else about reaching you or visiting?")
- **Where:**
  - Collected in `views_requester.py:247`.
  - Missing from `forms.validate_intake_payload` (it never reaches `cleaned`).
  - Missing from `SubmittedRequestPayload` (`requester_portal/services.py:340-363`).
  - No model field (`requests/models.py` has only `cancel_note`).
- **Impact:**
  - Journey §3.3: Deacon James writes "My neighbor James Carter helped me fill this in". Marcus never sees it on L2 or L9, even though L9's wireframe shows it for exactly this call.
  - "Best time to call: after 4 PM" also disappears.
  - The field asks for effort and then throws the answer away. Doris would reasonably assume leaders read it.
- **Fix:** Add a C-class `contact_note` to the request. Carry it through `cleaned` and the payload. Show it on L2 under "Visits and contact preference" and on L9 under the name and number. Show it on R6 under "Reaching you". Until then, remove the field rather than collect it silently (spec §11.4 already lists it as a data assumption).

### M4. The urgent reason rewrites the requester's own words
- **Where:** `views_requester.py:203-208` sets `justification = f"{label}. {justification}"`. `r2_need.html:66` then echoes that value back into the "Anything else…" textarea.
- **Impact:**
  - Doris goes back or edits from R6, and her textarea now starts with "Water is coming in or damage is getting worse." Text she didn't type.
  - Each Continue adds the label again ("Label. Label. my words"). Pastors certifying urgency read garbled text.
  - Related problem: if she ticks urgent but picks no reason, the error "Tell us why this is urgent." appears under a field labelled "(optional)". The reason radios get no error and no `id` (`urgency_reason` isn't in `_STEP_FIELDS[STEP_NEED]`).
- **Fix:** Store `urgency_reason` (code) and `urgency_justification` (free text) separately. Compose "Reason label. Extra text" only for display on L2. Validate the reason chip as required when urgent ticked, with the error on the "Why is it urgent?" fieldset: "Choose why it's urgent." Make the textarea required only for "Something else". Its label should then drop "(optional)" when that chip is chosen, or the message should read "Tell us a little about why it's urgent."

### M5. State is a required blank field (R3)
- **Where:** `requester/r3_home.html:67-71` has an empty `<input maxlength="2">` labelled "State". The validator requires it (`forms.py:114`).
- **Impact:**
  - It adds a 7th typed field against the spec's 6.
  - Doris types "Florida", `maxlength` stops her at "Fl" with no explanation, and she hesitates.
  - It has no `autocomplete="address-level1"`.
  - The spec says to prefill it from the church profile.
- **Fix:** Show "Florida · Change" as text, prefilled from `church_profile().state`. **Change** reveals a `<select>` of state names with `autocomplete="address-level1"`. Never ask for a 2-letter code.

### M6. The R8 code screen and code email use intake wording for a new link
- **Where:**
  - `requester/r8_verify.html:6,10-14` always shows "Last step", "Your answers are saved. To send your request…" and "Or tap Confirm my email", even when `purpose == link_regeneration`.
  - `verification.py:45-49` uses the subject "Confirm your request" and the body "Your answers are saved" for both purposes.
- **Impact:** Doris's link expired eight months after her project (§3.5). She taps **Send me a code** and is told her answers are saved and she's about to "send your request". She worries she's filing a new request, or that the old one was lost.
- **Fix:** Branch the copy on purpose.
  - New link, R8: no eyebrow. h1 "Check your email". Body: "We sent a 6-digit code to **d•••@gmail.com**. Enter it to open your request page. Or tap **Open my request** in that email."
  - New link, email subject: "Your {church.shortName} HAM code". Body: "Your code is 482 913. Use it to open your request page for HAM #047. It works for {minutes} minutes."

### M7. "Check on your request" (R11b) sends the wrong email and a dead-end code
- **Where:** `requester_portal/services.py:257-272`. `find_my_request` calls `request_link_regeneration_code`, which sends the code email. R11b never sets the R8 session, so there's nowhere to type the code. The email's link opens `confirm_link.html:7-8`: "Confirm your request · Tap Continue to finish sending your request". A second email (E3 "Here's your new link") follows.
- **Impact:**
  - Doris has lost her emails. She gets "Your code is 482 913" with nowhere to enter it.
  - She taps the link and is told she's finishing *sending* a request.
  - Then a third email arrives.
  - If she has two requests, nothing says which HAM # each email is for.
  - Spec E4 was one email with one button: "Your HAM request #047 · Open my request page".
- **Fix:**
  - For R11b, send one E4 email per matching request. Subject: "Your HAM request #047". Body: "Here's the link to your request." with the scanner-safe **Open my request page** button.
  - Consuming that link issues the new link and lands on R10. Skip the separate E3 in that case.
  - Make `confirm_link.html` purpose-aware. New link: h1 "Open your request", button **Open my request page**. Intake: keep the current copy.

### M8. Confirming on another device strands the first tab and invites a duplicate
- **Where:**
  - `views_requester.py:497-507`: the `no_challenge` result says "We couldn't find a pending code for this email. Please start again."
  - `confirm_link.html:19-22`: an already-used link says "…try the code instead, or start again", with a link to Ask for help.
  - R8 has no focus or poll check for "already confirmed" (spec R8 "Confirmed from another device").
- **Impact:**
  - Angela taps **Confirm my email** on her phone, and the request is received.
  - Back on her laptop she types the code and is told to start again. She does, and HAM #048 arrives as a duplicate that Marcus has to close.
  - Doris double-taps the email button and gets the same "start again" advice.
- **Fix:**
  - When the draft behind the pending verification has already been submitted, R8 and the used-link page should say: "Your request was already received. Your request number is HAM #047. We've emailed you a link to your request page." Show the masked email. Don't offer "start again".
  - Add a lightweight check on `visibilitychange`/focus on R8 that redirects to the welcome page once the draft is submitted.
  - Replace "Please start again" everywhere with a recovery that keeps the draft: "Send a new code".

### M9. Form error handling is not accessible, and the R6 summary has dead links
- **Where:**
  - `requester/_error_summary.html:5-9` has `role="alert"` and `tabindex="-1"`, but nothing moves focus to it. No script in `frontend/src` does.
  - No field anywhere in R2–R6 has `aria-invalid` or `aria-describedby`, and help text isn't linked to its field.
  - On R6, `views_requester.py:353` passes *all* payload errors. The summary links to `#id_line1`, `#id_email` and others, which don't exist on R6, and `#id_attested_statements`, which doesn't exist at all.
  - The certification ticks have no inline error or error styling.
  - `r4_safety.html:20` legend is a visually hidden "Hazards", so the spec's "Choose at least one" hint isn't in the legend.
- **Impact:**
  - A screen-reader user hears the alert but lands at the top of the page with no link to the fix.
  - A sighted user on R6 taps "Street address is required." and nothing happens.
  - This fails WCAG 3.3.1 and 1.3.1 (programmatic association), and the spec §8 "Errors" rules.
- **Fix:**
  - Focus the summary on render. A one-line `autofocus`-style script, or render the summary as the first focus target.
  - Add `aria-invalid="true"` and `aria-describedby="id_x-error id_x-help"` to each field, and give error `<p>`s ids.
  - On R6, list errors from earlier steps as links to that step's Edit URL, for example "Street address is missing · Fix in The home". Give the certification group a fieldset with legend "Please confirm", an id, and an inline error.
  - Make the R4 legend visible, or put the question in it: "Is there anything at the home our volunteers should know about? Choose at least one."
  - Messages: say how to fix, not "X is required". For example: "Enter your street address", "Enter the city", "Choose who owns the home" (not "relationship to the property").

### M10. The phone-check sheet can't place the call (L9)
- **Where:** `request_phone_check.html:13` prints `{{ revealed.phone }}` as text. The value is E.164, `+13055550177` (screenshot `leader-phone-check-sheet-390.png`). Lines 31-35 use a bare native checkbox. In the screenshot the fixed bottom nav covers "They no longer need help" and the no-answer note.
- **Impact:**
  - Marcus is on his phone. He has to copy the number by hand.
  - The unformatted E.164 is hard to read aloud to Mrs. Hall when he checks "is this the best number?".
  - The tick target is about 13px, and the 48px row isn't there.
  - The close links are hidden behind the nav.
  - The spec's 4-tap target (open → Record → **Call** → tick → Verified) isn't met.
- **Fix:**
  - Add a Secondary lg `tel:` button "Call (305) 555-0177", with accessible name "Call Ruth Hall, (305) 555-0177", above the tick. Format numbers for display with `phonenumbers` NATIONAL format everywhere: L2 reveal, L9, R7N.
  - Make the tick a 48px checkbox card with the copy "I spoke with Ruth Hall by phone, and they confirmed they asked for this help." (not "she or he").
  - Pad the sheet bottom by the nav height, or use a full-screen sheet without the tab bar as the spec says. Put the primary in a sticky bar.
  - Move `<details>` out of the `<p>` (invalid nesting).
  - Show the contact note (M3).

### M11. The Requests list is hard to scan and its filters don't work (L1)
- **Where:**
  - `requests_list.html:49`: rows link to the standalone detail page, so at 1280 each click leaves the split view. "Back to Requests" (`request_detail.html:8`) also drops the tab.
  - `views_requests.py:68-79`: `category` is applied only on the All tab, and `q` is ignored on the phone-check tab.
  - `requests_list.html:56-61` shows "12:31 PM EDT on Sep 28, 2026" rather than an age.
  - There are no photo-count or "Updates by phone" markers.
  - At 390 (screenshot) the three filters and the Filter button fill the first screen, and the tab row is cut off with no overflow cue.
- **Impact:**
  - Marcus's 10-minute triage becomes click, back, re-find the tab.
  - He picks a category on Awaiting approval and the list silently doesn't change, so he assumes the filter works and misses items.
  - Long timestamps hide the urgent-first, oldest-first reasoning.
  - Pastor Ruth on her phone sees no requests without scrolling.
- **Fix:**
  - At ≥1280, link rows to `?tab=…&id=<uuid>` (the view already supports it) and keep the list. Use the standalone page only below 1280. Make "Back" return to `?tab=` of origin.
  - Apply the filters on every tab, or hide the controls where they don't apply.
  - Show age in words ("3 days", "2 h"), with the full time in a `title`/`<time>` element.
  - Add the `image` "4 photos" and `phone` "Updates by phone" markers.
  - At 390, collapse the filters behind a "Filters · n" button (bottom sheet), and give the tabs a scroll affordance with visible counts.

### M12. The Earlier-request panel shows to the wrong people and hides useful facts (L5)
- **Where:** `views_requests.py:178`. `outcome_summary(request_row)` runs for every viewer, and `_request_detail.html:53-78` renders it with no permission check. The screenshot shows HAM #004 "Needs a phone check" in the panel.
- **Impact:**
  - The Administrator sees match chips such as "Same address" and "Same phone", which the spec (§9, L2 Administrator) excludes.
  - Pastors see a phone-check request they're not allowed to open, so "Open" is a dead end.
  - There's no category or date per match, so Marcus can't tell "same leak yesterday" from "different job in 2025" without opening each one.
- **Fix:**
  - Gate the panel on `request.history.view` (or a dedicated `request.matches.view`).
  - For pastors and the Board rep, leave out matches that are still NEEDS_PHONE_CHECK.
  - Row format: "HAM #047 · Roof or ceiling · sent Oct 5 · [Same email] [Same address] · (Awaiting Approval)".
  - Show "Close this one as a duplicate…" once under the panel, prefilled with the newest match, not repeated on every match.
  - Hand off to ham-privacy-security-reviewer.

### M13. Inbox updates can't be opened
- **Where:** `inbox.html:39-44`. Each update is a `<span>` title plus time, with no link and no mark-as-read.
- **Impact:** The spec's route for approvers is Inbox or email, "request waiting · HAM #047", then L2. From the Inbox that path dead-ends. Pastor Ruth has to go to Requests and find the number herself, which breaks the "≤3 taps from notification to decision" target that step 3 builds on.
- **Fix:** Make each update row a link to its subject (`request_detail`). Mark it read on open. Give it the accessible name "Request waiting for review, HAM #047, Roof or ceiling, 2 hours ago".

### M14. The secure page doesn't make status obvious (R10)
- **Where:**
  - `requester/r10_secure_page.html:28-31`: the status card has only a sentence. There's no chip ("Received" / "Being reviewed" / "Closed") and no "What happens next".
  - Line 24: "Hi {{ row.full_name }}" (the screenshot shows "Hi Visual QA Requester"). The spec's h1 is "Your request · HAM #047".
  - `projection.py:38-41`: every Cancelled status ends "You're always welcome to submit a new request."
  - Lines 42-48: "Ask for help again" shows for every cancel reason.
- **Impact:**
  - "Where does my request stand?" is the page's whole job, and the sentence alone is weak.
  - After a duplicate close, Doris is invited to send it a third time.
  - "Submit" is jargon.
- **Fix:**
  - Add the 32px chip (icon + word) plus the spec sentence, and a "What happens next" line per status (N§5).
  - Greet by first name. Make the h1 "Your request · HAM #047".
  - Use the spec's per-reason Cancelled wording. Duplicate: "We already have this same request from you, so we closed this copy. Your other request is still open. If that's not right, please call us." Show "Ask for help again" only for the withdrew reason.

## 3. Minor

1. **R1:** "Start over" (`r1_start.html:25-29`) sits outside the action area and uses `confirm()`. That's fine, but the resume prompt and emergency alert both use `role="status"`, so they're announced on load. Use plain text for the static alerts.
2. **R2:** "Start over" is rendered below the sticky action bar (`r2_need.html:77-81`), not beside Continue as the spec shows. The microphone tip is missing. `maxlength="2000"` is a hard stop; the spec asks for a soft counter at 1,800.
3. **R2–R6 page titles:** "Your need · X HAM". The spec wants "Step 1 of 5 · Your need · Ask for help · X HAM". The eyebrow says "Last step" on R6, but the spec gives "Last step" to R8 and "Step 5 of 5 · Check and send" to R6.
4. **R3:** The tenant info line (landlord's written permission, Q-104) is missing under "I rent it".
5. **R4:** The "Tell us more (optional)" label contradicts its required-for-"Something else" error. When "None that I know of" clears the other boxes, nothing is announced politely (spec §8).
6. **R5:** "How should we contact you?" isn't prefilled to Email, so it's an extra required tap and a likely error for Doris. There's no email typo suggestion. The helper text lacks "You can use a family member's or friend's email if they say it's OK" (Q-025, Q-105).
7. **R6:** The summary cards leave out relationship, home type, urgent reason, visit times and contact preference. Cards use h3 under h1 (skips h2). The privacy-statement link (Q-131) is missing. There's no double-send spinner or lock.
8. **R8:** "Choose 'I don't use email' instead" (`r8_verify.html:53`) goes to R5 without ticking the box. Link to R5 with `?no_email=1` pre-ticked and focus on it. "Wrong email? Change it" doesn't focus the Email field.
9. **R8:** No resend countdown. The cooldown message "once the current email has had a moment to arrive" gives no time; say "You can ask for a new code in 0:24." `minutes|default:15` in the template is a literal fallback for a rules value.
10. **R8 after a rate limit:** the page still says "enter the 6-digit code we sent" when none was sent. Swap the body text to the R12 "Code limit for today" copy.
11. **Code email:** it says "use the button below", but the body is plain text with a bare URL. Say "Or open this link:" until HTML email exists.
12. **R7 welcome:** the h1 lacks the first name. There's no "I'll add photos later" link. "What happens next" uses the normal wording even for urgent requests (the email uses the urgent wording). `?welcome=1` persists in bookmarks, so refreshing weeks later still says "Thank you. We've received your request." Drop the query after first render, or show welcome only while the status is Submitted or Awaiting.
13. **R7N:** the phone shows as `+13055550177` (E.164). Doris needs "(305) 555-0177" to recognize her own number. The h1 isn't focused.
14. **R10:** masked email and phone have no screen-reader text ("email ending in example dot org, phone ending in 0142"). "Hidden · Miami 33125" should read "Street address on file · Miami 33125". The photo count is shown without thumbnails of her own photos. The footer "This link works until…" is missing. When `church.phone`/`email` are unset, "How to reach us" says only "We're glad to help." Treat the church phone as required in church settings, since every recovery path depends on it (R7N, R11a, R12).
15. **R12:** the neutral page lacks "use the newest email from us, or call {church.hamPhone}".
16. **Draft expired mid-form:** `views_requester.py:285` says "Your answers weren't saved yet." That's inaccurate: they were saved and have expired. Use "It's been more than a day, so we cleared your answers to keep them private. Please start again." The session-storage copy and offline sync from spec §5 aren't built, so a dropped connection during Continue relies on the browser Back cache. Track this as a follow-up for field conditions.
17. **R9:** "Take a photo" is Secondary; the spec makes it the primary-style tile. The limits line is good. The `aria-live` summary exists.
18. **L2:** the urgent Awaiting banner ("Waiting for a pastor to certify…") is missing. Contact reveal is a POST that renders the page directly: refresh asks to resubmit, and in the split view it jumps to the standalone page. Use POST-redirect-GET with focus moved to the revealed region. "What's needed" is empty in `leader-request-detail-1280.png`; confirm this is seed data.
19. **L10 close sheet:** the consequence line is generic ("unless this is spam or a test"). For no-email requests it still promises an email. Adapt it: "Doris will get a short, kind email." / "No email will be sent." After an error, the view re-puts the free-text note into the URL query (`views_requests.py:347-349`), which ends up in logs and history. Re-render with POST data instead (privacy reviewer).
20. **L11:** the success toast "Asked HAM #047 for more photos" should read "Asked for more photos on HAM #047 · 7:58 PM". The no-email state should be a disabled button with the reason, not a replaced page.
21. **Home:** "1 request(s) need a phone check" (`requests/attention.py:89`) should pluralize and add age: "1 request needs a phone check · waiting 1 day". There's no urgent phone-check card ("Urgent · HAM #050 needs a phone check before pastors can see it · waiting 3 h [Call now]").
22. **Urgent banner:** `role="alert"` re-announces on every page load until acknowledged. Announce once (on arrival), then use `role="region"` with a label.

## 4. Checks that passed
- **Answers survive errors:** step errors re-render with values kept (422). A wrong or expired code keeps the draft. Messages include tries left.
- **"I don't use email" path:** explicit checkbox, reassuring info line, R7N copy matches the spec, no code or link. L8 tab and default tab logic are correct. Phone checks are blocked while impersonating.
- **Leadership list rows** show HAM # and category only (Q-132). Email subjects are neutral.
- **Masked contact block** has an accessible name that includes the HAM #. The Director's reveal isn't labelled "logged"; everyone else's is.
- **Close sheet** offers only the Q-107 reasons (plus "couldn't reach them" on phone-check requests, Q-140) and carries the "need or eligibility goes to the approvers" helper.
- **200% text:** `.choice-grid` uses `minmax(min(100%, 11em), 1fr)`, so cards drop to one column as text grows. The sticky action bar needs a visual check at 200% on 390 to make sure it doesn't cover the focused field (WCAG 2.4.11).

## 5. Success-measure impact
- **Doris's typed fields:** 7 → 8 (State, M5), plus an extra error-prone tap (contact preference, Minor 6).
- **Phone check:** the 4-tap target is unreachable without the Call button (M10).
- **Check status from email:** R11b needs 3 emails and a confusing confirm step instead of 1 email and 1 tap (M7).

## 6. Hand-offs
- **ham-frontend-engineer:** B1, M1, M4, M5, M6, M7 (copy), M8, M9, M10, M11, M13, M14 and the Minor items.
- **ham-backend-engineer / ham-architect:** M2 (vocabulary), M3 (contact note field), M1 (structured hazards and availability), M7 (E4 builder), M12 (panel gating).
- **ham-privacy-security-reviewer:** M12 (Administrator and pastor match visibility), Minor 19 (note in URL), L9 reveal logged again on each GET after a failed submit.
