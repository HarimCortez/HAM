# Step 2 (Intake): UI visual QA

> The 163 working screenshots from this pass were not committed (17 MB); the curated PR screenshots are in `docs/ux/screenshots/step2/`.

ham-ui-designer · 2026-09-28 · branch `feature/step-2-intake` (HEAD `fd5228f`) · report only; no code, template or CSS changed in this pass.

**Specs checked against:** `design-system/screens/intake.md` (cited **S§n / R2 / L2**), `design-system/components.md` C§19–§32 (**C§n**), `design-system/tokens.css` v1.3.0, CLAUDE.md "Design".
**Dark mode:** out of scope for V1 (Q-016, decided: light only), so it was not captured.

## Method
- **Existing captures** reviewed: `docs/ux/screenshots/step2/*` (18 files).
- **New captures** in `docs/ux/screenshots/step2-qa/`, made against a separate dev server (port 8040, DB `ham_qa`, seeded with `seed_dev` + `seed_dev_requests` + flows driven by a throwaway Playwright script).
  - Requester R1–R12: at 390×844, 768×1024 and 1280×800. Also at 390 with 200% root text (`*-390-text200.png`) and at 195 CSS px, which equals 200% page zoom (`*-195-zoom200.png`).
  - Leadership: at 390/768/1280/1440 for Director, Pastor and Administrator (`dir-*`, `pastor-*`, `admin-*`).
- **Automated checks per page:**
  - Horizontal overflow (`scrollWidth > innerWidth`).
  - Action-bar height as a percentage of the viewport.
  - Interactive elements under 44px tall.
  - axe-core 4.10 (WCAG 2.0/2.1/2.2 A+AA + best-practice) at 390 and 1280.
- **Full-page screenshot caveat:** full-page captures draw sticky/fixed bars (action bar, bottom nav) at their viewport position, partway down the image. That is a capture artifact, not overlap, and it was not counted as a finding.
- **Not verified:** R11a (a genuinely expired link) and the urgent phone-check Home card/app-wide banner for the Director. Neither was reachable with seed data.

## Summary
| Severity | Count |
|---|---|
| Blocker | 3 |
| Major | 17 |
| Minor | 22 |

The requester flow is readable and calm at 390 with normal text, and the leadership list/detail content is all there. Two things fall short:
- **The large-text contract (S§0.2), the owner's hard requirement, fails.** At 200% text or 200% zoom the primary button is pushed off-screen and several pages scroll sideways.
- **The step's shared form primitives (fieldset/legend, radios in lists, long values) have no base styles.** This shows as browser-default boxes, raw enum values and cramped targets across both sides.

Most fixes are small, shared CSS rules, not per-screen work.

---

## Blockers

### B1. At 200% text the sticky action bar pushes the primary off-screen (R3–R6, R8, and every step with Back)
- **Where:** 390 + 200% text (`r3-home-bottom-viewport-390-text200.png`) and 195px / 200% zoom.
  - Continue measures 221px wide with its right edge at x=433 in a 390 viewport, so it is half clipped.
  - Send request (R6) has its right edge at x=411.
  - The page scrolls sideways (scrollWidth 433 on R3/R4/R5).
- **Code:** `shell.css:1555` `.action-bar__inner { display:flex }` has no wrap and no container query. Buttons are `flex:none` for Back and `flex:1` for the primary but can't shrink below their text.
- **Spec:** S§0.2 items 1–2; C§22 "Large text: under `22em` bar width, Back leaves the bar … the bar holds the primary only".
- **Fix:**
  - Make `.action-bar` a size container (`container-type: inline-size`).
  - Add `@container (max-width: 22em) { .action-bar__inner { flex-direction: column-reverse; } .action-bar__inner .btn { width: 100%; } }` as the minimum.
  - Better, per spec: render Back a second time in the flow after the last field and hide the in-bar Back under 22em.
  - Also add `flex-wrap: wrap` as a fallback.

### B2. Long unbroken values cause horizontal page scroll (R6, R7, R10, R8, R11b sent, L2)
- **Where and how wide:**

  | Screen | 390 | 390 + 200% text | 195 (200% zoom) |
  |---|---|---|---|
  | R6 | 601 | 1200 | 601 |
  | R7/R10 | 527 | 1053 | — |
  | L2 | 520 (`dir-detail-urgent-photos-390.png`) | — | — |
  | R8 | — | 553 | 282 |

- **Causes:**
  - A description with a long unbroken string (a pasted URL behaves the same).
  - A long street name.
  - At large text, an ordinary email address (`doris.pennington.longname@example.org`).
- **Code:** `.summary-card__highlight` (shell.css:1604) is the only element with `overflow-wrap:anywhere`. These values have no wrapping:
  - `r6_review.html:22,30`
  - `r10_secure_page.html:53,61–62`
  - `r8_verify.html:12` (`<strong>{{ email }}</strong>`)
  - `r11b_find_request.html` (sent state)
  - `_request_detail.html:82,134`
- **Spec:** S§0.2 item 1; C§18 preamble ("any value that can be long and unbroken … `overflow-wrap: anywhere`"); S§6 checklist.
- **Fix:**
  - One utility, `.u-wrap-anywhere { overflow-wrap: anywhere; }`, applied to every user-entered value (description, address, email, name, file names) on requester and leadership pages.
  - Simpler still: set `.public-shell p, .public-shell dd, .public-shell li, .request-detail p, .request-detail dd { overflow-wrap: anywhere; }`.

### B3. Fieldsets have no reset: browser-default border and legend, and they overflow at large text (all R steps, L10)
- **Where:**
  - Every requester fieldset ("What kind of help?", "Whose home is it?", "Type of home", hazards, contact method, visit times) renders as a grey default-bordered box with an inline 16px legend (`request-form-390.png`, `r3-home-tenant-390.png`, `dir-close-390.png`).
  - At 195px the fieldsets are wider than the viewport (`fieldset.form-field` right edge at 207–232 on R2–R5). This comes from the UA default `min-inline-size: min-content`.
  - The default fieldset padding (about 12px + 2px border) also narrows the choice grid, which is why the category and "Type of home" grids fall to **1 column at 390** instead of the specified 2.
- **Code:** `shell.css` has no `fieldset` / `legend` rule at all. The fieldsets carry `.form-field` (shell.css:638), which only sets flex.
- **Spec:** S§0.3 ("main question of a step (fieldset legend) `type-h2`"); C§19 A11y ("every set is a fieldset + legend (`type-label`, or `type-h3` when it's the step's main question)"); S§0.2 item 1.
- **Fix:**
  ```css
  fieldset { border: 0; margin: 0; padding: 0; min-inline-size: 0; }
  legend   { padding: 0; font: var(--ham-type-label-weight) var(--ham-type-label-size)/var(--ham-type-label-line-height) var(--ham-font-ui); margin-bottom: var(--ham-space-3); }
  .public-shell fieldset > legend { font: var(--ham-type-h2-weight) var(--ham-type-h2-size)/var(--ham-type-h2-line-height) var(--ham-font-ui); }
  fieldset + fieldset, fieldset + .form-field { margin-top: var(--ham-space-8); }
  ```
  Secondary groups ("Why is it urgent?", visit days) use `type-h3`. This restores 2 columns at 390 with no other change.

---

## Major

### Requester

**M1. Raw codes shown to the requester and to leadership**
- **What shows:**
  - R6 "Safety at the home" shows `none_known` / `dogs_or_other_animals` (`r6_review.html:38`, `payload.hazards|join`).
  - L2 "Safety at the home" shows `dogs_or_other_animals` (`_request_detail.html:89`).
  - L2 "Visits and contact preference" shows `1 · prefers email`: the availability day index (`_request_detail.html:118`).
- **Spec:** R6 summary card (C§23); L2 "Safety at the home: each hazard as a row with its R4 icon in `tone.attention.icon` + label + the requester's words"; "None that I know of" plain `text.secondary` with `shield-check`.
- **Fix:**
  - Map codes to labels in the view (`hazard_labels`, availability labels) and render them as a list.
  - On L2, show each hazard as icon + `type-label` + quoted note.

**M2. Action bar is not the last thing on short pages, and secondary links sit below it (R1, R2, R8, R12, R11b)**
- **What happens:**
  - On R1, "Already asked? Check on your request" renders **after** the bar (`request-start-390.png`).
  - On R2, Start over is a separate form **after** the bar (`r2_need.html:77–81`).
  - On R8, Resend / Change it / Didn't get it all render after the bar (`verify-code-390.png`).
  - On short pages the bar therefore floats mid-screen with content under it, and on R2 the Start over target ends up under the bar in the thumb zone.
- **Spec:**
  - C§22 layout `[Back / Start over (Ghost)] [Primary]`.
  - R1 wireframe puts the links above the bar.
  - R8 puts Resend "on its own row below the field" and before the bar in DOM and visual order ("h1 → code → Resend → Change it → Didn't get it → Confirm").
- **Fix:**
  - Move secondary links and Resend above `.action-bar` in the templates (`r1_start.html:41–42`, `r8_verify.html`).
  - Put Start over inside `.action-bar__inner` as the Ghost via `form="start-over-form"` on a button, keeping the second `<form>` elsewhere.
  - At `<768` give `.public-shell__content` `display:flex; flex-direction:column`, and the form `flex:1`, so the bar sits at the viewport bottom on short pages.

**M3. R2–R5 choice cards: no icons, wrong label weight, radio misaligned**
- **What shows:**
  - The cards have no Lucide icons (spec lists one per option for R2, R3, R4, R5).
  - The label is `type-body-lg` **400** because `--ham-type-body-lg-weight` is 400. The fallback `600` in `shell.css:1463` never applies.
  - The radio sits about 12px lower than the first text line (`margin-top: 2px` + `align-items: flex-start` against a 28px line height), so every card looks off.
  - `margin-bottom: space-3` on each card (shell.css:1466) doubles the grid `gap: space-2`, making the vertical rhythm uneven.
- **Spec:** C§19 anatomy (icon `size.icon-lg`, label `type-body-lg` 600, text top-aligned with the control); R2/R3/R4 icon lists.
- **Fix:**
  - `font-weight: 600` on `.choice-card > span:first-of-type`.
  - `margin-top: calc((var(--ham-type-body-lg-line-height) - 24px) / 2)` on the input, or `align-items: center` for single-line cards.
  - Remove `margin-bottom` inside `.choice-grid`.
  - Add the icon span (`<svg class="choice-card__icon">`, `width: max(1.25em, var(--ham-size-icon-lg))`, `text.secondary`, `text.brand` when `:has(:checked)`).

**M4. Native 13px radios/checkboxes in chips and app sheets**
- **What shows:**
  - The `.choice-chip` input is 13×13 (R2 "Why is it urgent?", R5 visit days), because `shell.css:1520` sets no size.
  - L10 close reasons are bare 13×13 radios in a default fieldset (`request_close.html:22`).
  - The L9 statement is a 13×13 checkbox inside bold text (`request_phone_check.html:33`).
  - The labels are clickable, so WCAG 2.5.8 technically passes, but these are the hardest controls to hit on the screens a Director uses on the phone.
- **Spec:**
  - C§19 chip (selected shows a leading `check` icon; min height `size.target-min`).
  - L10: "3 radio choice cards (C§19, app size, 1 column)".
  - L9: "statement choice card".
- **Fix:**
  - Reuse `.choice-card` / `.choice-card--statement` in L9/L10.
  - For chips, size the input at 20px, or hide it visually and show the `check` icon on `:has(:checked)`.

**M5. R7/R10 status card has no status chip and duplicates the h1**
- **What shows:**
  - The card says only "We've received your request."
  - The "Received / Being reviewed" chip is missing, and so is "What happens next" inside the card.
  - The Urgent chip is plain text with no `siren` icon.
  - `r10_secure_page.html:28–31`.
- **Spec:** C§26 (chip row at `size.chip-lg` with icon + requester label, sentence, "What happens next" list); principle "status at a glance".
- **Fix:** Render `chip chip--info` with `inbox`/`hourglass` icon + requester label from the C§26 table. On R10, move "What happens next" into the card.

**M6. R10 hierarchy inverted: "Hi Visual QA Requester" is the h1 (full name), and the request title is a paragraph**
- **Where:** `r10_secure_page.html:24–25`.
- **Spec:** R10 "Hi {first name}" `type-h3` `text.secondary`, then h1 "Your request · HAM #047".
- **Fix:** Swap the elements and use the first name only. R7N shows the same first-name problem: "Thank you, No." came from "No Email QA Requester". Use the saved first-name field, or fall back to "Thank you."

**M7. Success hero is a text "✓" at body size**
- **Where:** `r10_secure_page.html:8`, `shell.css:1717`.
- **Why it fails:** `font-size: var(--ham-size-icon-xl)` on a text glyph renders at about 14px optical size in `tone.success.icon` (`request-received-390.png`).
- **Spec:** C§26 `circle-check-big` at `size.icon-xl`.
- **Fix:** Use the sprite `<svg width/height = size.icon-xl>` with `aria-hidden`.

**M8. Requester metadata below `type-body`**
- **What shows:**
  - kv-list labels on R7/R10 are `type-small` 14px (`shell.css:1030` `.kv-list dt`).
  - The R7 "What happens next" list items are 15px (`ol li` is not covered by `.public-shell p`).
  - Field helpers are `type-small` where not wrapped in `<p>` (`.form-field__help`, shell.css:715; saved only because `.public-shell p` wins on most helpers).
  - Field errors are `type-small`.
- **Spec:** S§0.3 "helper/hint `type-body` (never below `type-body`)"; lists `type-body-lg`.
- **Fix:** `.public-shell .kv-list dt, .public-shell .form-field__help, .public-shell .form-field__error { font-size: var(--ham-type-body-size); line-height: var(--ham-type-body-line-height); }` and `.public-shell li { font: inherit from p }`.

**M9. Requester desktop is a stretched mobile column (known simplification: judged Major, not Blocker)**
- **Where:**
  - R1–R6/R8 at 1280 are a single 640px card with about 320px of empty canvas on each side.
  - R7/R10 at 1280 are also a single narrow column (`request-received-1280.png`, `secure-page-1280.png`).
  - There is no step rail, no "Good to know" aside, and no `requester-wide-max` 2-column layout.
- **Spec:** S§1.2 (≥1280 step rail + card + aside), R7/R10 ≥1280 (`3fr 2fr` at `size.requester-wide-max`); CLAUDE.md "Desktop layouts should make real use of the extra space".
- **Judgement:**
  - For the wizard, the rail is a nicety (the eyebrow carries progress). The **aside is the part that matters**: it is where the phone number and "what happens after you ask" live for desktop users.
  - For R7/R10 the two-column layout is cheap and makes the status visible alongside the details.
- **Minimum to accept:**
  - R7/R10: a `@media (min-width:1280px)` grid `3fr 2fr` in `size.requester-wide-max` (template: wrap the left/right groups in two divs).
  - Wizard: the aside with phone + next steps.
  - The step rail can wait.

**M10. R9 upload tiles: Remove and Retry targets too small; rejected file tile unstyled**
- **What shows:**
  - Remove is 32×32 (`shell.css:1648`); spec is 48×48.
  - Retry is a 35×20 link-button (`.link-button` has `padding:0`, `shell.css:1754`).
  - The rejected-file tile shows "bad.txtThat file type isn't supported." as one run of text with no line break, no `file-x` icon, and no tile box (`r9-photos-tiles-390.png`).
  - The failed tile has no `circle-alert`.
  - Pickers are not full width at 390 and sit about 4px apart (spec: stacked full width, gap `space-3`).
  - Drop zone not built (known).
- **Spec:** C§24.
- **Fix:**
  - `.upload-tile__remove { width/height: var(--ham-size-target-min) }`, with the icon kept at 20px.
  - `.link-button { min-height: var(--ham-size-target-min); display:inline-flex; align-items:center }`.
  - Rejected tile markup: name (`overflow-wrap:anywhere`) on its own line + icon + reason.
  - `.upload-pickers { display:grid; gap: var(--ham-space-3) }` with full-width buttons at <1024.
- **Drop zone:** acceptable to defer; the pickers work everywhere.

**M11. R6 Edit links are 29×24 with an ambiguous name**
- **Where:** `r6_review.html:19,28,36,44`.
- **Spec:** C§23 Edit is a 48px-tall link-style button with `aria-label="Edit your need"`.
- **Fix:** `.summary-card__header a { min-height: var(--ham-size-target-min); display:inline-flex; align-items:center; padding-inline: var(--ham-space-2) }` + `aria-label`. axe also flags `heading-order` because the card titles are h3 under the h1; make them h2 styled `type-h3`.

### Leadership

**M12. Split view: rows navigate away from the split**
- **Where:** `requests_list.html:49`. At ≥1280 every row links to `/requests/<id>` (the full page), so selecting a second request leaves the split view. The pane is only reachable via `?id=`.
- **Spec:** L1 ≥1280 split view (selected row + detail pane, Enter moves focus to the detail h1, Esc returns).
- **Fix:** At ≥1280 the row href should be `?tab={{active_tab}}&id={{row.id}}`, preserving q/category/status. Keep the full-page href for <1280, either with two anchors toggled by CSS or by rewriting the href in a small script. Also:
  - The pane has no region label; add `role="region" aria-label="HAM #047 details"`.
  - The pane doesn't scroll independently; add `position: sticky; top; max-height: calc(100vh - appbar); overflow:auto`.

**M13. Status chip language inconsistent; row age is an absolute timestamp**
- **Chips:**
  - Rows use `chip--tag` (grey, `requests_list.html:59`), while the detail header uses tone chips (`chip--info` / `chip--attention`). The same status looks different on the same screen.
  - At 390 the grey chip wraps into a 2-line pill ("Awaiting / Approval", `leader-requests-list-390.png`).
- **Age:** Line 2 shows "12:31 PM EDT on Sep 28, 2026", which also wraps. The spec's age is "3 days"; phone-check rows should read "Saved Oct 5 · waiting 1 day".
- **Spec:** C§28 line 2 "status chip (`outline` variant) + age"; C§5; principle "consistent status chip language".
- **Fix:**
  - `chip chip--{{tone}} chip--outline` with the status icon, and `white-space: nowrap` on `.chip`.
  - A relative-age filter with the absolute time in `<time title>`.

**M14. L5 earlier-request panel is always expanded and dominates the detail**
- **What shows:** With 4 matches, the detail shows 4 tall cards (about 900px at 1280, more at 390) before "What's needed" (`dir-requests-split-urgent-1440.png`, `dir-detail-urgent-photos-390.png`).
- **Also:**
  - Each card repeats "Close this one as a duplicate…".
  - Line 1 lacks category/date.
  - Reason chips have no icons.
  - The alert's **View** action is missing.
- **Spec:** L5 "action **View** … expands the panel in place (a disclosure)"; card lines 1–3; one "Close this one as a duplicate…" Secondary at the panel's end.
- **Fix:** Wrap the panel in `<details class="disclosure">` with summary "View" inside the alert. Tighten the cards to padding `space-4` / gap `space-2`, with chips inline on one row. Show one close action at the end.

**M15. Administrator sees the L5 earlier-request panel**
- **Where:** `admin-detail-1280.png`.
- **Spec:** L2 "Administrator: no actions, **no L5**".
- **Note:** This is a role-visibility issue, not only visual. It is flagged for ham-privacy-security-reviewer. The template condition in `_request_detail.html:53` should also check a `can_view_matches` flag.

**M16. Filter bar is not responsive (L1)**
- **Where:**
  - At 390, three stacked labelled fields + Filter take about 290px before the first row, so only 2 rows fit on screen.
  - At 768 and 1280 the labels orphan from their selects ("Category" at a line end, the select on the next line; `dir-requests-all-768.png`, `leader-requests-list-1280.png`).
- **Spec:** L1 390 "search 1fr + Secondary md → bottom sheet"; ≥1280 "search full width, Category and Status as a second row".
- **Fix:**
  - Wrap each label+control in `.filter-bar__field { display:flex; flex-direction:column }` so they never separate. Grid: `grid-template-columns: 2fr 1fr 1fr auto` at ≥768; in the split pane, search full width then `1fr 1fr`.
  - At <768 show search + a "Filters" Secondary that opens the category/status sheet. Or, as an interim, put category/status in a `<details>` "Filters" disclosure.

**M17. Home attention cards: wrong urgent semantics and missing context**
- **Director Home:**
  - The **awareness** row "Waiting for a decision (8)" carries an **Urgent** chip (`dir-home-390.png`). A muted, non-actionable row with a danger chip sends mixed signals.
  - The phone-check card has no `phone-call` icon, no context line ("oldest waiting 1 day"), and says "7 request(s)" (`ham/requests/attention.py:89`).
- **Pastor Home:** one card, "Urgent · Waiting for a decision (8)". That labels all 8 as urgent when only some are.
- **Spec:** L7 / C§27. Pastor: urgent requests as their own cards ("Urgent · HAM #048 Plumbing or water · waiting 2 h" + Review), then one normal card "N requests are waiting for a decision". Director awareness variant: no chip, no bar, no button.
- **Fix:**
  - Split urgent items into per-request cards.
  - Drop the chip on awareness rows.
  - Pluralize properly ("1 request needs" / "7 requests need").
  - Add the icon + context line (`type-small`, `text.secondary`).

---

## Minor

1. **Emoji padlock** "🔒" (`&#x1F512;`) in `r6_review.html:97`, `r9_photos.html:34`, `r10_secure_page.html:63`. It renders as a color emoji outside the icon system. Use the sprite `lock` at `size.icon-sm` in `text.secondary`.
2. **Error summary (C§30):**
   - The title is body weight; it should be `type-label`.
   - There is no `circle-alert` icon.
   - Field errors sit **after** the textarea on R2 (`r2_need.html:38`); the spec places them between label/helper and input.
   - `.form-field--error` colours `input` only, not `textarea` (shell.css).
   - The group-level `tone.danger.icon` 2px left rule is missing on the category fieldset.
3. **R2 urgent card:**
   - When checked, the whole card turns `text.brand`. The spec keeps the label `text.primary` and turns the `siren` icon to `tone.danger.icon`.
   - The reveal area lacks the 2px `border.selected` left rule and the "Please tell us a little more." helper switch.
4. **R3:**
   - "Owner's full name" is always visible, including when "I rent it" is selected. It should appear only for "family" (C§19 reveal).
   - The tenant `inline-alert--info` does not appear under the cards after selecting "rent" (`r3-home-tenant-390.png`).
   - State is a free-text field; the spec is the read-only "Florida · Change".
   - City/ZIP never sit side by side at ≥768.
5. **R5 "I don't use email":**
   - The Email field stays visible and the contact-method group is not locked to "Phone call" (`r5-no-email-toggled-390.png`).
   - "Any time works" is not set apart (`space-3`, `calendar-check`).
6. **R6 step header** says "Last step" for R6 and R8 (`_step_header.html:89` uses `step_number == step_count`). The spec says R6 is "Step 5 of 5 · Check and send" and only R8 is "Last step".
7. **R6:**
   - The Reaching-you card omits contact method and visit times ("By email · Any time works").
   - Urgent shows as "· Urgent" text instead of an Urgent chip.
   - The phone number wraps mid-number ("(305) 555-\n0142"). Add `white-space: nowrap` on phone spans.
   - The summary cards stay single-column at ≥1280 (spec 2×2; tied to M9).
8. **R8:**
   - The wrong-code message is a separate danger alert above the field instead of a field error, and the typed value is cleared. The spec keeps it selected.
   - Focus lands on the code field on load (page scrolls at 200% text, `r8-verify-plain-390-text200.png`); the spec focuses the h1.
   - The step header has no progress bar.
   - "Didn't get it?" disclosure has no chevron.
9. **R7N:**
   - The phone is shown as `+13055550177`. Format it as `(305) 555-0177`, `type-body-lg` bold.
   - The request number is not `type-code-entry` on its own line.
   - The quiet block lacks the `phone-incoming` icon and has extra paragraph margin inside (`.quiet-block p { margin:0 }`).
   - Done is a Secondary at auto width; the spec is full width in the bar.
10. **L9 phone check:**
    - The phone is E.164 (`request_phone_check.html:13`).
    - There is **no Call button** (`tel:`, Secondary lg, full width <768). This is borderline Major for the field workflow.
    - There is no Cancel.
    - The statement copy says "she or he confirmed they", and the whole label is bold.
    - The "What to say" summary is 24px tall with the default triangle; use `.disclosure` (48px, chevron).
    - At 390 it renders as a floating card with page margins, not the full-screen sheet (`.sheet--fullscreen` not applied).
    - At ≥768 it is a standalone narrow page on an empty canvas instead of a modal over L2. Acceptable for V1 if L2 stays reachable via "Back".
11. **L10 close:**
    - The Danger button is the pale danger-tint style (`shell.css:587`). The spec's "Danger variant" for the only destructive action should be solid: `tone.danger.icon` fill with `text.on-primary`. Check contrast in the tokens contrast table.
    - The consequence box is `inline-alert--info` (blue). The spec is `bg.sunken` with an `info` icon and "This can't be undone." as `type-label`.
    - There is no Cancel.
    - The helper sits under the fieldset instead of under the legend.
12. **L11 no-email:** the "Ask for more photos" trigger stays enabled on L2 for no-email requests and leads to a dead-end page (`dir-more-photos-noemail-390.png`). The spec shows it disabled with the reason line on L2.
13. **L2 photos:**
    - Gallery items render as text "photo · uploaded" (`_request_detail.html:101`) instead of the read-only tile grid.
    - In QA the request with 2 uploaded photos showed "Photos (0) · No photos yet." because processing had not run. That should show tiles in a "processing" state, not "none".
    - The Administrator line reads "0 photos · not shown…" with no `image-off` icon.
14. **L2 layout:**
    - Section rhythm is tight: headings sit `space-2` from the previous section. The spec uses `space-8` between sections and `space-3` from heading to content.
    - There is no key-facts strip.
    - "Close request…" is a top-level button; the spec puts it in More ⋯.
    - Timestamps are verbose ("12:31 PM EDT on Sep 28, 2026"; spec "Oct 6, 9:14 AM").
    - "intake-v1" shows raw in History (spec "intake statements v1").
    - The masked-block note is 12–13px with a large empty gap before the field list.
    - The full-page detail at 1280/1440 is one stretched column. The spec's 1024–1279 two-column main/side is not built, and 1024–1279 has no table (known simplification).
15. **Category labels differ between sides:** staff labels "Accessibility", "Plumbing", "Yard & outdoor" versus requester labels "Ramps, rails or grab bars" etc., and R7/R10 show "Roof" / "Single family home" versus the R2/R3 choices "Roof or ceiling" / "House". Use one label map (S§3 uses the requester labels on rows).
16. **Selected request row** shifts its text 4px right because the accent bar is a real border (`shell.css:1288`). Use `box-shadow: inset var(--ham-size-accent-bar) 0 0 var(--ham-border-selected)`. The selected style also shows at 390 in `leader-requests-list-390.png` (the "Mobile" first-row highlight); confirm the `aria-current` is only emitted when a pane exists.
17. **Markers** lack their 16px icons (`copy`, `phone-call`) (`requests_list.html:65–66`).
18. **View tabs:** there are no edge fade masks for overflow at 390 (C§29), and the count pill is 12px.
19. **Inbox "Updates" rows** have no inline padding (the text touches the list border), no separators rhythm and no target height (`dir-inbox-390.png`). Also, the Director receives "Urgent request needs a pastor" updates; confirm the audience with ux-designer.
20. **Urgent banner** uses `triangle-alert`; the spec is `siren`. The same applies to the Urgent chip in `_request_detail.html:13` and the rows. The pastor-facing "I've seen this" variant is not in S§4 L7; log it or fold it into the spec.
21. **Raw px and fallbacks** where tokens exist:
    - `.list-detail` `minmax(360px, 420px)` (shell.css:964): use `--ham-size-split-list-min` / `--ham-size-split-list-max`.
    - `.chip__icon` 16px, `.upload-tile__remove` 32px, `.status-timeline li::before` 8px/-5px: use `--ham-size-icon-sm` etc.
    - Leftover `var(--x, 4px)` fallbacks on tokens that now exist (`--ham-size-accent-bar`, `--ham-type-chip-size`, `--ham-size-list-row-min`). S§6 asks for the fallbacks to be dropped.
    - Requester pages don't set `font-feature-settings: "ss02"` (S§0.3).
22. **R12 / R11b:**
    - R12 lacks the `circle-help` `size.icon-xl` icon.
    - The Secondary "Check on your request" sits in the sticky bar at auto width; make it full width, or out of the bar, since it's not a primary.
    - R11b "sent" has no "Didn't get it? Call …" line when the church phone is empty. R1 "Prefer to talk?", R10 "How to reach us" and "No longer need help? Call us" also lose their number when `church.phone` is unset, which leaves a dead end. In production the church profile should require a phone; otherwise show the ministry email.

## Known implementer simplifications: verdicts
| Simplification | Verdict |
|---|---|
| No desktop step rail | Acceptable for V1 (the eyebrow carries progress). |
| No "Good to know" aside | **Major (M9).** Build at least the aside on R1–R6/R9 at ≥1280 with phone + what happens next. |
| R9 drop zone not built | Acceptable; pickers work everywhere. Fix the tile/target issues (M10) instead. |
| Container queries → media queries | **Not acceptable as-is.** It is the direct cause of B1. Viewport queries can't see 200% text. At minimum the action bar needs a container query (B1). The choice grid already uses an `em`-based `auto-fill` and works once B3 removes the fieldset padding. |
| Secure page at 1280 is a narrow single column | **Major (M9).** A `3fr 2fr` grid at `requester-wide-max` is a small change. |

## Accessibility (axe-core) results
- **R9: `label` (critical).** `#camera-input` and `#file-input` have no accessible name. They are visually hidden and triggered by buttons, but still focusable. Add `tabindex="-1"` + `aria-hidden="true"`, or `aria-label`.
- **`heading-order` (moderate)** on R6, L1 empty state and L2: h1 → h3 skips. Use h2 elements (styled as needed).
- No contrast violations were reported on any captured screen.

## Checklist for ham-frontend-engineer (in priority order)
- [ ] B3: base `fieldset`/`legend` reset + legend type per S§0.3.
- [ ] B1: container-query action bar (Back relocation under 22em, `flex-wrap` fallback).
- [ ] B2: `overflow-wrap:anywhere` on every user-entered value (requester + L2).
- [ ] M1: label maps for hazards/availability (R6, L2).
- [ ] M2: secondary links/Resend/Start over placement relative to the bar; bar at the viewport bottom on short pages.
- [ ] M3/M4: choice-card icons, weight, alignment, spacing; choice-card in L9/L10; chip controls.
- [ ] M5–M8: status chip in the status card, R10 h1, success icon, `type-body` floor on requester metadata.
- [ ] M10/M11: target sizes (tile remove, Retry, Edit) and the rejected-tile layout.
- [ ] M12: split-view row links + labelled, independently scrolling pane.
- [ ] M13: row chips (tone, outline, icon, nowrap) + relative age.
- [ ] M14/M15: L5 as a disclosure, trimmed cards; hide for the Administrator.
- [ ] M16: filter bar field grouping + mobile "Filters".
- [ ] M17: Home attention cards (per-request urgent, no chip on awareness, plural, icon + context).
- [ ] M9: R7/R10 two-column at ≥1280; wizard aside.
- [ ] Minors as time allows; re-capture at 390 / 390 + 200% text / 195 / 768 / 1280.

## Artifacts
- New screenshots: `docs/ux/screenshots/step2-qa/` (requester `r*-{390,768,1280,390-text200,195-zoom200}.png`, leadership `dir-*`, `pastor-*`, `admin-*`).
- QA server: port 8040, DB `ham_qa`. The throwaway driver scripts live in the session scratchpad, not the repo.

---

## Re-check at 90f28d8
ham-ui-designer · 2026-09-28 · report only. Server on port 8041, DB `ham_qa` (migrated and re-seeded). Captures were taken at 390, 768, 1280, 1440, at 390 + 200% root text, and at 195px (200% zoom). Screenshots are in the session scratchpad, not the repo. Checks: horizontal overflow, action-bar button rects, targets under 44px, and axe-core 4.10 at 390/1280 (69 pages).

| ID | Status | Evidence |
|---|---|---|
| B1 | **Not fixed** | There is no `container-type` or `@container` anywhere in `shell.css`. `.action-bar__inner` (shell.css:1832) is still a no-wrap flex row. At 390 + 200% text, Continue's right edge is at x=433 (R3–R5) and Send request's at x=411 (R6), and the page scrolls sideways. At 195px they reach x=217 and x=205. The FIX-C commit message claims this fix, but the diff doesn't contain it. The "proof" test is also broken (see N3). |
| B2 | Fixed (one gap) | scrollWidth equals the viewport on every requester and L2 page at 390, 390 + 200% text and 195px, including a long street name, a long unbroken description and a long email. Remaining gap: at 195px the R6 statement card's text ("condominium") spills past the card border. Add `overflow-wrap: anywhere` to `.choice-card`. |
| B3 | Fixed (one gap) | No default borders remain, legends use h2/h3 type, and nothing overflows at 195px. But the category and "Type of home" grids are still **1 column at 390**. `minmax(min(100%, 11em), 1fr)` (shell.css:1687) needs 360px and the content box is 358px. Use `10.5em`. |
| M1 | Fixed | R6, R10 and L2 show labels. Raw codes remain only on pre-FIX-A seed rows (`roof`, `yard_outdoor`, `single_family_home`). See N-minor 3. |
| M2 | Partially fixed | R1 links, R2 Start over (now in the bar) and R8 Resend/Change/Didn't-get-it now sit above the bar. **New:** the wizard aside renders *after* the sticky bar at <1280 (R1–R6, R9), so content scrolls under and below the bar. On short pages (R8, R11b, R12) the bar still floats mid-screen. |
| M3 | Partially fixed | Weight 600, alignment and grid spacing are fixed. Card icons (R2–R4) are still missing, and so is the 2-column grid at 390 (see B3). |
| M4 | Fixed | Chip inputs are 20px. L9 and L10 use choice cards. |
| M5 | Fixed | The chip row (Urgent + Received) and "What happens next" are inside the card on R7 and R10. |
| M6 | Fixed | The h1 is "Your request · HAM #0NN" and the greeting uses the first name only ("Thank you, Doris."). |
| M7 | Fixed | The success hero is the SVG icon. |
| M8 | Fixed | kv labels and list items render at body size. |
| M9 | Partially fixed | R7/R10 `3fr 2fr` and the R6 2×2 are good. **The wizard aside grid is broken at ≥1280 (N2).** The aside repeats the page's own intro copy, and has no phone when `church.phone` is unset. |
| M10 | Partially fixed | Remove and Retry are ≥44px. The rejected tile still reads "bad.txtThat file type isn't supported." as one run of text with no icon (`frontend/src/upload.ts` `addRejectedTile`). Pickers are still auto-width with no gap at 390. The failed-tile text breaks awkwardly ("Couldn't / upload. Retry"). |
| M11 | Fixed | Edit links are ≥44px. There are no heading-order violations. |
| M12 | Fixed | At ≥1280 rows link to `?tab=…&id=…`. The pane is `role=region` with an aria-label, sticky, and scrolls on its own (`overflow:auto`). The pane has no `tabindex` (N4). |
| M13 | Fixed | Row chips use tone, outline and icon with relative age ("5 min", "1 day"). Polish: "Awaiting Approval" is title case while "Needs a phone check" is sentence case. |
| M14 | Fixed | L5 is a "View" disclosure inside the alert. |
| M15 | Fixed | The Administrator's L2 shows no earlier-request panel. |
| M16 | **Regressed** | 390: a "Filters" disclosure, good. **At ≥768 the filter bar is invisible** (N1). |
| M17 | Mostly fixed | Director: the awareness row has no chip, correct plurals, and a context line ("oldest waiting 1 day"). The phone-call icon is still missing. Pastor: one card per urgent request, then "2 requests are waiting". Urgent cards lack the "waiting 2 h" context line. |

### New Blocker
- **N1. Leadership filter bar hidden at ≥768.**
  - **Where:** `requests_list.html:20` wraps the filters in `<details class="filter-bar-sheet">`. `shell.css:1041–1047` tries to force them open with `.filter-bar-sheet:not([open]) .filter-bar { display:flex }`.
  - **Why it fails:** Chromium 131+ (tested: 141) hides a closed `<details>` through its `::details-content` slot (`content-visibility: hidden`), so `display` can't reveal it. Measured: `.filter-bar` gets a 76px box, but `checkVisibility()` on the search input is false at 768, 1280 and 1440. Tablet and desktop users have no search or filters at all, and a blank 76px gap sits above the list (§64 leadership triage).
  - **Fix:** render the bar outside `<details>` at ≥768. Or add `open` server-side and close it on mobile with `matchMedia('(max-width: 767px)')`. At minimum, add `@media (min-width:768px){ .filter-bar-sheet::details-content { content-visibility: visible; display: contents; } }`, but Safari <18.4 and Firefox <143 ignore that, so the markup fix is the real one.

### New Major
- **N2. Wizard aside grid at ≥1280 (R1–R6, R9).**
  - **Where:** `shell.css:2204–2223`.
  - **Why it breaks:** `grid-row: 1 / -1` on `.wizard-aside` spans only row 1, because there are no explicit rows. Row 1 (the step header) stretches to the aside's height, and `gap: space-8` also applies as a row gap between every child. The result is about 130px of dead space between the progress bar and the h1, and wide gaps between h1, "Your answers are saved." and the intro (`r3-home-tenant-1280.png`).
  - **Fix:** wrap the non-aside children in `<div class="wizard-main">` and use a 2-column grid of main + aside. Alternatively, `row-gap: 0; column-gap: var(--ham-space-8)` plus `grid-row: 1 / span 99` on the aside.
  - **Also:** at <1280, move the aside before `.action-bar` (or hide it where it duplicates the intro) so the bar stays the last thing (M2).
- **N3. The 200%-text proof test doesn't enlarge text.**
  - **Where:** `tests/e2e/test_step2_requester_screenshots.py:181` runs `add_init_script("document.documentElement.style.fontSize='200%'")`.
  - **Why it fails:** the script runs before `<html>` exists and throws, so the committed `docs/ux/screenshots/step2/request-home-390-text200.png` and `request-review-390-text200.png` show 16px text. That is why B1 looked fixed.
  - **Fix:** wrap it in `document.addEventListener('DOMContentLoaded', …)`. Assert that `getComputedStyle(document.documentElement).fontSize === '32px'` and that `scrollWidth <= innerWidth`.
- **N4. axe `scrollable-region-focusable` (serious) on `.split-detail`.**
  - **Where:** the Administrator's `/requests` at 1280, whose pane has no focusable content. `requests_list.html:102`.
  - **Fix:** add `tabindex="0"` to the pane. It already has `role="region"` and a label.
- **N5. Pastor urgent banner is cramped at 390.**
  - **Where:** `.urgent-banner__text { flex:1; min-width: var(--ham-size-target-min) }` (shell.css:197–200).
  - **What happens:** the text can shrink to about 80px, so "Urgent request needs a pastor · HAM #027 Roof or ceiling" wraps to 7 lines next to Open and "I've seen this". The banner is sticky and about 190px tall, roughly 22% of the viewport on every page.
  - **Fix:** `flex: 1 1 16em; min-width: 0`. The actions then wrap to their own row; make them a `space-2` row of Secondary sm buttons.

### New minors
1. Pastor Home with many urgent requests shows a column of solid-primary "Open" buttons (12 in QA data), which breaks the "one primary" rule. Cap it at 3 urgent cards plus "N more urgent → Requests", or use Secondary buttons after the first.
2. L2 at 390: "Photos (0) · Videos (0)" sits flush under the hazard row (missing `space-8` section gap). The count reads 0 while 2 items are still processing (Minor 13 is still open).
3. The label maps return the raw code for unknown values (`roof`, `yard_outdoor`, `single_family_home` on older rows). Fall back to a humanized label, never the code.
4. The L9 "What to say" summary shows a stray "⌟" glyph instead of the chevron.
5. R6 error summary copy: "Please read and tick both statements. · Fix in Please confirm" reads awkwardly. Use "Tick both statements in Please confirm."

axe: 0 violations on 37 requester pages and 31 of 32 leadership pages; the only violation is N4.

---

## Final re-check at f1d4fb9
ham-ui-designer · 2026-09-28 · report only.
- **Setup:** server on port 8042 with `HAM_BASE_URL=http://127.0.0.1:8042`. Without it, local presigned PUTs go to :8000 and every upload shows "Couldn't upload"; that's a QA environment issue, not an app bug. DB `ham_qa` was recreated (FIX-F2's `req_urgency_reason_iff_urgent` constraint rejected old QA rows), migrated and seeded.
- **Captures:** 390, 768, 1280, 1440, 390 + 200% text (root measured at 32px) and 195px. Chromium 141, axe-core 4.10. Screenshots are in the session scratchpad (`step2-qa-final/`).
- **Tests:** `tests/e2e/test_fix_f1_{large_text,requests_filter,wizard_layout}.py` pass (4 passed).

| ID | Status | Evidence |
|---|---|---|
| B1 | **Fixed** | `container-type` on `.action-bar` plus `@container (max-width:22em)` (shell.css:1851–1878). At 390 + 200% text, Back and Continue stack at L32–R358. At 195px they sit at L16–R179. scrollWidth equals the viewport on every requester page in every mode. The residual bar height is logged as N6. |
| B2 | Fixed | No overflow anywhere. `overflow-wrap:anywhere` on `.choice-card` causes N7. |
| B3 | Fixed | The choice grid is 2 columns at 390 (10.5em). Reopened as N7 because of mid-word breaks. |
| N1 | **Fixed** | `<details open>` at ≥768. q, category, status and Filter all return `checkVisibility()` true at 768, 1280 and 1440. At 390 the bar collapses behind "Filters". |
| N2 | Fixed | At 1280 the h1 sits directly under the progress bar, with the aside in the right column (`r3-home-tenant-1280`). |
| N3 | Fixed | The init script runs on DOMContentLoaded. The test asserts `fontSize === '32px'` and no horizontal scroll. |
| N4 | Fixed | `.split-detail` has `tabindex="0"`. axe reports 0 violations on the Administrator's /requests. |
| N5 | Fixed | The Pastor banner is 129px at 390 (was about 190). Text wraps in 2 lines and the actions sit on their own row. Home shows 3 urgent cards plus "6 more urgent", and only the first Open is Primary. |
| M2 | **Partially fixed** | At <1280, `.wizard-aside` still renders after `.action-bar` on R1–R6 and R9 (for example `afterBar: ASIDE.wizard-aside` on r9 at 390, 768 and 390 + 200% text). The aside then scrolls up under the bar, and "Good to know" repeats the intro line on R3. On short pages (R11b at top 308, R12 at 298 at 390) the bar still sits mid-screen. |
| M3 | Partially fixed | R3 and R4 cards have icons. R2 category cards have none. The 2-column grid at 390 breaks words (N7). |
| M10 | Fixed | The rejected tile shows a file-x icon, the file name in bold and the reason on its own line. Pickers are full width. Uploaded tiles read "Uploaded". Polish: the "×" remove button covers the photo's centre-top. |
| M16 | Fixed | The filter bar is labelled and grouped at ≥768 and becomes a "Filters" disclosure at 390. |
| M17 | Fixed | The Director's awareness card has `icon-phone-call` and "oldest waiting 1 day". Pastor urgent cards show "waiting under 1 h". |
| B2/B3 gaps | Fixed, but see N7 | |

### New Major
- **N6. The stacked sticky bar takes up to a third of the viewport at 200% zoom and text.** It is 141px of 422 at 195px (33%) and 177px of 844 at 390 + 200% text (21%), and it covers the fields while typing.
  - **Where:** shell.css:1878 (`@container (max-width:22em)`) stacks Back above the primary.
  - **Fix (per the B1 spec, "Back relocation under 22em"):** under 22em, keep only the primary in the sticky bar. Render Back as a tertiary text link in the flow, above the bar (duplicate the markup with `.action-bar__back--inline`, and toggle it with the same container query on a wrapping container). The bar then drops to 101px / 77px.
- **N7. Mid-word breaks in icon choice cards at default text size.**
  - **Examples:** at 390, "Townh/ouse", "Apartm/ent or condo" and "Mobile or manufa/ctured home" (`r3-home-tenant-390`). At 1280, "manufactur/ed home".
  - **Cause:** `overflow-wrap:anywhere` (shell.css:1734) collapses the label's min-content. In a 10.5em column (shell.css:1705), the radio (24px), icon (24px), gaps and padding leave only about 70px of text width.
  - **Fix:**
    - (a) shell.css:1734: `overflow-wrap: break-word; hyphens: auto;`. `html` already needs `lang="en"`.
    - (b) Icon grids get a wider minimum: `.choice-grid:has(.choice-card__icon){grid-template-columns:repeat(auto-fill,minmax(min(100%,15em),1fr))}`. That gives 1 column at 390 and 2 columns in the 640px main column at 1280. Icon-less grids (R2 categories) keep 10.5em and 2 columns at 390, which already reads well.
    - (c) Alternative to (b): a compact card variant with the icon stacked above the label.

### Minors / polish
1. R7N: the phone number wraps as "(305) 555-/0177". Put `white-space:nowrap` on the phone span. Done is still auto width in the bar (spec: full width). The quiet block has extra top padding.
2. L9: the "What to say" summary still shows a stray glyph after the label instead of the `.disclosure` chevron. The script block has about 24px of extra top padding.
3. Pastor Home: "waiting under 1 h" breaks between "1" and "h". Use `&nbsp;` or `nowrap` on the age.
4. L2 at 390: "Photos (2) · Videos (0)" and "The home" still sit about `space-2` from the section above (spec `space-8`). Timestamps remain verbose.
5. The 1280 split pane cuts content mid-heading with no fade or scroll affordance. Consider a bottom fade mask on `.split-detail` when it overflows.

**axe:** 0 violations across 58 requester runs (390 and 1280, over two passes) and 32 leadership runs (390 and 1280).
