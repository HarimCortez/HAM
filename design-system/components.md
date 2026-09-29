# HAM Components — V1 core

Visual spec for `ham-frontend-engineer`. Behavior and copy come from `docs/ux/`; this file decides how components **look**.
Use tokens only (`tokens.css`), never raw hex or px. Icons are [Lucide](https://lucide.dev) (outline, 1.75 stroke, `--ham-size-icon-md` unless stated).

**Rules for every component**
- Every interactive element: min 48×48px hit area (`--ham-size-target-min`), visible focus ring (`outline: var(--ham-size-focus-ring-width) solid var(--ham-focus-ring); outline-offset: var(--ham-size-focus-ring-offset)`), `:focus-visible` only.
- States to design and build: default, hover (pointer only), focus-visible, pressed, disabled, loading, error, selected (where relevant).
- Motion: `--ham-duration-fast` for hover/press, `--ham-duration-base` for enter, `--ham-duration-slow` max; tokens already drop to 0ms under `prefers-reduced-motion`.
- Color is never the only signal: status = icon + text label; errors = icon + message.
- Text never truncates labels of actions or statuses. Allow wrapping; leave room for ~30% longer translations (PRD §75: V1 English-only). No fixed-width buttons.

---

## 1. App bar (with logo)
- **Anatomy:** `bg.appbar` (dark ink in both themes) · logo · screen title (mobile) · right slot (search icon, notifications, avatar) · 3px bottom stripe: linear gradient `accent.brand-light → accent.brand-mid → accent.brand-dark` (decorative, `aria-hidden`).
- **Logo:** the brand's `logos.onDark` file (`brands/<brand>/brand.json`; Miami Temple: `brands/miami-temple/logo-white-on-dark.png`), height 32px (lockup) on ≥390px wide; the brand's `logos.mark` at 28px when a back button + title need the room (detail screens on mobile). Logo links to Home; `alt` = `logos.alt` + " — HAM" (Miami Temple: `alt="Miami Temple Seventh-day Adventist — HAM"`). Never hard-code the church's logo path or name in a component.
- **Height:** `--ham-size-appbar-height` + `env(safe-area-inset-top)`. Sticky, `--ham-z-appbar`.
- **Mobile:** detail screens show back button (left), title (`h3` style, `text.on-appbar`, 1 line, ellipsis allowed for titles only — full title repeated as page `h1`), one overflow action.
- **Desktop (≥1024):** full lockup left, global search field center (max 480px), notifications + avatar right. Sidebar sits below.
- **Impersonation (PRD §59):** a full-width `tone.attention` banner is pinned *under* the app bar ("You are viewing as J. Smith — End"); it cannot be dismissed.
- **Don't:** place the white logo on a light surface; add other colors to the bar.

## 2. Bottom navigation (mobile < 768px)
- 4–5 destinations max, set by the person's highest role (destinations and labels: `docs/ux/navigation.md` §3.1). `bg.surface`, top `border.default`, `--ham-shadow-sm`.
- Item: 24px icon over label (`type-nav-compact`, 12px — the only text below 14px, always with icon). Min 64px wide × 56px tall.
- Selected: icon filled style + `text.brand` label + 32×4px `border.selected` pill above icon. Unselected: `text.secondary`.
- Badge: count dot `tone.danger.icon` with number in `text.on-danger`, min 18px; `aria-label` includes count ("Invitations, 2 new").
- Height `--ham-size-bottomnav-height` + safe-area; hides on scroll-down only if the screen has a sticky primary action.

## 3. Sidebar (≥ 1024px; rail at 768–1023)
- `bg.surface`, right `border.default`, width `--ham-size-sidebar-width` (rail: `--ham-size-sidebar-collapsed`, icons + tooltip).
- Groups separated by `space-6`, optional group label (`type-small`, `text.tertiary`, sentence case).
- Item: 48px tall, `radius-md`, icon + label (`type-label`, `text.secondary`). Hover `bg.hover`. Selected: `bg.selected`, `text.brand`, 4px left bar `border.selected`, `aria-current="page"`.
- Bottom: Settings, Sign out. No role switcher: nav is the union of the person's roles (see `docs/ux/navigation.md` §3).

## 4. Buttons
| Variant | Fill | Text | Border | Use |
|---|---|---|---|---|
| Primary | `action.primary.bg` | `text.on-primary` | none | The ONE main action per screen/sheet |
| Secondary | `action.secondary.bg` | `action.secondary.fg` | 1.5px `action.secondary.border` | Alternative actions |
| Ghost | transparent | `action.ghost.fg` | none | Tertiary, toolbars, "Cancel" |
| Danger | `action.danger.bg` | `text.on-danger` | none | Destructive, only inside a confirm step |
| Link | none | `text.link`, underline | — | Inline navigation in text |
- **Sizes:** sm `control-sm` (desktop dense tables only), md `control-md` (default), lg `control-lg` (mobile field & requester pages primary; full width on mobile).
- **Anatomy:** `radius-md`, padding-inline `space-5`, gap `space-2`, `type-label`, optional leading icon 20px. Icon-only buttons need `aria-label` + tooltip, 48×48.
- **States:** hover `-bg-hover`; pressed `-bg-pressed` + no scale; disabled `action.disabled.*` (avoid—prefer enabled button + explanatory error); loading: spinner replaces leading icon, label stays, `aria-busy`, width locked.
- **Placement:** mobile primary in a sticky bottom action bar (thumb zone); desktop primary right-aligned at end of form/header.
- **Don't:** two primary buttons on one screen; green text buttons on light-green fills; use Danger for "Decline invitation" (declining is normal — use Secondary).

## 5. Status chip
The single language for every state (projects §52, tasks §15.5, invitations/commitments §28–§33 (names Q-017), attendance §37.2, credential verification §24 (Q-018)), plus three non-status markers in the same chip shape: Urgent priority, the *Excused* flag (Q-022) and the computed credential-expiry badges *Expiring Soon* / *Expired* (Q-018).
- **Anatomy:** pill `radius-pill`, height 28px (32px on requester pages), padding-inline `space-3`, icon 16px (`--ham-status-*-icon`) + label (`type-chip`, `--ham-status-*-fg`) on `--ham-status-*-bg`, 1px `--ham-status-*-border`.
- **Tokens:** `--ham-status-{group}-{slug}-{bg|fg|border|icon}` (see `tokens.json › status` for label + tone + icon of every state). Label text = exact PRD status name.
- **Variants:** `subtle` (default, above); `outline` (transparent bg, for dense tables); `dot` (8px icon-colored dot + label, no pill — table cells on desktop only). Icon is always present in subtle/outline.
- **Reason line:** Blocked (task) and On Hold (project) always show the reason next to/under the chip ("Blocked · Materials").
- **Urgent** is a separate chip placed *before* the status chip; never merged into status.
- Not interactive. If filtering by status, use a Filter chip (§ Form fields), not the status chip.
- **Don't:** invent colors per status; show a chip without its icon; abbreviate labels.

## 6. Card
- `bg.surface`, `radius-lg`, padding `space-4` (mobile) / `space-5` (desktop), `border.default` 1px in light, no shadow at rest; interactive cards get `shadow-sm` on hover and whole-card link (one `<a>` covering title; secondary actions stay separately focusable).
- **Project card anatomy:** chips row (Urgent, status) → title (`h3`) → meta line (date, general area — never requester name/address unless the viewer's role allows; see §18 and Q-004) → staffing progress ("6 of 8 volunteers", bar: track `bg.sunken`, fill `action.primary.bg`, height 8px, `radius-pill`, text always shown) → footer (Project Leader avatar + name).
- Group content with spacing, not inner borders. Max one divider (`border.subtle`) per card.

## 7. Attention / action item row
For "What needs attention" lists (PRD §64) and personal to-dos.
- Row 64px min, `bg.surface`, left 4px bar in the item's tone `-icon` color, 24px tone icon, title (`type-label`), one-line context (`type-small`, `text.secondary`), right: due text ("Due in 2 days") + chevron or inline action (Secondary sm).
- Sorted by severity: danger → attention → info. Count chip in section header.
- Whole row is a link; inline action is a separate button (not nested).

## 8. KPI tile
For member scoreboard (PRD §63) and leadership dashboard (§64).
- `bg.surface`, `radius-lg`, padding `space-5`. Label (`type-label`, `text.secondary`) → number (`type-kpi`, `text.primary`, `font-variant-numeric: tabular-nums`) → comparison line (`type-small`: "▲ 12 vs last month", arrow icon + words, never color alone).
- Hero variant (Families Served, Volunteer Hours): number 56px on desktop, `accent.brand-*` decorative 4px top stripe.
- Time switcher (This Month / This Year / All-Time) is a segmented control above the tile group, not per tile.
- Aggregate only — no names, addresses or circumstances (PRD §63, §68).

## 9. Table (desktop ≥ 1024) / list (mobile)
- Header row `bg.sunken`, `type-small` 600 `text.secondary`, sticky. Rows 52px (dense 48px), `border.subtle` row separators only (no vertical lines), hover `bg.hover`, selected `bg.selected` + checkbox.
- Numbers right-aligned, `tabular-nums`. Status column uses chip `outline` or `dot` variant.
- Sort: header button with arrow icon + `aria-sort`. Pagination or "Load more" at 50 rows.
- Persistent filter bar above (see patterns.md). Empty result → Empty state (compact).
- **Mobile:** tables become stacked list rows (title, chip, 1 meta line). Never horizontal-scroll a table on phones except the budget detail, which gets a sticky first column.

## 10. Form fields
- **Anatomy:** label above (`type-label`, `text.primary`) · optional "(optional)" suffix — required is the default, don't mark with red asterisks · helper text (`type-small`, `text.secondary`) · input · error message.
- **Input:** height `control-md` (`control-lg` on requester pages), `bg.surface`, 1.5px `border.strong`, `radius-md`, padding-inline `space-3`, `type-body` (16px — prevents iOS zoom). Focus: border `border.selected` + focus ring. Error: border `tone.danger.icon`, message with `circle-alert` icon in `tone.danger.fg`, `aria-describedby`, `aria-invalid`. Read-only: `bg.sunken`, no border.
- **Types:** text, textarea (auto-grow, min 3 rows), select (native on mobile), date/time (native pickers; show local time with timezone hint, PRD §70.5), checkbox/radio (24px box, 48px row), toggle (only for instant settings), segmented control (2–4 options), search, file/photo (see patterns.md), currency (prefix `$`, right-aligned, tabular).
- **Prefilled / templated values** (PRD §3.1, §19): show a small `text.tertiary` note "From template ‘Roof repair’" under the field; user can edit.
- **Required justification fields** (dependency override §15.4, excused event §33): textarea with visible character hint, placed directly above the confirming button.
- **Filter chip:** 36px pill (48px hit), `border.default`, selected = `bg.selected` + check icon + `border.selected`.

## 11. Alerts and banners
- **Inline alert:** `radius-md`, `--ham-tone-{info|success|attention|danger}-bg`, 1px `-border`, 20px icon in `-icon`, title (`type-label`, `-fg`) + body (`type-body`, `text.primary`), optional action link. `role="status"` (info/success) or `role="alert"` (danger).
- **Page banner:** full width under app bar, no radius; for safety holds (PRD §39: "On Hold — safety hazard reported"), integration outages (PRD §70.3: "Google Calendar sync is paused. Your work is saved."), impersonation. Dismissible only if informational.
- Safety and legal banners use `danger` and cannot be dismissed.

## 12. Empty states
- Centered in the content area, max width 360px: 96px simple line illustration using `accent.brand-*` + `neutral` only (decorative, `alt=""`), title (`h3`), one sentence (`text.secondary`), one primary or secondary action.
- Tone is warm and specific: "No invitations right now. We'll let you know when a project needs your skills."
- Compact variant (inside tables/cards): icon 32px + one line + link.

## 13. Toast
- `bg.inverse`, `text.on-inverse`, `radius-md`, `shadow-lg`, max-width 480px; bottom-center above bottom nav on mobile, bottom-right on desktop. Icon (`text.on-inverse`) + message + optional "Undo"/"View" action.
- Auto-dismiss 6s, paused on hover/focus; `role="status"`. Never for errors that need action (use inline alert) or for anything the user must read (agreements, safety).

## 14. Modal / bottom sheet
- **Mobile:** bottom sheet, `bg.surface-raised`, top `radius-xl`, drag handle 36×4px `border.default`, max 90vh, sticky footer with primary action. **Desktop:** centered modal 480/640px, `radius-lg`, `shadow-lg`. Scrim `bg.scrim`.
- Title (`h2`), close button (48px, top-right), body, footer: primary right, ghost "Cancel" left of it.
- Focus trapped, `Esc` closes (not for mandatory confirmations), returns focus to trigger. Enter: `duration-base` slide/fade; exit `duration-fast`.
- **Confirm destructive/consequential actions** (cancel commitment, reject request, clear safety hold): state consequence in plain words; for reliability-affecting cancellations show the impact before confirming (PRD §33, §34).

## 15. Avatar
- Circle; sizes 24 / 32 / 40 / 64px. Photo or initials (`type-label`, `text.primary` on `bg.sunken`; 2 letters). Never color-code people by role or reliability.
- Optional status badge bottom-right 10px (e.g. Mentor = `award` icon badge 16px, with text elsewhere).
- Avatar stacks: max 4 + "+3" counter; accessible name lists count ("8 volunteers").

## 16. Status timeline
Shared by project lifecycle, request history, commitment history, credential verification, incident + amendments.
- Vertical list; each event: 24px tone icon in a circle on a 2px `border.default` rail, title (`type-label`), actor + local time (`type-small`, `text.secondary`, e.g. "Pastor A. Diaz · Sep 27, 2:14 PM"), optional note.
- Current state: icon filled in tone color + "Current" label; future lifecycle steps (optional, project only): `circle-dashed`, `text.tertiary`.
- Immutable records (incidents §56, comments §57): amendments shown as nested entries labeled "Amendment", original never visually replaced; deleted comments show "Comment deleted by {actor} · {time}".
- Desktop: may render horizontally as a stepper for the §52 main path only; alternates (On Hold, etc.) always shown as a banner, not a step.

## 17. AI suggestion card (PRD §61, §79)
Must never be mistaken for a decision or saved data.
- `bg.surface`, 1.5px **dashed** `tone.ai.border`, `radius-lg`, header: `sparkles` icon (`tone.ai.icon`) + "Suggestion" chip (`tone.ai.*`) + source line ("Drafted by AI from the assessment · not saved").
- Body: the draft content (list, text, estimate). Money is always labeled "Estimate" (PRD §61.3).
- Footer actions, in this order: **Accept** (Primary sm/md) · **Edit** (Secondary) · **Dismiss** (Ghost). On Accept, HAM runs normal permission/rule validation; if validation fails show an inline `danger` alert *inside* the card (e.g. "Volunteer lacks required electrical license" — PRD §27.1); the card stays a suggestion.
- After Accept, the content renders as normal data (solid border, no violet) with a small timeline note "Accepted AI suggestion · {actor} · {time}".
- Partial accept: list suggestions (tasks, materials) get a checkbox per item + "Accept selected".
- **Read-only AI output** (e.g. the "Suggested summary" on the leadership dashboard, PRD §64) has nothing to accept, so it uses **Refresh** (Secondary) + **Hide** (Ghost) instead of Accept / Edit / Dismiss. It keeps the dashed violet border, the "AI draft" chip, the generated-at time and "Check before acting.", and uses `aria-live="off"`.
- Violet (`tone.ai`) is reserved for AI and is never used for a status.

## 18. Privacy-masked field (PRD §3.4, §67, §68)
For requester name, address, phone, circumstances, and license numbers when the viewer lacks permission or data is not yet revealed.
- Rendering: label as normal; value area `bg.sunken`, `radius-sm`, `lock` icon 16px + text "Hidden" (`text.secondary`) + reason in `type-small` ("Visible to the Project Leader and directors"). No bullet-dot fake data, no blur of real data (real data must never be sent to the client).
- **Reveal on demand** (design proposal, not yet a numbered PRD question; only where the UX spec hides a value by default from a role that is allowed to see it): Ghost button "Show address" (`eye` icon); reveal is audited — add small `text.tertiary` note "Viewing is logged". Re-hides on navigation.
- Partial reveal (design proposal): only where the UX spec/PRD permits, e.g. general area before assignment per Q-004. Show the permitted part + lock icon for the rest.
- Never used in Google Calendar, dashboards or reports — those simply omit the field.

---

# Additions for step 2 (Intake), v1.3

Used by `design-system/screens/intake.md`. Class names are proposals in the same BEM style as `ham/web/static/web/shell.css`; reuse existing classes (`.btn--*`, `.chip--*`, `.inline-alert--*`, `.card`, `.form-field`, `.list-detail`, `.sheet`) wherever they already fit. New tokens in v1.3: `--ham-breakpoint-short`, `--ham-size-{icon-xl, list-row-min, chip, chip-lg, choice-card-min, code-input-max, dropzone-height, progress-height, accent-bar, empty-max, modal-sm, modal-md, split-list, split-list-min, split-list-max, step-rail, aside, wizard-max, requester-wide-max}`, `--ham-type-code-entry-*`, `--ham-shadow-bar-top`. (`shell.css` already reads `--ham-size-chip`, `--ham-size-empty-max` and `--ham-size-modal-sm` with fallbacks; the fallbacks can now go.)

**Large-text contract (requester pages).** Every component below must work for a 390px phone with the browser/OS text size at 200% *and* at 200% page zoom (≈195 CSS px wide), with no horizontal page scroll:
- Heights are `min-height`, never `height`, so controls grow with their text. Labels wrap; nothing truncates except record titles.
- Any value that can be long and unbroken (email addresses, street lines, file names) gets `overflow-wrap: anywhere`.
- Multi-column grids use **container queries on the grid**, not viewport media queries, so they collapse to one column when the text is large (thresholds in `em`, which scale with the text).
- Icons in cards and chips are sized in `em` relative to the label (1.25em) with the `--ham-size-icon-*` value as the minimum, so they scale with the text instead of looking tiny.

## 19. Choice card, choice chip (radio / checkbox as a big target)
For "What kind of help?", "Whose home is it?", "Type of home", hazards (R4), "This is urgent" and the certification ticks.
- **Anatomy (`.choice-card`):** a real `<input type="radio|checkbox">` inside a `<label>` that is the whole card. Left: the 24px control (`accent-color: var(--ham-action-primary-bg)`); optional icon (`--ham-size-icon-lg`, `text.secondary`); label (`type-body-lg` 600 on requester pages, `type-label` in the app); optional hint line (`type-body` on requester pages / `type-small` in the app, `text.secondary`).
- **Box:** `bg.surface`, 1.5px `border.strong`, `radius-md`, padding `space-3` block / `space-4` inline, gap `space-3`, `min-height: var(--ham-size-choice-card-min)`, text top-aligned with the control.
- **States:** hover (pointer) `bg.hover`; focus-visible = focus ring on the **card** (`:has(:focus-visible)`), not only the tiny control; **selected** `bg.selected` + 2px `border.selected` (inset so the size doesn't jump) + icon and label `text.brand`; disabled `bg.sunken`, `text.disabled`, reason as text below the group; error: the fieldset (not each card) gets the error message above the cards and a 2px `tone.danger.icon` left rule on the group.
- **Grid (`.choice-grid`):** CSS grid, gap `space-2` (requester) / `space-3` (roomy). Columns by container query: `repeat(auto-fill, minmax(min(100%, 11em), 1fr))`. At 390 with normal text this gives 2 columns for short labels; at 200% text it gives 1. Long-label groups (relationship, certification, hazard "None") are always 1 column.
- **Exclusive card** (`.choice-card--exclusive`, "None that I know of"): full width, separated from the grid by `space-4` and a `text.secondary` "or" line (`type-body`), `shield-check` icon. Ticking it clears the others and vice versa; a visually hidden `aria-live="polite"` line announces what was cleared.
- **Reveal card** ("This is urgent"): a checkbox card whose checked state reveals content directly below it, inside the same visual group (`space-3` gap, left 2px `border.selected` rule on the revealed area). The revealed area is in the DOM after the card, not in a popover.
- **Certification tick** (`.choice-card--statement`): 1 column, label `type-body-lg` **400** (it's a sentence, not a title), bold only on the inserted owner name. Never pre-ticked.
- **Choice chip (`.choice-chip`):** for multi-select sets of short answers ("Why is it urgent?", visit days and times). Pill `radius-pill`, `min-height: var(--ham-size-target-min)`, padding-inline `space-4`, `type-label`, 1.5px `border.strong`, `bg.surface`; selected = `bg.selected` + `border.selected` + leading `check` icon (the icon is the non-color signal). Wraps (`flex-wrap`, gap `space-2`). A chip that is really a single choice (radio) uses the same look with `role` from the native radio.
- **A11y:** every set is a `fieldset` + `legend` (`type-label`, or `type-h3` when it's the step's main question); hints linked with `aria-describedby`. No custom ARIA widgets.
- **Don't:** use cards for more than ~10 options; use a toggle for a one-off tick; put a link inside a card label (the whole card is the label).

## 20. Code input (6-digit email code)
- **Anatomy (`.code-input`):** label "Code from your email" (`type-label`) → one `<input>` (`inputmode="numeric"`, `autocomplete="one-time-code"`, `maxlength` large enough for pasted spaces) → helper (`type-body`, `text.secondary`) → error.
- **Box:** `max-width: var(--ham-size-code-input-max)`, width 100%, `min-height: var(--ham-size-control-lg)`, `type-code-entry` (tabular-nums, `font-feature-settings: "ss02"`), centered text, 1.5px `border.strong`, `radius-md`, `bg.surface`. Placeholder none (no fake digits).
- **Never** six separate boxes: they break paste, autofill, screen readers and large text.
- **States:** focus = `border.selected` + ring; checking (after the 6th digit) = the Confirm button enters loading, the field goes `aria-busy` and read-only; wrong = `tone.danger.icon` border + message with tries left; expired/locked = field disabled + `attention` inline alert with **Send a new code**; success = replaced by the next screen (no green flash).
- **Narrow/large text:** a container query drops `letter-spacing` to `0.1em` below `16em` of field width so 6 digits never overflow.

## 21. Step indicator (wizard header and step list)
- **Step header (`.step-header`, every size):** eyebrow "Step 2 of 5 · The home" (`type-label`, `text.secondary`; R8 says "Last step") → progress bar (`--ham-size-progress-height`, track `bg.sunken`, fill `action.primary.bg`, `radius-pill`, `role="progressbar"` hidden from AT because the text already says it: `aria-hidden="true"`) → `h1` → quiet caption "Your answers are saved." (`type-body` on requester pages, never `type-small`; `text.tertiary`; 16px `cloud-check` icon, decorative). Spacing: eyebrow→bar `space-2`, bar→h1 `space-4`, h1→caption `space-1`, caption→first field `space-6`.
- **Step list (`.step-list`, ≥1024 only):** an `<ol>` in a `nav aria-label="Steps"`, width `--ham-size-step-rail`, sticky at `top: calc(var(--ham-size-appbar-height) + var(--ham-space-8))`. Item: min 48px, `radius-md`, 24px step marker circle + label (`type-label`). Done: `circle-check` icon `tone.active.icon` + label as a link (`text.link`, no underline until hover) back to that step. Current: `bg.selected`, `text.brand`, 4px (`--ham-size-accent-bar`) left bar `border.selected`, `aria-current="step"`. Upcoming: `circle-dashed` `text.tertiary`, not a link.
- Hidden below 1024; the header's text carries the progress there.

## 22. Sticky action bar
The thumb-zone home of the one primary action (P§1). Formalizes step 1's `.public-shell .form-actions` rule.
- **Anatomy (`.action-bar`):** `position: sticky; bottom: 0`, `bg.surface`, top 1px `border.default`, `--ham-shadow-bar-top` only while content is scrolled beneath it, padding `space-3` block / `space-4` inline + `env(safe-area-inset-bottom)`, `z: --ham-z-sticky`. Contents centered to the page column (`max-width: var(--ham-size-form-max)` on requester pages).
- **Layout:** `[Back / Start over (Ghost)] [Primary, flex: 1]`, gap `space-3` (≥ 8px apart, WCAG 2.5.8). A loading primary locks its width.
- **Large text:** if the bar's inner width is under `22em` (container query), Back leaves the bar and renders in the form flow directly after the last field as a Ghost button; the bar holds the primary only. The bar must never exceed 25% of the viewport height: button labels are short (≤ 3 words) and never wrap to more than 2 lines. When the viewport is shorter than `breakpoint.short` (`(max-height: 480px)`, landscape phone), the bar becomes static at the end of the form.
- **Keyboard open (mobile):** the bar stays above the on-screen keyboard (it's in normal flow with sticky, not `position: fixed`); fields scroll into view above it (`scroll-padding-bottom` = bar height).
- **≥1024:** not sticky. The same buttons sit at the end of the form card: Ghost left, primary right (`justify-content: space-between`).
- **With bottom nav (signed-in, <768):** sits directly above the bottom nav; bottom nav hides on scroll-down only on screens that have this bar (C§2).

## 23. Review summary card (R6)
- `.card` with a header row: section name (`type-h3`) left, **Edit** Link-style button right (`min-height` 48px, `aria-label="Edit your need"`). Body: a `kv-list` in `type-body-lg`; quoted description in `text.secondary`, clamped to 4 lines with "Show all" (the full text is also one Edit away). Highlighted value (the email or phone the code/call goes to): `type-h3` weight on its own line, `overflow-wrap: anywhere`, preceded by its lead-in line.
- Card gap `space-3`; 1 column below 1024, 2×2 grid at ≥1280 (`grid-template-columns: repeat(auto-fit, minmax(min(100%, 18em), 1fr))`).

## 24. Upload tile, drop zone, upload summary (R9; P§8)
- **Pickers:** mobile: **Take a photo** (Primary lg, `camera`) + **Choose from my phone** (Secondary lg, `images`), stacked full width, gap `space-3`. ≥1024: **Choose photos or videos** (Secondary) inside the drop zone; **Take a photo** is hidden where there's no camera capture.
- **Drop zone (`.dropzone`, ≥768 only):** `min-height: var(--ham-size-dropzone-height)`, 2px dashed `border.strong`, `radius-lg`, `bg.surface`, centered `upload` icon (`--ham-size-icon-lg`, `text.secondary`) + "Drag photos here, or" + the button. Drag-over: `bg.selected`, `border.selected` dashed, text "Drop to add". Works entirely without drag and drop.
- **Tile (`.upload-tile`):** grid item, 1:1 thumbnail `radius-md`, `bg.sunken` while loading; **status strip below the image** on `bg.surface` (never text over the photo, whose colors we can't control): progress bar (`--ham-size-progress-height`, fill `action.primary.bg` on `bg.sunken`) + `type-small` status ("Uploading 60%", "Waiting to upload", "Getting your video ready…", "Uploaded" with `circle-check` `tone.success.icon`, "Couldn't upload" with `circle-alert` `tone.danger.icon` + **Retry** Link button). Remove: 48×48 icon button (`x`) at the tile's top-right on a `bg.surface` circle with `shadow-sm`, `aria-label="Remove photo 3"`. Video: `play` badge + duration ("0:42") bottom-left on a `bg.inverse` pill (`text.on-inverse`, `type-small`), which is a solid fill, so contrast holds on any image.
- **Grid:** `repeat(auto-fill, minmax(min(100%, 6.5rem), 1fr))`, gap `space-2`: 3-up at 390 with normal text, 1–2-up at 200% text (the minimum is in rem, so it grows with the text), 5-up in the 640 column at desktop.
- **Summary (`.upload-summary`):** above the grid, `type-label`: "4 of 10 photos · 0 of 3 videos" (tabular-nums), plus a polite live region with "3 of 4 uploaded". Offline: `attention` inline alert with `cloud-off`.
- **Limit reached:** pickers disabled and the reason shown as text directly under them (not a tooltip).

## 25. Masked contact block (extends §18)
Three variants of one component (`.masked-block`), all `radius-md`, padding `space-4`, `bg.sunken`, gap `space-2`.
1. **Requester self-view (R10, `--self`):** partial values as text: "d•••@gmail.com", "(•••) •••-0142", "Street address on file · Miami 33142". Bullet characters are `aria-hidden`; a visually hidden span reads "email ending in gmail dot com". `lock` 16px + "Shown partly to keep your details private." (`type-body`, `text.secondary`). No button.
2. **Leadership hidden (L2, `--hidden`):** header row: label "Requester & contact" (`type-h3`) + lock note ("Leadership only" or "Leadership only · viewing is logged", `type-small`, `text.secondary`, `lock` icon). Body: `lock` + "Hidden" (`type-label`, `text.secondary`) + reason "Visible to HAM leadership and approvers." (`type-small`) + the fields that are hidden, as words ("Name, phone, email, street address"). Action: **Show contact details** Secondary md (`eye`), `aria-label` includes "for HAM #047". No fake data, and nothing real sent to the client until the click.
3. **Revealed (`--revealed`):** background switches to `bg.surface` with 1.5px `border.default`; the lock note stays (and is part of the region's accessible name). Values `type-body-lg`, `overflow-wrap: anywhere`; phone is a `tel:` link and on <1024 also a Secondary **Call** button; email a `mailto:` link. **Hide** Ghost sm. Focus moves to the "Requester & contact" heading.
4. **No access (Administrator, `--none`):** as variant 2 without the button: "Hidden · Not shown to the Administrator role."
- **Don't:** blur real values, use hover to reveal, or show "••••" in place of fields leadership can't see at all.

## 26. Requester status card (R7, R10)
- `.card` (`radius-lg`, padding `space-5`, `bg.surface`) with a 4px top bar in the tone's `-icon` color (`--ham-size-accent-bar`; decorative). Row: Urgent chip (if any) + status chip at `--ham-size-chip-lg`. Then the plain sentence (`type-body-lg`, `text.primary`), then "What happens next" (`type-label`) + a numbered list (`type-body-lg`, `space-2` between items).
- **Requester chip labels and tones** (requester words from N§5; the staff chip keeps the §52 name and tone):

| Staff status | Requester chip | Tone tokens | Icon |
|---|---|---|---|
| Submitted | Received | `--ham-tone-info-*` | `inbox` |
| Awaiting Approval | Being reviewed | `--ham-tone-info-*` (not amber: nothing is waiting on her) | `hourglass` |
| Cancelled | Closed | `--ham-tone-neutral-*` | `ban` |
| (priority) | Urgent | `--ham-status-priority-urgent-*` | `siren` |

  Later statuses get requester labels when their steps are designed.
- **Success hero (R7, R7N):** above the card, a `circle-check-big` at `--ham-size-icon-xl` in `tone.success.icon` (decorative, `aria-hidden`) and the h1. No confetti, no animation beyond the normal enter.

## 27. Action card ("Things we need from you", R10) and attention card (leadership Home)
- **Action card (`.action-card`):** `.card` with left `--ham-size-accent-bar` in `tone.attention.icon`; title `type-h3`; one sentence `type-body-lg`; optional reason from HAM in a quote block (`bg.sunken`, `radius-sm`, padding `space-3`, prefixed "HAM asked:" in `type-label`); one button (Primary lg, full width on mobile). The first action card's button is the page's only primary.
- **Attention card (`.attention-card`):** C§7 row promoted to a card for Home: left accent bar in the item's tone, 24px tone icon + title (`type-label`), context line (`type-small`, `text.secondary`, e.g. "oldest waiting 1 day"), right-aligned action (Secondary sm at ≥1024, full-width Secondary md at <768). **Urgent** variant: Urgent chip before the title, accent bar `tone.danger.icon`, action becomes Primary ("Call now"). **Awareness** variant (not actionable): no bar, no button, `text.secondary` title with "Owner: pastors · awareness only" and excluded from counts (N§8.3).

## 28. Request row (L1, L8) and markers
- **Row (`.request-row`):** whole row is one link to the detail; `min-height: var(--ham-size-list-row-min)`; padding `space-3` block / `space-4` inline; `border.subtle` separators. Line 1: Urgent chip (if any) + **HAM #047 · Roof or ceiling** (`type-label`, `text.primary`; the number is `white-space: nowrap`). Line 2: status chip (`outline` variant) + age ("3 days", `type-small`, `text.secondary`, `tabular-nums`). Line 3 (only if any): markers.
- **Marker (`.marker`):** inline icon 16px + word, `type-small`, `text.secondary`; separated by `space-3`; wrap freely. Set: `copy` "Earlier request" · `image` "4 photos" · `phone` "Updates by phone" · `phone-call` "Phone check needed" (this one uses `tone.attention.fg` text and icon, since it's the Director's to-do).
- **Selected (split view):** `bg.selected` + left `--ham-size-accent-bar` `border.selected` + `aria-current="true"`. Hover `bg.hover`.
- **Table form (1024–1279):** the same data as columns: Request · Status · Age · Markers; rows 52px; chip `outline`.
- Never shows name, street, neighborhood or ZIP (Q-132).

## 29. Tabs with counts (saved views)
- `role="tablist"` only if panels switch in place; since each view is its own URL, use a `nav` of links with `aria-current="page"` (`.view-tabs`). Item: min 48px, padding-inline `space-4`, `type-label` `text.secondary`; count in a `chip--tag` style pill (`bg.sunken`, `type-chip`); current: `text.brand` + 3px bottom bar `border.selected`. Track: bottom 1px `border.default`.
- **Mobile:** single row, horizontal scroll *inside the tab row only* (`overflow-x: auto`, `scroll-snap`), with 24px fade masks at the edges as overflow cues and the current tab scrolled into view. At 200% text the row still scrolls; the page never does.

## 30. Error summary
- `inline-alert--danger` at the top of the form, `role="alert"`, `tabindex="-1"`, receives focus on submit. Title "Please check {n} things" (`type-label`) + a list of links, each to its field ("Choose what kind of help you need"). The links use `tone.danger.fg` with an underline (not `text.link`), which is 6.80:1 on `tone.danger.bg`.

## 31. Disclosure and overflow menu
- **Disclosure (`.disclosure`):** native `<details><summary>`; summary is a 48px row, `type-label`, `text.link`, `chevron-right` rotating 90° (`duration-fast`, off under reduced motion). Content indented `space-6`, `type-body` (`type-body-lg` on requester pages).
- **Overflow menu (`More ▾`):** Secondary md button with `ellipsis` + "More"; opens a popover menu (≥1024: `bg.surface-raised`, `radius-md`, `shadow-md`, items 48px, `type-body`) or a bottom sheet listing the same items (<1024). Menu items that open a consequential sheet end with "…".

## 32. Sheet sizes (extends §14)
- **Small** (`--ham-size-modal-sm`): L10 close, L11 more photos. **Medium** (`--ham-size-modal-md`): L9 phone check.
- **Full-screen sheet (<768):** for sheets whose content is longer than half the screen (L9): full height, no drag handle, app-bar-style header on `bg.surface` with ✕ (48px) left and the title (`type-h3`), the body scrolls, and the primary sits in the §22 action bar.

---

# Additions for step 3 (Approvals), v1.4

Used by `design-system/screens/approvals.md`. **No new tokens** in v1.4: everything below is built from v1.3 tokens (`tokens.css` stays 1.3.0). Class names are proposals in the same BEM style as `ham/web/static/web/shell.css`; reuse `.card`, `.btn--*`, `.chip--*`, `.inline-alert--*`, `.choice-card--statement`, `.action-bar`, `.sheet`, `.locked-note`, `.urgent-banner`, `.marker` wherever they fit. New icons needed in `icons.svg` are listed in the screen spec's checklist.

The large-text contract from v1.3 applies to every component here, on leadership screens too (step-2 NM3): `min-height` only, container queries in `em`, decorative icons dropped under `22em`, `overflow-wrap: anywhere` on every quoted user text.

## 26a. Requester chip labels for step 3 (extends the §26 table)
| Staff status (§52) | Requester chip | Tone tokens | Icon |
|---|---|---|---|
| Approved | Approved | `--ham-tone-success-*` (good news for her; staff chip stays `status-project-approved`, info) | `circle-check` |
| Rejected (can be reconsidered) | Not approved | `--ham-tone-neutral-*` (never red) | `circle-x` |
| Reconsideration Pending | Taking another look | `--ham-tone-info-*` (not amber: nothing waits on her) | `rotate-ccw` |
| Rejected · final | Closed | `--ham-tone-neutral-*` | `ban` |
| Awaiting Approval, question open | Being reviewed (unchanged) | info | `hourglass` |

Staff screens keep the §52 chips from `tokens.json › status.project` (Approved info `badge-check`, Rejected neutral `circle-x`, Reconsideration Pending attention `rotate-ccw`). "Final" is never a separate chip: it is a **reason line** after the Rejected chip ("Rejected · Final"), like "Blocked · Materials" (§5).

## 33. Decision card (`.decision-card`)
The one place on a request where the decision state and the decision actions live (UX A1). It is a `section` with `aria-labelledby` its h2 "Decision", placed **before** the long content in the DOM at every width.
- **Box:** `.card` (`bg.surface`, 1px `border.default`, `radius-lg`, padding `space-4` <1024 / `space-5` ≥1024) with a top `size.accent-bar` in the state's tone `-icon` colour (decorative): awaiting `tone.attention.icon` · urgent awaiting `tone.danger.icon` · pending undo `tone.info.icon` · approved `tone.info.icon` · rejected / final `tone.neutral.icon` · reconsideration `tone.attention.icon` · read-only/blocked: no bar.
- **Anatomy (top to bottom, gap `space-3`):**
  1. h2 "Decision" (`type-h3`) + optional right-aligned `type-small` `text.secondary` age ("waiting 5 days", `tabular-nums`, `nowrap`).
  2. **State line** (`type-body`, `text.primary`): who can decide, or the outcome chip row (status chip + Urgent chip if any, `size.chip`) followed by the decider line (`type-small`, `text.secondary`): "Pastor Ruth Alvarez · pastoral route · Oct 6, 3:15 PM".
  3. Optional **notice** (§37 pending notice, or an `inline-alert` compact for urgent / window / concurrency).
  4. Optional **quote blocks** (§35): "What we told the requester", "Why approved (leaders only)", the reconsideration note.
  5. Optional **question marker** (`.marker--attention`, `message-circle-question`): "Waiting on the requester's answer · asked by Andre W. · 2 days".
  6. **Actions** (`.decision-card__actions`): the §34 pair (or one Primary), then secondary actions as a wrap row of Secondary md buttons (Ask a question, More ▾). Gap `space-2` (≥ 8px).
  7. **Reason line** when an action is unavailable (`.locked-note`: `lock` 16px + `type-small` `text.secondary`), never a disabled button alone.
- **Sticky (≥1024 two-column only):** `position: sticky; top: space-6` inside the scrolling detail pane (split view) or `top: calc(size.appbar-height + space-6)` on the full page. Not sticky when the viewport is shorter than `breakpoint.short`, or when the detail is one column (container query), so it never covers content at 200% text.
- **States:** loading = a `bg.sunken` skeleton block the height of the awaiting card, no buttons, `aria-busy="true"` on the section, and it resolves **last** (never a flash of enabled buttons); error = `inline-alert--danger` inside the card "We couldn't load the decision." + **Try again** (Secondary md); offline = actions shown with `action.disabled.*` + a reason line with `cloud-off` "You're offline. You can decide when you're connected."; impersonating = decision/undo/question actions removed and one reason line "Decisions and questions can't be recorded while acting as someone else." (Change category stays, Q-172); read-only (Administrator, decided, or not your route) = no actions area at all.
- **Focus:** after any decision, undo or take-over, focus moves to the card's h2 (`tabindex="-1"`), so the new state is read.
- **Don't:** colour the Approve or Decline buttons green/red; put the decision buttons only in the sticky bar (the card must work alone); show the card's accent colour as the only state signal (the chip and words carry it).

## 34. Decision button pair (`.decision-pair`)
Approve and Decline carry **equal visual weight** (owner decision; §3.2 "humans decide").
- **Normal pair:** two **Secondary** buttons of the same size (`control-lg` <1024, `control-md` ≥1024), same fill (`action.secondary.*`), same leading icon size, one grid row `1fr 1fr` (gap `space-3`), in the order **Approve…** then **Decline…**. Icons: `check` and `x` in `action.secondary.fg` (same colour both). No Primary on the page while the pair shows.
- **Urgent pair:** **Approve as urgent…** is Primary (speed is the point, §10) and **Decline…** is Secondary, both the same height; the grid becomes `2fr 1fr` at ≥22em.
- **Stacking:** in the Decision card at ≥1024 the pair stacks full width (1 column), Approve first. In any container under `22em` the pair stacks full width.
- **In the <768 sticky bar (§22):** at ≥22em bar width the pair sits in the bar side by side. Under `22em` a normal pair **leaves the bar entirely** (no primary exists to keep) and shows stacked in the Decision card, which sits right under the header; an urgent pair keeps only **Approve as urgent…** in the bar and **Decline…** shows in the card. The bar and the card render the buttons from the same data; the hidden copy is `display: none`, so assistive tech meets each button once.
- **Accessible names** include the request: "Approve HAM #047", "Decline HAM #047", "Approve HAM #048 as urgent" (visible label first, so 2.5.3 Label in Name holds).
- **Don't:** use Danger for Decline (declining is a pastoral decision, not a destructive system action); give one button an icon and not the other; reorder by recommendation.

## 35. Quote block (`.quote-block`)
For the requester's own words, the message we sent, questions, answers and notes. Formalizes the "quote block" named in §27.
- **Markup:** `<figure class="quote-block">` + `<figcaption>` (above the quote) + `<blockquote>`. The caption is visible text, not an ARIA label.
- **Box:** `bg.sunken`, `radius-sm`, padding `space-3` block / `space-4` inline, left `size.accent-bar` rule in `border.strong` (decorative). Text `text.primary` (15.85:1 on `bg.sunken`), `type-body` in the app / `type-body-lg` on requester pages, `overflow-wrap: anywhere`, `white-space: pre-line` (keeps the writer's line breaks). Caption `type-small` (app) / `type-body` (requester), `text.secondary`, gap `space-1`.
- **Variants:** `--leaders-only`: caption gets a `lock` 16px icon and ends "(leaders only)"; `--muted` (withdrawn question): text `text.secondary`, no strike-through; `--hidden` (Administrator): body replaced by `lock` + "Not shown to the Administrator role." (`type-small`, `text.secondary`).
- **Long text:** in lists of several (Q&A thread, decided panel) clamp at 6 lines with a **Show all** Link button (`size.target-min` row); never clamp on requester pages.
- **Don't:** use curly-quote glyphs as the only marker; italicize (hard to read at large sizes).

## 36. Message preview (`.message-preview`, "What the requester will read")
Shows the decider exactly what the requester reads (UX A3, A9). Always WYSIWYG with R15/R18b.
- **Region:** `<section role="region" aria-labelledby>` with heading "What the requester will read" (`type-label`) + caption "In the email and on their request page" (`type-small`, `text.secondary`), `mail` icon 20px before the heading. After Show contact details it reads "What Doris will read" (Q-170).
- **Frame:** `bg.surface`, 1.5px **dashed** `border.strong`, `radius-md`, padding `space-4`. Dashed says "not saved yet, a draft render"; it is neutral grey, never the AI violet.
- **Body:** the requester-page rendering at requester type sizes (`type-body-lg`, `text.primary`): the fixed sentence → "Here's why:" → the message in a §35 quote block (requester variant) → the fixed closing lines (with the deadline date bold). Nothing inside is interactive.
- **Behaviour:** updates on input with a debounce; `aria-live="off"`. An empty message shows the quote block with `text.tertiary` "Your message will appear here."
- **<768:** inside a §31 disclosure "What the requester will read", **open by default**. **≥768:** always visible under the message field.
- **Don't:** render it inside a phone mockup frame or at a reduced scale (the point is legibility).

## 37. Pending-decision notice (undo window, Q-156/Q-176)
A decision can be undone by the person who recorded it for `{rules.DECISION_UNDO_WINDOW}` (30 minutes; the number comes from the rules module, never a literal).
- **Component:** `inline-alert--info` compact inside the Decision card, `timer` icon (`tone.info.icon`). Title `type-label` `tone.info.fg`; body `type-small` `text.primary`.
  - **Decider:** title "Can be undone until 3:45 PM" · body "Nothing has been sent to the requester yet." (urgent certification adds "Marcus and Andre were alerted right away.") · action **Undo decision…** (Secondary md, `undo-2` icon; opens the undo sheet). `aria-label` "Undo the approval of HAM #047".
  - **Everyone else:** title "Decision pending (Pastor Ruth, can be undone until 3:45 PM)" · body "You can't decide while it can still be undone." No action.
- **Time:** always an absolute local time in a `<time datetime>` (never a ticking countdown: a live countdown is noisy for screen readers and fails the spirit of 2.2.1). When the window passes while the page is open, the notice is removed on the next minute tick and a polite status says "The time to undo has passed. The decision stands."
- **In rows and cards:** a `.marker` with `timer` icon: "Undo until 3:45 PM" (decider) / "Decision pending" (others), `type-small`, `text.secondary`.
- **Don't:** use the attention or danger tone (nothing is wrong); hide the outcome chip during the window (the decision is real, only reversible).

## 38. Question thread (`.qa-thread`)
The "Questions and answers" section on A1 (and the requester's own Q&A on R10).
- `ol` of items, gap `space-4`, each item a `li` with no box (group by space):
  1. Meta line: `message-circle-question` 16px + "Andre Whitfield asked · Oct 6, 3:02 PM" (`type-small`, `text.secondary`; requester side: "From HAM · Oct 6", no names, Q-171).
  2. The question (§35).
  3. State row, one of:
     - **Open:** `.marker--attention` `hourglass` "Waiting for the requester's answer · 2 days" + actions (wrap row, Secondary sm ≥1024 / Secondary md <1024): **Record their answer** · **Withdraw** (asker, Director, AD).
     - **Answered:** meta `message-circle` "The requester answered · Oct 7, 9:12 AM" (or "Answer taken by phone · Marcus Bell · Oct 7, 6:40 PM") + the answer (§35).
     - **Answered, Administrator:** "Answered on Oct 7" only; no answer text, no hidden-block placeholder beyond one `lock` line (Q-124/Q-151).
     - **Withdrawn:** `text.tertiary` meta "Withdrawn · no longer needed" (automatic on a decision) or "Withdrawn by Andre W. · Oct 7"; the question in the `--muted` quote variant.
  4. A **new** answer (not yet opened by the asker) gets a `.marker` "New" (`message-circle`, `tone.attention.fg`) before the meta line; it clears on view.
- Heading "Questions and answers ({n})" `type-h2` (`type-h3` in the split pane). Empty: the section is omitted; "Ask a question" lives in the Decision card.
- Items are immutable: no edit or delete affordances ever.

## 39. Side sheet (≥1024; extends §14 and §32)
Decision sheets on desktop open from the right edge, so the request stays in view behind a light scrim and the sheet sits where the Decision card was.
- **Frame:** `role="dialog"` `aria-modal="true"` `aria-labelledby` its h2. Anchored right, from under the app bar to the viewport bottom, width `size.modal-sm` (approve, undo, question, phone answer, category, not urgent, take-over approve) or `size.modal-md` (decline and reconsideration decline, which carry the preview), max `100vw - size.sidebar-collapsed`. `bg.surface-raised`, `shadow-lg`, left corners `radius-lg`. Scrim `bg.scrim` over the rest, click on scrim = Cancel (not for the undo sheet).
- **Header:** h2 (`type-h2`) + request line "HAM #047 · Roof or ceiling" (`type-small`, `text.secondary`) + ✕ icon button (48×48, `aria-label="Close"`), padding `space-5`, bottom 1px `border.subtle` only while the body is scrolled.
- **Body:** scrolls; padding `space-5`; fields `space-6` apart.
- **Footer (sticky at the sheet bottom):** top 1px `border.default`, padding `space-4` / `space-5`. Consequence line (`type-small`, `text.primary`, `info` 16px icon) on its own row, then `[Cancel (Ghost)] … [Primary]` right-aligned (`justify-content: flex-end`, gap `space-3`).
- **Motion:** enter slide from the right `space-8` + fade over `duration-base` `easing-enter`; exit `duration-fast` `easing-exit`; reduced motion = fade only (tokens already drop to 0ms).
- **768–1023:** the same content as a centered modal (§14) at the same width, max-height 90vh, sticky footer.
- **<768:** the §32 full-screen sheet: **no bottom nav** (the sheet covers it; z `--ham-z-sheet`), header ✕ left + title `type-h3`, body scroll, and the §22 action bar as footer. In the bar at ≥22em: the consequence line (`type-small`, max 2 lines) above `[Cancel (Ghost)] [Primary flex 1]`. **Under 22em** the consequence line and Cancel move into the flow as the last items of the body (Cancel as a full-width Ghost), and the bar holds **only the primary** (≤ 18% of the viewport). The body is a flex column with `flex: 1`, so on short sheets the bar is pinned to the viewport bottom.
- **Focus:** on open, the h2 (`tabindex="-1"`); Tab order header ✕ → body fields → consequence → Cancel → Primary; Esc and ✕ return focus to the trigger button (or, after a successful record, to the Decision card h2).

## 40. Urgent banner (`.urgent-banner`, formalizes step 2)
App-wide, under the app bar, above the impersonation banner. One banner row at most: several items collapse into a count ("2 urgent requests need a pastor" + **Open list**).
| Variant | Audience | Tone | Icon | Text | Actions | Dismiss |
|---|---|---|---|---|---|---|
| `--needs-pastor` | Pastors | `tone.danger` | `siren` | "Urgent request needs a pastor · HAM #048 Plumbing or water" | **Open** (Secondary sm) · **I've seen this** (Ghost sm) | Hides for this person only; returns on the next new urgent request. Clears for all when decided, certified or left for normal review |
| `--approved` | Director, AD | `tone.danger` | `siren` | "Urgent request approved · HAM #048 Plumbing or water. Arrange the site visit." | **Open** · **Got it** | Must acknowledge (§10, Q-161): stays until **Got it** or Open |
| `--undone` | Director, AD | `tone.attention` | `undo-2` | "The urgent approval of HAM #048 was undone by Pastor Ruth A. It's waiting for a decision again." | **Open** · **Got it** | Until Got it; replaces an unacknowledged `--approved` for the same request |
- **Box:** `-bg` fill, bottom 1px `-border`, padding `space-3` / `space-4`, icon 24px in `-icon`, text `type-label` `text.primary` with the HAM # `nowrap`; actions wrap to their own row (`flex: 1 1 16em` text, `min-width: 0`, step-2 N5).
- **Sticky** under the app bar at ≥22em. The banner sits in a slot that is a size container; under `22em` the banner is `position: static`, so at 200% text it scrolls away instead of eating the viewport.
- **A11y:** `role="region"` `aria-label="Urgent"`; the first arrival is announced once through a separate polite live region, never by making the whole banner live.
- Leadership only. Text never contains a name, address or circumstance (Q-132).
