# Step 3 (Approvals): UI visual QA

ham-ui-designer · 2026-09-29 · branch `feature/step-3-approvals`. The code under test is `7f43fb4`; later commits touch only the review docs. This is a report only: no app code, templates, CSS or tests were changed.

**Specs:** `design-system/screens/approvals.md` (**A§n**), `design-system/components.md` C§26a and C§33–C§40 (**C§n**), CLAUDE.md "Design", and the lessons from `docs/ux/reviews/step2-ui-visual-qa.md` (**S2 …**).
**Dark mode:** out of scope for V1 (Q-016), so it wasn't captured.

## Method
- **Server:** port 8044, `HAM_BASE_URL=http://127.0.0.1:8044`.
- **Database:** `ham_qa3`, recreated, migrated and seeded with `seed_dev` + `seed_dev_requests`.
- **Test data:** a throwaway script created each step-3 state through the real services (`approve_request`, `reject_request`, `request_reconsideration`, `decide_reconsideration`, `ask_question`, `verify_by_phone`, `finalize_rejection`, `run_held_decision_effects`):
  - approved (#007)
  - declined, window open (#008)
  - Reconsideration Pending (#009)
  - inside the undo window, approved (#010) and declined (#011)
  - open question (#012)
  - urgent awaiting (#013)
  - Board-approved urgent, not yet certified (#014)
  - no-email approved, "call to share" (#015)
  - no-email with an open question (#016)
  - final after reconsideration (#017)
  - approved after reconsideration (#018)
  - reconsideration window passed (#019)
  - urgent approved and certified (#020)
- **Second pastor:** "David Kim" was added to view the take-over state.
- **Past-window decisions:** these were made under a `FixedClock` set in the past, then their held effects were released.
- **Urgent banners:** the outbox was drained once, part-way through the pass, so the urgent banners appear. See "Coverage caveats".
- **Captures:**
  - 390×844, 768×1024, 1280×800 and 1440×900.
  - 390 + 200% root text (root measured at 32px).
  - 195×422, which equals 200% zoom.
  - 58 screens × 6 modes = 348 page captures, plus the 390 recaptures with a live banner.
  - Screenshots are in the session scratchpad (`…/scratchpad/step3-qa/`), not in the repo.
- **Checks on every capture:**
  - `scrollWidth` against `innerWidth`.
  - Every visible sticky or fixed element (top and height).
  - Action-bar height as a % of the viewport.
  - `elementFromPoint` at each Primary's centre and at every control in `main`.
  - Per-word Range `getClientRects`, to find mid-word breaks.
  - Controls under 44px.
  - axe-core 4.10.2 (WCAG 2.0/2.1/2.2 A+AA + best practice) at 390 and 1280.
- **Sticky-card test:** the Decision card was scrolled at 1024, 1280 and 1440, on the full page and in the split pane.

**Ignore in all "mid-word break" counts:** the deliberately unbroken 60-character URL in the test description. It is supposed to wrap anywhere.

## Summary
| Severity | Count |
|---|---|
| Blocker | 4 |
| Major | 14 |
| Minor | 22 |

**What works:**
- Content, copy and state coverage are largely there.
- The requester pages are calm and readable at 390 and 1280. R15/R17/R18 use the 3fr/2fr layout at 1280.
- The Decision card at 390 is the first block after the header.
- R16 applies the step-2 "Not now leaves the bar under 22em" pattern correctly.
- axe reports **0 violations** on all 116 runs (58 screens at 390 and 1280).

**What fails:**
- **The large-text contract (A§0.3) fails on the leadership side.** Four causes combine:
  - The urgent banner has no large-text behaviour.
  - Sheets don't apply the "primary only under 22em" rule.
  - An inherited `overflow-wrap:anywhere` breaks buttons letter by letter.
  - The Decision card is sticky even though the layout is one column.
- **Several step-3 status signals are wrong or missing in the list.**

---

## Blockers

### B1. The urgent banner overflows sideways and stays sticky at large text, on every leadership page and sheet
- **Where:** every leadership screen for a pastor, Director or AD while an urgent banner is live. Measured on all 46 leadership captures that had a banner:
  - 390 + 200% text: `scrollWidth` 499 of 390.
  - 195: `scrollWidth` 248 of 195.
  - The "I've seen this" button is clipped at the right edge (`a1-urgent-390t200`).
- **Height:** the banner stays sticky, at 325px of 844 (39%) at 200% text and 218px of 422 (52%) at 195.
- **Why it's a Blocker:**
  - On sheets it stacks with the action bar (B2). At 195 the app bar, banner and bar together (56 + 218 + 159px) are taller than the 422px viewport, so no sheet content can be reached.
  - Playwright couldn't tick a decline reason on A3 or A9 at 195: the element was always covered.
  - Even at 390 with normal text, sheets carry 56 + 129 + 133 = 318px of sticky chrome (38%).
- **Code:**
  - `shell.css:176–210`: `.urgent-banner` is always `position: sticky`, and `.urgent-banner__actions { flex: none }` can't wrap.
  - `_urgent_banner.html:7`: `role="alert"`; the spec is a region.
  - `base.html:24`: the banner is included on the full-screen sheets as well.
- **Spec:** C§40 ("sticky ≥22em … under 22em the banner is `position: static`"; `role="region" aria-label="Urgent"`); A§0.3 item 7; C§39 (full-screen sheets cover the app chrome).
- **Fix:**
  1. Wrap the banner in `.urgent-banner-slot { container-type: inline-size }`.
  2. Make `.urgent-banner` static by default. Add `@container (min-width: 22em) { .urgent-banner { position: sticky; top: var(--ham-size-appbar-height) } }`.
  3. Set `.urgent-banner__actions { flex: 1 1 100%; flex-wrap: wrap; min-width: 0 }` and `.urgent-banner__actions .btn { flex: 1 1 auto }`.
  4. On sheet templates (the ones that already empty `{% block bottom_nav %}`), render the banner static, or not at all: the decision is already in progress.
  5. Use the `siren` icon (S2 minor 20 is still open) and `role="region" aria-label="Urgent"`.

### B2. Sheet action bars keep Cancel and grow to 26–49% of the viewport under 22em; short sheets don't pin the bar
- **Where:** every sheet (A2, A2b, A2u, A2n, A2c, A3, U1, A4, A5, A6, A9, A11, A12).
- **Bar height (both buttons stacked):**

  | Mode | Most sheets | A9 take-over |
  |---|---|---|
  | 390, normal text | 133px (16%) | — |
  | 390 + 200% text | 219–267px (26–32%) | 363px (43%) approve, 411px (49%) decline |
  | 195 | 135–159px (32–38%) | 207px (49%) |

  - A9 decline at 200% text wraps its primary to six lines (`a9-recon-decline-takeover-390t200`).
- **Even at 390 with normal text** the bar is stacked. The sheet is an inset card (page gutter + `.sheet` padding `space-6`), so the bar's container is about 310px, under 22em.
- **Short sheets:** U1, A2n, A12 and A9-decider leave the bar floating mid-screen at 390 (U1 bar top 520 of 844, with empty canvas below).
- **Code:**
  - `shell.css:1967–1987`: under 22em only `.action-bar__back` is hidden. Sheets put Cancel in the bar as a plain `.btn--ghost` (for example `request_reject.html:80`, `request_decision_undo.html:33`), so both buttons stack.
  - `shell.css:2034–2055`: the short-page pinning is scoped to `.public-card` only.
  - `shell.css:1201–1208`: `.sheet` keeps its padding at <768.
- **Spec:** C§39 ("Under 22em the consequence line and Cancel move into the flow … bar holds only the primary (≤ 18%) … body `flex: 1` so the bar is pinned"); A§0.3 items 2, 4 and 5; S2 N6.
- **Fix:**
  1. Add `action-bar__back` to every sheet's Cancel / Keep my decision. Render the in-flow twin (`<p class="wizard-back-link">`, already styled at `shell.css:2016–2027`) directly above `.action-bar`.
  2. Under `@media (max-width: 767px)`: set `.sheet--fullscreen { display: flex; flex-direction: column; padding-inline: var(--ham-space-4); box-shadow: none }` and `.sheet--fullscreen > form { flex: 1; display: flex; flex-direction: column }`, and give `.sheet--fullscreen .action-bar` `margin-top: auto`.
  3. Shorten the A9 primary to "Take over and decline" / "Decline (final)". The HAM # is already in the accessible name and the header (A§2.10).

### B3. Buttons inside the Decision card break mid-word ("Und/o deci/sion", then one letter per line at 195)
- **Where:** A1 pending state (decider), at 390 + 200% text (`a1-pending-decider-390t200`: "Und / o / deci / sion") and at 195 ("U / nd / o / de / ci / si / on / …").
- **Scope:** the same inheritance hits every `.btn` wrapped in a `<p>` inside `.request-detail`. That includes Certify as urgent…, Tell by phone… and Record request to reconsider (phone)….
- **Cause:**
  - `shell.css:606–614` sets `.request-detail p { overflow-wrap: anywhere }`. The property is inherited, so the `.btn` inside `<p>` (`_decision_card.html:121`, `:152`, `:162`) collapses its min-content.
  - The inline-alert's icon column and padding then leave about 60px (at 195) for the button.
- **Spec:** A§0.3 item 3 (no mid-word breaks); C§37 (Undo decision… is a Secondary md).
- **Fix:**
  - `.btn { overflow-wrap: normal; word-break: normal }` (shell.css:653). Buttons already wrap between words with `text-wrap: balance`.
  - Take the button out of the `<p>`, as a direct child of the alert body.
  - Under `@container (max-width: 22em)` on `.decision-card`, hide `.inline-alert__icon` in the pending notice so the text gets the full width.

### B4. At ≥1024 the sticky Decision card covers the request on the one-column full page
- **Where:** `/requests/<id>` at 1024, 1280 and 1440 (for example Home → Review, the list at <1280, or the "Back to HAM #…" link).
- **What happens:**
  - The detail is one column (`parentGrid: none`), but the card is `position: sticky`. When scrolled, a card 952–1112px wide and 311–323px tall pins under the app bar (and under the sticky urgent banner).
  - What's needed, Photos, Visits, Requester & contact and History all scroll underneath it.
  - At 1280×800: app bar 56 + banner 75 + card 311 = 442px, so 55% of the viewport is chrome (`sticky-full-urgent-1280.png`).
- **In the split pane (1280/1440):** the same sticky card overlaps the "Earlier request found" alert above it. The alert's "View ›" chevron shows through the Rejected chip (`sticky-split-declined-1440.png`).
- **Code:** `shell.css:2665–2673` gates sticky on `@media (min-width: 1024px)`. The spec gates it on the two-column container query.
- **Spec:** C§33 ("Not sticky … when the detail is one column (container query), so it never covers content"); A§1.5 and §0.2.
- **Fix:**
  - Minimum: remove the sticky rule, because no two-column layout exists yet.
  - Proper fix (see M1): `.request-detail { container: detail / inline-size }`, then `@container detail (min-width: 42em) { .request-detail__grid { display: grid; grid-template-columns: minmax(0,1fr) var(--ham-size-aside); column-gap: var(--ham-space-6) } .decision-card { position: sticky; top: var(--ham-space-6) } }`, and also `@media (max-height: 479px) { .decision-card { position: static } }`.

---

## Major

**M1. No two-column detail at ≥1024. The desktop A1 is a stretched mobile column**
- **What shows:**
  - At 1280 and 1440 the full-page detail is one column. The Decision card is 952–1112px wide, and its Secondary buttons span the full width (a 1070px "Ask a question", `a1-approved-1440.png`).
  - In the split pane the detail is also one column.
  - The Requests view at 1280 keeps the full sidebar, not the rail (P§2 v1.4).
- **Spec:** A§1.5 (main + `size.aside` side column with the sticky Decision card, the facts in the side column, the pair stacked at `control-md`); CLAUDE.md "Desktop layouts should make real use of the extra space".
- **Fix:** as in B4. Also:
  - In the side column, set `.decision-card__actions .btn { width: 100% }`. At one column ≥768, cap the card actions at `size.form-max`.
  - Wrap the main sections and the side facts in two elements in `_request_detail.html`.
  - Selector for the Requests rail: `.app-shell:has(.list-detail)` at 1280–1535.

**M2. Take-over can't be reached from A1: another pastor sees no decide buttons on a Reconsideration Pending request**
- **Where:** #009 viewed by David (pastor). Samuel and Marcus see the same thing.
- **What shows:** the card says "Goes to Ruth A., who declined it. If they're unavailable, another pastor can take it over." It offers no action. Only the original decider (Ruth) gets Approve… / Decline….
- **Code:**
  - The A9 sheet itself supports take-over (`?take_over=1` works; `views_requests.py:1273`). But `views_requests.py:344–367` sets `can_decide` from `may_decide_reconsideration(...)`, which refuses a non-original pastor while the original is an active pastor.
  - As a result the `needs_take_over` branch in `_decision_card.html:75–81` never renders, and `:88` renders instead.
- **Spec:** A§1.3 ("Reconsideration Pending, another pastor: … The same pair shows; accessible names 'Take over and approve HAM #046'"); Q-157.
- **Fix (backend + template):**
  - For a pastoral-route reconsideration, when the viewer is a pastor and not the original decider, set `can_decide=True, needs_take_over=True`. The sheet already enforces the tick.
  - The visible labels should stay **Approve…** / **Decline…**, with `aria-label="Take over and approve HAM #009"`.

**M3. Status chips: wrong tone and icon, requester labels leak onto staff rows, and "Final" is missing**
- **Rejected tone and icon:** Rejected renders as a **red danger chip with `circle-alert`** everywhere (rows, A1 header, Decision card). The spec is neutral `circle-x` and "never red" (C§26a, A§0.4).
  - Code: `presentation.py:90` (`"danger"`) and `:103` (`"circle-alert"`).
- **Approved:** `success` + `circle-check`; the spec is info + `badge-check`.
- **Reconsideration pending:** `hourglass`; the spec is `rotate-ccw`.
  - Code: `presentation.py:88, 101, 104`.
- **Requester labels on staff rows:** every decided or reconsideration row adds a second grey chip carrying the **requester** label ("Approved", "Not approved", "Taking another look"). Code: `requests_list.html:76` (`row.decision_chip`). Staff screens must use the §52 staff chips only (C§26a last paragraph).
- **"Final" missing on rows:** the Rejected · Final reason line doesn't appear on rows (#017 shows only "Rejected").
- **Fix:**
  - Tones and icons: Approved `info` `badge-check`; Rejected `neutral` `circle-x`; Reconsideration pending `attention` `rotate-ccw`. Take them from `tokens.json › status.project`.
  - Delete the `decision_chip` span.
  - Add a `type-small` "· Final" reason line after the chip when `is_final`.

**M4. The step-3 row markers are missing, and every tab shows the submission age**
- **What shows:**
  - Rows show only "Earlier request".
  - None of the A§0.4 markers render: Undo until / Decision pending, Question open · 2 days, New answer, **Yours** / Goes to Pastor Ruth A. / Goes to the Board, Can ask until Oct 12, After reconsideration, Call to share a decision.
  - Line 2 on every tab is `row.submitted_at|relative_age`, so the Decided tab shows "3 h" instead of "Pastor Ruth A. · Sep 28", and Reconsideration shows no "asked Oct 10".
  - The Decided tab includes Cancelled requests (#005, #006) and has no All / Approved / Rejected / Final filter chips.
- **Code:** `requests_list.html:71–83`.
- **Spec:** A§3.2 table; C§28; C§37 (row markers).
- **Fix:**
  - Add per-tab line-2 variants and a marker loop: icon 16px + `type-small`, `tone.attention.fg` for Yours / New answer / Call to share.
  - Restrict Decided to Approved/Rejected (Cancelled belongs to All).
  - Add the filter-chip row.

**M5. The "Waiting on requester" tab lists nearly every request (count 19–20 instead of 2)**
- **Where:** `list-waiting-ruth-1280.png`.
- **Cause:** `queries_questions.py:57–58`. `filter(questions__answered_at__isnull=True, questions__closed_at__isnull=True)` is a LEFT JOIN, so requests with **no** questions match too.
- **Why it's Major:** the tab count and list are wrong for every approver.
- **Fix (backend):** add `questions__isnull=False`, or use `Exists(RequestQuestion.objects.filter(request=OuterRef('pk'), answered_at__isnull=True, closed_at__isnull=True))`. Add a test with a question-less request. Rows then need "asked by Andre W. · 2 days" (M4).

**M6. The decline preview isn't WYSIWYG, and the decline sheet has no consequence line**
- **Wording mismatch:** the A3 preview ends "…you can ask us to reconsider, once, within the next 14 days." (`request_reject.html:66`). The requester actually reads "You can ask until **Mon, Oct 12**" (R15, `req-declined-390`). A decider can't check what the requester will see.
- **No consequence line:** A3 has no consequence line at all ("The requester's email goes out at 3:51 PM, after your 30 minutes to undo. They can ask us to reconsider once, until Tue, Oct 20."). Only the call tip exists (`:69`).
- **Other gaps:** the preview isn't a disclosure at <768, and the empty state "Your message will appear here." is missing.
- **Spec:** C§36 ("Always WYSIWYG with R15"), A§2.5.
- **Fix:**
  - Pass the would-be `reconsideration_deadline` (from the rules module) into the template and render the R15 sentence exactly.
  - Add the consequence `quiet-block` with the absolute undo-end time.

**M7. A9 decline has no prefill, no preview and no final-wording check**
- **Where:** `request_reconsideration_decide.html:58–77`.
- **What shows:** the reason cards leave "What we'll tell the requester" empty (no prefill, no `decline-prefills` script), and there's no message preview.
- **Why it's Major:** this is the requester's **final** message.
- **Spec:** A§2.10 decline mode ("A3's reason cards + What we'll tell the requester + preview in the final wording (R18b)").
- **Fix:** reuse A3's field, prefill script and `.message-preview` include, with the R18b sentences.

**M8. Changing the decline reason silently overwrites an edited message**
- **Where:** `request_reject.html:95–104`. On every reason change the message is replaced, with no Replace / Keep choice.
- **Why it's Major:** a pastor who wrote a careful message and then corrects the reason loses the text without warning.
- **Spec:** A§2.5 (inline "Replace your message with the suggested one?" [Replace] [Keep mine] row, `bg.sunken`).
- **Fix:** track `dirty` on `input`. If dirty, show the inline row instead of replacing.

**M9. Hard-coded people's names and rule values in sheet copy**
- **Names:** "Marcus and Andre are alerted / are told" is written literally in `request_approve.html:65,69` and `request_certify_urgency.html:20`. These are seed persona names, and a real church would read the wrong people.
- **Rule values:** "30 minutes" and "14 days" are literals in:
  - `request_reject.html:66,69`
  - `request_approve.html:65,69`
  - `request_decision_undo.html:15`
- **"Elder" prefix:** "Elder" is hard-coded before the Board rep's name (`_decision_card.html:84`).
- **Spec:** CLAUDE.md (fixed rules live in ONE rules module; never scattered literals); A§8 ("No hard-coded … 30-minute / 14-day values"); A§2.1 consequence copy uses runtime times.
- **Fix:**
  - Pass `dir_ad_names` (current Director/AD short names, or "the Director and Assistant Director" as the fallback).
  - Pass `undo_until` and `reconsider_until` from the rules module.
  - Drop "Elder".

**M10. Mid-word breaks at 200% text and 195 in sheets: A6 categories, statement cards, the A4 question quote**
- **A6:** "Plumbin/g", "Electric/al", "window/s", "Somethi/ng", "(Current/)" at 390 + 200% text, and more at 195 (`a6-category-390t200`).
- **Statement cards:** A9 "Ruth / isn't / available", and A4/A5/A11/A12 "I spoke with the requester by phone" break at 200% text and 195.
- **A4 open-question quote:** "roughly", "ceiling".
- **Cause:**
  - The sheet's double inset (B2) plus the card padding.
  - `overflow-wrap: anywhere` on `.choice-card` (shell.css ~1786).
  - The A6 icon isn't dropped. The 22em container query applies to `.choice-grid`, but the sheet grid is narrower than the rule assumes.
- **Spec:** A§0.3 item 3; A§2.9 (icons dropped under 22em; labels `overflow-wrap: break-word`); S2 NM1.
- **Fix:**
  - B2's sheet padding fix, plus `.choice-card--statement, .choice-card > span { overflow-wrap: break-word }`.
  - Under `@container (max-width: 22em)` on the grid: `.choice-card { padding-inline: var(--ham-space-3); gap: var(--ham-space-2) }`.
  - Confirm the A6 icons carry `.choice-card__icon` so the existing drop rule applies.

**M11. Requester chips overflow at 200% text and 195 (R17, and "Being reviewed" on R10/R13)**
- **Measurements:**
  - `req-recon-390t200`: `scrollWidth` 429 of 390. "Taking another look" runs out of its pill.
  - At 195: R17 229, and R13 / urgent / undo-window pages 197.
  - Chip icons also drop below the text line at 200% text, on staff and requester chips alike (`a1-urgent-390t200`).
- **Cause:** `shell.css:928–946`. `.chip` has a fixed `height: var(--ham-size-chip)` plus `white-space: nowrap`, and `.chip__icon` is a fixed 16px box.
- **Spec:** A§0.3 item 1; C§26.
- **Fix:**
  - `.chip { height: auto; min-height: var(--ham-size-chip); max-width: 100% }`.
  - `.chip__icon { width: 1em; height: 1em }`, with the svg at 100%.
  - On `.public-shell` under 22em, allow `white-space: normal` for `.chip--lg`.

**M12. Home, Inbox and banner content doesn't match A§4**
- **Pastor Home (`home-ruth-390`):**
  - Rows read "Certify urgent · approved (1)" and "Reconsideration for you (1)", with **Open** as the action. The spec is per-request cards: "Urgent · HAM #014 · Approved by the Board · not yet certified" [Review], and "Asked to reconsider · HAM #009 · you declined it Sep 28" [Review].
  - There is no Answer received card.
- **Director Home:**
  - "Call to share a decision (1)" has no HAM #, category, `phone-outgoing` icon or date.
  - The awareness rows for Reconsideration, Approved and Waiting on requester are missing.
- **Director Inbox:** receives "Urgent request needs a pastor · HAM #020" updates. That's the wrong audience (S2 minor 19 is still open).
- **Banner:**
  - Shows only the newest item, with no "2 urgent requests need a pastor" count.
  - The `--approved` variant lacks "Arrange the site visit." and uses "I've seen this" instead of **Got it**.
- **Spec:** A§4.1–4.4, C§27, C§40.
- **Fix:** per-request card builders in `ham/requests/attention.py`; the banner count; the variant copy and actions.

**M13. "Why it's urgent" is merged into What's needed as grey secondary text**
- **Where:** A1 on #013 and #014 (all widths): "Urgent: Water is coming in…" in `text.secondary` under the description.
- **Why it's Major:** it's the basis a pastor certifies on, and here it has less visual weight than the description.
- **Spec:** A§1.1 item 5 (its own block: h2 with `siren`, reason `type-label`, the requester's words in a §35 quote, danger accent bar); step-2 N-M1.
- **Fix:** give it its own `<section>` in `_request_detail.html`, directly under the Decision card.

**M14. Heading copy bug on A9 for the original decider**
- **Where:** the visible h1 reads "**approve** HAM #009?" in lower case, and "Take over and **Approve** HAM #009" has a capital A mid-phrase.
- **Code:** `request_reconsideration_decide.html:11–14` and `:83–85`.
- **Fix:** separate strings: "Approve HAM #009 after reconsideration?" / "Take over and approve HAM #009?", and primaries **Approve HAM #009** / **Take over and approve**.

---

## Minor
1. **Pending notice (C§37):**
   - It uses `hourglass`; the spec is `timer`.
   - `role="status"` on first render announces on every page load (`_decision_card.html:116`). Drop it; announce only on window end.
   - The "other approver" variant has no title line (`:126–129`).
2. **Decision pair (C§34):**
   - No `check` / `x` leading icons.
   - No accessible names with the HAM # (A§7).
   - At 390 the pair is always stacked, because the card's container is under 22em. That's acceptable without the bar.
3. **Decision card extras:**
   - "Not urgent: leave for normal review…", "Change category…" and "Record request to reconsider (phone)…" are full-width Secondary buttons, so the urgent card at 390 shows five bordered buttons.
   - The spec puts these in **More ▾** (A§1.1, §1.2).
   - The "Ask for more photos" button sits between the header meta and the Decision card at <1024; the spec has it in the header row at ≥1024 and in More at <1024.
4. **Spacing:**
   - The Decision card touches the L5 alert (0–8px) and "What's needed" (about 16px). Sections are `space-8` apart (A§1.1).
   - Add `.decision-card { margin-block-end: var(--ham-space-8) }`.
5. **Reconsideration card for the decider:** it lacks the state line "The requester asked us to reconsider on …. It comes back to you." The caption uses the verbose timestamp.
6. **Timestamps** are verbose everywhere ("10:53 PM EDT on Sep 28, 2026"). The Board line mixes "Sept. 28, 2026" and "Sep 28, 2026". The spec is "Oct 6, 3:15 PM" (S2 minor 14, still open).
7. **A2u:**
   - The "Why approved (leaders only)" field is missing (A§2.2).
   - The reason label and the requester's words are merged in one quote.
   - The "Approve, but not as urgent" link isn't on a `size.target-min` row.
8. **A2 / A2b:**
   - No one-line summary ("Roof or ceiling · waiting 5 days").
   - Hard `maxlength` on the note and messages; A§0.6 asks for soft counters, and no counters exist.
   - The Board-on-urgent `inline-alert--info` needs a visual check (A§2.1).
9. **Sheet headers** show only "Decline HAM #012". Add the "HAM #012 · Plumbing or water" request line (C§39), because at ≥768 the request isn't visible behind the sheet.
10. **A9:**
    - The requester's note caption is a loose `<p>` outside the figure (`request_reconsideration_decide.html:38–40`). Use a `figcaption`.
    - The take-over block has no `border.subtle` divider.
    - The name reads "Ruth A."; the spec is "Pastor Ruth Alvarez".
11. **A11 script quote:** a blank first line and a hard break before "visit". `white-space: pre-line` on `blockquote` preserves the template's indentation (`request_decision_phoned.html:15–18`). Put the text on one line.
12. **A11 / A4 no-email / A5** reveal the name and phone on open, without the C§25 masked block and **Show contact details**. The reveal is logged (`views_requests.py:1409, 1474`), so this is a spec deviation, not a leak. Flagged for ham-privacy-security-reviewer to confirm the auto-reveal-on-GET is acceptable.
13. **Unscoped CSS:** the S3.7 block redefines `.quote-block figcaption` and `.quote-block blockquote` globally (`shell.css:2751–2762`), overriding the app's `type-small` caption. Scope both under `.public-shell`.
14. **Requester status card** always uses the info accent (`shell.css:2239`). The spec is success for R14, neutral for R15/R18 and info for R13/R17 (A§5.0). Add `.status-card--{{ tone }}`.
15. **R13:** two Primaries on the page (Send answer + Add photos). Make Add photos Secondary while a question card is open.
16. **R18b / R18c:**
    - "Photo uploads are closed for now. If HAM needs more, we'll ask." and "No longer need help? Call us and we'll close your request." appear on a request that is already final. Hide them when closed.
    - The quote uses curly-quote glyphs around a bar block (C§35 don't).
    - The "Photo uploads are closed" alert touches the button above it on R15.
17. **R16:**
    - The bar is 195px (23%) at 390 + 200% text and 99px (23%) at 195; the target is ≤18%. The primary "Send my request to reconsider" wraps to three lines. Consider "Send my request".
    - The focused h1 shows a green focus box on load. Use `:focus-visible` styling, or `outline: none` on `[tabindex="-1"]` headings.
18. **Tabs:**
    - At 390 the fourth tab is cut ("Waiting on reque") with no fade mask (S2 minor 18, still open).
    - At 1280 the Director's six tabs overflow the row (`view-tabs__item` right edge 1313) with no affordance.
19. **Row line 1** splits "HAM #020" and "· Plumbing or water" into two flex items, so the category wraps as a separate block ("· Plumbing or / water"). Keep them in one text node.
20. **Chip icons in the Urgent chip** render the `siren` glyph at 16px regardless of text size (see M11).
21. **L5 duplicate-panel titles** break "Electrical" / "Plumbing" at 195. These are step-2 components.
22. **The banner clearing logic may clear Director/AD must-acknowledge banners.** `_clear_urgent_banner` (`ham/requests/notifications.py:248–262`) acknowledges **every** `requires_ack` notice for the request, including the Director/AD `--approved` notice, which Q-161 says must be acknowledged. In this pass (outbox drained in one batch) pastors also kept a stale "needs a pastor · HAM #020" after #020 was certified. That may be a delivery-order artifact. Flagged to ham-backend-engineer to verify with ordered delivery: filter the clear by `kind` / recipients.

---

## Known simplifications: verdicts
| Simplification | Verdict |
|---|---|
| **Sheets are full-screen at every width; no right side sheet at ≥1024** | **Acceptable for V1, with conditions.** At <768 it is the correct frame. At ≥768 it is really a 480px centred card page on the empty app canvas, not a modal, so the request isn't in view. That is tolerable because each sheet restates what it needs (quote, reason, preview). Conditions: fix B2 (Cancel into the flow, pinned bar, sheet padding) and B1 (no sticky banner on sheets); add the request/category line to the header (Minor 9); add the consequence line to A3 (M6). The side sheet can follow once the two-column A1 (M1) exists, because it depends on it. |
| **No second sticky decision bar** | **Acceptable, but the Decision card's own sticky rule must go (B4).** At 390 and 768 the card is the first block after the header. On first paint the pair is visible at 390 (Approve at y≈520–690) and at 768. Under 22em the spec removes the normal pair from the bar anyway. The cost is at 200% text for **urgent** requests: Approve as urgent… sits about two screens down (y≈1871), behind the banner. Fixing B1 recovers most of that. Revisit if the usability review finds pastors scroll past the card. |
| **R16 has no desktop aside** | **Acceptable (Minor).** R16 is a single short task in a centred card. At 1280 nothing is lost except "What happens next" and the phone. Add one `type-body` line under the deadline ("We'll email you and update your page when we've decided.") and the phone line when `church.phone` is set. |

## Accessibility (axe-core 4.10.2)
- **0 violations** on all 116 runs (58 screens × 390 and 1280), including every sheet, the lists, Home, Inbox and all requester states.
- axe can't see these failures, which are covered above:
  - The reflow failures (B1, M11): WCAG 1.4.10.
  - The covered controls at 195 (B1/B2): 2.4.11 Focus Not Obscured.
  - The banner's `role="alert"` on every page load (B1).

## Coverage caveats
- **Undo refused, concurrency alert, offline, loading, impersonation and A2 dual-role** were not staged (they need a second session race, network emulation or impersonation). A13 error states weren't captured.
- **Banners:** the outbox was drained once, part-way through the pass. The 390 normal-text captures of leadership screens were therefore re-taken with a live banner (`banner-*-390.png`). All other modes had banners from the start of their run.
- **Photos:** the test requests have no photos, so photo tiles in the Decision flow weren't exercised.

## Checklist for ham-frontend-engineer (priority order)
- [ ] **B1:** banner slot container, static under 22em, wrapping actions, `siren` icon, `role="region"`, and no sticky banner on sheets.
- [ ] **B2:** Cancel / Keep as `action-bar__back` with the in-flow twin; `.sheet--fullscreen` flex column with a pinned bar and `space-4` inline padding at <768; shorter A9 primaries.
- [ ] **B3:** `.btn { overflow-wrap: normal }`; take buttons out of `<p>`; drop the alert icon under 22em.
- [ ] **B4 / M1:** remove the viewport-gated sticky; build the `detail` container with two columns at 42em, the sticky card only there, and the rail on Requests at 1280–1535.
- [ ] **M2** (with backend): take-over pair for non-original pastors.
- [ ] **M3 / M4:** staff chip tones and icons; remove the requester chip on rows; "Final" reason line; step-3 markers and per-tab line 2; Decided excludes Cancelled; filter chips.
- [ ] **M5** (backend): `waiting_on_requester` join fix + test.
- [ ] **M6 / M7 / M8:** WYSIWYG preview with the real date; A3 consequence line; A9 prefill + preview; Replace / Keep row.
- [ ] **M9:** names and rule values from context / the rules module; drop "Elder".
- [ ] **M10 / M11:** statement and choice-card wrapping; chip height and icon sizing in `em`.
- [ ] **M12 / M13 / M14:** Home / Inbox / banner copy; the "Why it's urgent" block; A9 heading strings.
- [ ] Minors as time allows. Then re-capture at 390, 390 + 200% text, 195, 768, 1280 and 1440 **with a live urgent banner**, and assert: `scrollWidth <= innerWidth`, sheet bar ≤ 18%, and no sticky element over the Decision card or the form.

---

## Re-check at 089473e
ham-ui-designer · 2026-09-29 · after FIX-3B (screens) and FIX-3A (logic). This is a report only: no app code changed.

**Method:** the same as before. Server on port 8045. Database `ham_qa3` was recreated, then `seed_dev` + `seed_dev_requests` were run. The same 14 step-3 states were staged through the services: past decisions under a `FixedClock` with `run_held_decision_effects`, and #010/#011 inside the live 30-minute window. The outbox was drained in event order **before** capture, so a banner is live in every mode. Captures:
- 62 screens at 390, 768, 1024, 1280, 1440, 390 + 200% text, and 195.
- A scrolled pass of every A1 page at 390, 1024, 1280 and 1440.
- Interaction probes for M2, M6, M7, M8, and ticking reasons at 195 and 200% text.
- axe-core 4.10.2: **0 violations on 124 runs** (390 + 1280).

Screenshots are in the session scratchpad (`…/step3-qa-recheck/`), not in the repo.

| ID | Verdict | Evidence |
|---|---|---|
| B1 | **Fixed** | No sideways scroll on any banner page (390t200 = 390, 195 = 195). The banner is static under 22em, `role="region" aria-label="Urgent"`, uses the siren icon, and is not rendered on sheets. |
| B2 | **Partially** | Cancel / Keep now sit in the flow; there's one button in the bar on every sheet; short sheets pin at 390 (bar 73px, 9%); a decline reason can be ticked at 195 and at 200% text. **Still open:** bars are over 18% at 390t200/195 whenever the primary wraps: A2n, A12, A9 decline and R16 at 23%, A9 take-over approve at 29% (243px). And U1, A2c, A2u, A4, A5, A11 and A2n are *not pinned* at large text: the `<form>` wraps only the bar, so sticky has no room (U1 390t200 bar top 1928 of an 844 viewport). |
| B3 | **Partially** | No more letter-by-letter breaks. But at 195 and 390t200, "Undo decision…" **spills outside its own button border**: the button is x82–145 and the text x74–154 (`crop-a1-pending-decider-195-full.png`). The alert icon is still displayed, and "request/er" still breaks in the notice text. |
| B4 | **Fixed** | The side column is 320px at ≥1024. When scrolled, the card never pins over content (full page and 1280 split pane). |
| M1 | **Fixed** (Minor residue) | Two columns via `@container (min-width: 42em)`, and the rail at 1280/1440. Residue: the side column is only as tall as the card (`align-items: start`), so the sticky side card never actually sticks. The old viewport rule at `shell.css:2719–2727` is dead. |
| M2 | **Fixed** | David sees "Take over and approve…" / "Take over and decline…". Copy nit: "Goes to Ruth A.. If…" (`_decision_card.html:90`). |
| M3 | **Partially** | Tones and icons are right (Approved info badge-check, Rejected neutral circle-x, Reconsideration attention rotate-ccw) and the requester chip is gone from rows. The "· Final" reason line is still missing on #017/#019. |
| M4 | **Partially** | Decided now excludes Cancelled (10 rows). Still no step-3 markers, no filter chips, and line 2 is the submission age on every tab. |
| M5 | **Fixed** | Waiting on requester shows 2 (#012, #016). |
| M6 | **Partially** | The preview is WYSIWYG ("until Mon, Oct 12"). There's no empty state ("Here's why:" with nothing after it), and the consequence line is relative only, with no absolute time. |
| M7 | **Not fixed** | On A9 decline, `textarea[name=reason]` stays empty after picking a reason, and there's no `.message-preview` (decider and take-over). |
| M8 | **Fixed** | The edited text is kept and a Replace / Keep mine row appears. |
| M9 | **Partially** | Names now come from context and the undo minutes from `undo_minutes`. Still hard-coded: "The 30 minutes to undo ended" (`request_decision_undo.html:17`) and "Elder" (`_decision_card.html:97`). |
| M10 | **Partially** | A6, A4 and A5 are clean at 390t200. Still open: A9 statement "available" (390t200, 195), A12 "reconsider" (390t200), A6 "Something" (195). |
| M11 | **Fixed** | R17 390t200 has no overflow, chips have auto height, and icons are sized in em. This causes new Major N2 below. |
| M12 | **Not fixed** | Pastor Home still shows "Reconsideration for you (1)" and "Certify urgent · approved (1)". Director Home shows "Call to share a decision (1)". The Director Inbox still receives "Urgent request needs a pastor". The banner still shows the newest item only, with "I've seen this". |
| M13 | **Fixed** | "Why it's urgent" is its own block under the Decision card, with the siren icon and a danger accent bar. |
| M14 | **Fixed** | The strings are correct, but see N1. |

### New Major
- **N1. The A9 decider h1 overflows sideways at large text.** `scrollWidth` is 498 of 390 at 200% text and 251 of 195 at 195 (`a9-decider-390t200-probe.png`). The single word "reconsideration?" at h1 size is wider than the sheet column, and `h1` has no wrap rule. This is WCAG 1.4.10.
  - **Where:** `request_reconsideration_decide.html:22`; `shell.css:32`.
  - **Fix:** `.sheet h1 { overflow-wrap: break-word; hyphens: auto }`, and also, inside the sheet container, `font-size: min(var(--ham-type-h1-size), 9cqi)`, with `container-type: inline-size` on `.sheet--fullscreen`.
- **N2. Status chips now break mid-word ("Approv/ed").** This happens in the L5 "Earlier request found" panel on every A1 page at 390t200 and 195 (`l5-chips-390t200.png`). The `.chip` change from M11 (`white-space: normal`) now inherits `overflow-wrap: anywhere` from `.request-detail p/li` (`shell.css:635–640`).
  - **Fix:** add `overflow-wrap: normal; word-break: normal` to `.chip` at `shell.css:3059`.
- **N3. The desktop urgent banner stretches "Open" to 1100–1260px.** Seen at 1024–1440 (`list-awaiting-ruth-1280.png`, `a1-urgent-1280.png`). `.urgent-banner__actions { flex: 1 1 100% }` plus `.btn { flex: 1 1 auto }` (`shell.css:225–235`) apply at every width, so a huge outline button competes with the page's own Primary.
  - **Fix:** `@container (min-width: 40em) { .urgent-banner__actions { flex: 0 0 auto; margin-inline-start: auto } .urgent-banner__actions .btn { flex: 0 0 auto } }`.

### New Minor
- The banner's `@container (min-width: 22em) { position: sticky }` never sticks, because its containing block is the slot, which wraps it exactly. It scrolls away at every width.
  - **Fix:** make `.urgent-banner-slot` the sticky element, gated by `@media (min-width: 22em) and (min-height: 30em)`. Alternatively, accept static everywhere and update C§40.
- B2's un-pinned bar: move `<form>` to wrap the whole sheet body (as A2/A3 do), or give the sheet `min-height: calc(100dvh - appbar)` with the form as `flex: 1`.

---

## Final re-check at 810210a
ham-ui-designer · 2026-09-29 · after FIX-3D (screens) and FIX-3E (logic). This is a report only: no app code changed.

**Method:** the same as before.
- **Server and data:** server on port 8047. Database `ham_qa3` was recreated, then `seed_dev` + `seed_dev_requests` were run. The same 14 step-3 states were staged: past decisions under a `FixedClock` with `run_held_decision_effects`, and #010/#011 inside the live 30-minute window. The outbox was drained in event order before capture, so a banner is live in every mode.
- **Captures:** 62 screens at 390, 768, 1024, 1280, 1440, 390 + 200% text and 195, plus a scrolled pass of every A1 page.
- **New this round:** a keyboard pass that tabs forward and backward on A1, A3, A2u, A2n and A9 at 390, 390t200, 195 and 1280, checking whether each focused element is fully hidden (`elementFromPoint` at three points).
- **axe-core 4.10.2:** 1 violation on 124 runs (see Minor).

Screenshots are in the session scratchpad (`…/step3-qa-final/`), not in the repo.

| ID | Verdict | Evidence |
|---|---|---|
| B2 | **Partially** | Every sheet now pins its one-button bar at 390, 390t200 and 195, except **A2n** (390t200: bar top 1464 of 844; 195: 760 of 422) and **R16** (1128 of 844). In both, `<form>` opens after the header and quote (`request_decline_urgency.html:20`, `r16_reconsider.html:18`), so the form box starts below the fold. Bars are still 23% (195px) at 390t200 and 99px at 195 on A12, A2n, A9 take-over approve and R16, because the primary wraps. All other sheets are 17–18%. |
| B3 | **Fixed** | "Undo decision…" at 195: button x50–145, text x58–138, no spill. At 390t200: button 98–292, text 114–276. The alert icon is `display: none` and "request/er" no longer breaks. |
| M3 | **Fixed** | "· Final" follows the Rejected chip on #017 and #019. Tones and icons are unchanged and correct. |
| M4 | **Partially** | Markers now render ("Can still be undone", "Can ask to reconsider", "Question open", "Call to share a decision"), and Decided has 10 rows. Still open: (a) rows with `line2_text` **lose their status chip** and repeat the markers as line 2, so #011 reads "Can still be undone · Can ask to reconsider" twice with no chip (`requests_list.html:72–89`, chip only in the `{% else %}`). (b) Labels and icons differ from A§0.4 (no "Undo until 2:11 AM", no "Can ask until Oct 12", no Yours / Goes to…). (c) No All / Approved / Rejected / Final filter chips. (d) Decided and Reconsideration line 2 is still the submission age ("2 h", "5 h"). |
| M6 | **Partially** | The preview stays WYSIWYG ("until Tue, Oct 13"). With no reason picked it still shows "Here's why:" followed by nothing; there's no "Your message will appear here." The consequence line is still relative only ("The email goes after your 30 minutes to undo."), with no absolute send time. |
| M7 | **Fixed** | A9 decline (decider and take-over): picking a reason prefills `textarea[name=reason]`, and `.message-preview` shows the R18b final wording ("We looked at your request again, and we're sorry, we're still not able to help… You're welcome to send a new request…"). |
| M9 | **Fixed** | No "30 minutes", "14 days", "Elder", "Marcus" or "Andre" literals remain in the sheet or card templates. The undo-ended line uses `{{ undo_minutes }}` (`request_decision_undo.html:17`). |
| M10 | **Fixed** (sheets) | No mid-word breaks on any sheet at 390t200 or 195 (A9 "available", A12 "reconsider" and A6 "Something" are gone). Residue outside sheets: the step-2 L5 panel at 195 (Minor 21) now also breaks the new Q-167 reason line "Appr/oved", because its text column is 63px. |
| M12 | **Partially** | Fixed: per-request Home cards (Urgent · HAM #013, Reconsideration · HAM #009, Certify urgent · HAM #014, Call to share · HAM #015), and the banner count and "Got it". Still open: (a) Pastor Home order: "Certify urgent · HAM #014" sits **last**, after the "3 requests are waiting" summary; A§4.1 puts it in group 1, Urgent. (b) Card copy isn't the spec's ("Asked to reconsider · … · you declined it Sep 28"; "Urgent · HAM #014 · Approved by the Board · not yet certified"). (c) Director Home has no Reconsideration (1) or Waiting on requester (2) awareness rows, and the call card has no "decided" date. (d) The Director `--approved` banner has no "Arrange the site visit.". (e) The Director Inbox still lists "Urgent request awaiting a pastor · HAM #0xx" updates. They're retitled, but A§4.3 has no such update for the Director. |
| M14 | **Fixed** | h1s: "Approve HAM #009 after reconsideration?", "Take over and approve HAM #009?". Primaries: Approve / Take over and approve / Decline (final). But see new Major F3. |
| N1 | **Fixed** (overflow) | `scrollWidth` equals the viewport on every sheet at 390t200 and 195. The fix causes F3 below. |
| N2 | **Fixed** | No chip breaks on any page or mode. |
| N3 | **Fixed** | At 1024–1440, Open and Got it are content-sized and right-aligned (`a1-urgent-1280.png`). |

### New Blocker
- **F1. B1 is back: the sticky banner covers up to 64% of the screen at large text.**
  - **What changed:** FIX-3D moved `position: sticky` to `.urgent-banner-slot` and gated it with `@media (min-width: 22em) and (min-height: 30em)` (`shell.css:190–196`). Media-query `em` uses the *initial* font size, not the user's text size. So at 390 + 200% text the slot sticks: it is 485px tall under the 56px app bar, and stays over the page while scrolling (`sticky-slot-a1-urgent-390t200-scrolled.png`).
  - **Impact:** it hides "Approve as urgent…". On A1 at 390t200, 42 of 56 and 53 of 57 keyboard focus stops land fully under the banner. At 390 + 150% it's 253px (37% with the app bar). At 768 + 200% it's 31%.
  - **Why it's a Blocker:** WCAG 2.4.11 and 1.4.10, and this is the exact B1 failure again.
  - **Fix:** make the query font-relative again. Put `container: shell / inline-size` on the element that contains `.urgent-banner-slot` (`.app-shell`), then use `@container shell (min-width: 22em) { @media (min-height: 30em) { .urgent-banner-slot { position: sticky; … } } }`. Container-query `em` uses the container's computed font size, so 390 at 32px root = 12em, which is static. Add a Playwright assertion at 390 with root `font-size: 200%`: slot `position` is `static`.

### New Major
- **F2. Focus is hidden behind the pinned bar and the sticky banner (WCAG 2.4.11).**
  - **Where:** nothing sets `scroll-padding`, so the browser scrolls a focused control to the viewport edge, under sticky chrome. Examples:
    - A2u at 390, normal text: the in-flow **Cancel** lands at y802–822, fully under the bar (`focus-a2u-cancel-390.png`).
    - A9 take-over decline at 390: `reason_code` at y785.
    - A3 at 390t200: `reason_code` at y810.
    - At 1280, backward tabbing on A1 hides controls under the banner and app bar.
  - **Fix:**
    - In `shell.css`: `html { scroll-padding-block: calc(var(--ham-size-appbar-height) + var(--ham-space-4)) calc(var(--ham-size-bottomnav-height) + var(--ham-space-4)); }`.
    - Add `html:has(.urgent-banner-slot) { scroll-padding-block-start: calc(var(--ham-size-appbar-height) + 5rem); }`.
    - Add `html:has(.sheet--fullscreen .action-bar) { scroll-padding-block-end: calc(var(--ham-size-control-md) + 2 * var(--ham-space-3) + var(--ham-space-4)); }`. That's rem-based, so it scales with text.
- **F3. The N1 fix shrinks every sheet h1 below body text.**
  - **What:** `.sheet--fullscreen h1 { font-size: min(var(--ham-type-h1-size), 9cqi) }` (`shell.css:1280–1281`) is width-only, and the line height stays at the fixed token:
    - 195: 11.8px h1 on a 40px line, against 16px body (`a9-recon-approve-decider-195.png`).
    - 390 + 200% text: 23.6px h1 against 32px body.
    - 390, normal text: 29.3px instead of 32px.
  - **Impact:** the heading shrinks as the user enlarges text (1.4.4), and hierarchy inverts on every sheet. My N1 recommendation had no floor; that's corrected here.
  - **Fix:** replace it with `@container (max-width: 22em) { .sheet--fullscreen h1 { font-size: var(--ham-type-h2-size); line-height: 1.2; } }`. Container `em` is font-relative, so this scales with text. Keep `overflow-wrap: break-word; hyphens: auto` for the one long word.
- **F4. The sticky Decision card slides under the sticky banner at ≥1024.**
  - **What:** `.request-detail__side .decision-card { top: calc(appbar + space-6) }` = 80px (`shell.css:3021–3024`), but the banner slot now occupies 56–129. When scrolled, the card's top 49px ("Decision" h2, age and the status chip) is hidden (`a1-declined-1280-scrolled.png`).
  - **Fix:** `body:has(.urgent-banner-slot) .request-detail__side .decision-card { top: calc(var(--ham-size-appbar-height) + var(--ham-space-6) + 4.5rem); }`, or set a `--ham-sticky-offset` custom property on `.app-shell` that the banner adds to. Make sure the card fits: `max-height: calc(100dvh - offset); overflow: auto`.
- **F5. The skip link is invisible when focused (app-wide; 2.4.7 and 2.4.11).**
  - **What:** `.skip-link` has `z-index: var(--ham-z-appbar)` (`shell.css:102`). That's the same layer as the sticky app bar, which comes later in the DOM and paints over it. On focus at 1280, the element at its centre is `.app-bar__logo` (`skiplink-1280.png`).
  - **Fix:** `.skip-link:focus { z-index: var(--ham-z-toast); }`.

### New Minor
- **axe `target-size`:** A9 take-over decline at 390, the 18×18 `take_over` checkbox. The whole 294×56 statement card is its label, so this is near-false-positive. Give the input `inline-size/block-size: 1.5rem`, or add `margin` so 24px spacing holds.
- **Banner copy:** "2 urgent requests need you · Urgent request needs a pastor · HAM #014 Electrical" says "urgent" and "need" twice, and makes the 390 banner 3 lines + actions (153px, 25% with the app bar). Consider "2 urgent requests need a pastor · newest HAM #014 Electrical".
- **Unchanged from earlier rounds:** Minors 15–19 and 21: row line 1 still splits "HAM #020 / · Plumbing or water"; R13 has two Primaries; R18c "respon/sible" breaks at 390t200.

### Coverage caveats
- **Banner count:** seed request #003 is urgent but has no notification (it was seeded directly), so the banner says 2 while Home shows 3 urgent cards. This is a data artifact, not a bug.
- **Not tested:** dark mode, offline, the concurrency alert and impersonation were not re-tested this round.

### Checklist for ham-frontend-engineer (priority order)
- [ ] **F1:** container-query gate for the sticky banner slot, plus a 200%-text test.
- [ ] **F2:** `scroll-padding-block` for the app bar, banner, bottom nav and sheet bar.
- [ ] **F3:** replace the `9cqi` h1 rule with the 22em container step to `type-h2`.
- [ ] **F4:** the Decision card's sticky offset includes the banner.
- [ ] **F5:** skip link above the app bar on focus.
- [ ] **B2 residue:** `<form>` wraps the whole sheet body on A2n and R16. Shorter A12, A2n and A9 take-over primaries so the bar is ≤ 18% at 390t200.
- [ ] **M4 residue:** always render the status chip, no duplicate line-2/markers, A§0.4 marker labels, filter chips, per-tab line 2.
- [ ] **M6 residue:** preview empty state; absolute send time in the consequence line.
- [ ] **M12 residue:** Home group order, card copy, Director awareness rows, `--approved` copy, Director Inbox audience.
