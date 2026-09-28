# Intake: hi-fi screen specs (build-order step 2)

Owner: ham-ui-designer · 2026-09-28 · Design system v1.3.0
Behavior, copy and rules come from `docs/ux/intake.md` (screens R1–R12, L1–L11, emails; cited **UX R2** etc.) and `docs/ux/navigation.md` (**N§n**). Where those differ from `docs/architecture/intake.md`, its "Owner decisions and reconciliation" box wins; nothing here changes behavior. Components are `design-system/components.md` (**C§n**; §19–§32 are new in v1.3), patterns `design-system/patterns.md` (**P§n**).

Tokens only: every color, size, space, radius, shadow and duration below is a token name (`--ham-…` without the prefix where unambiguous, e.g. `space-6`, `text.secondary`, `type-body-lg`). No raw values. Copy in quotes is from the UX spec; `{rules.X}` and `{church.X}` are filled at runtime, never literals.

Contents
0. Shared rules for this step (breakpoints, large text, type and spacing rhythm, focus, targets, contrast)
1. Requester frame (public shell, wizard layout)
2. Requester screens R1–R12
3. Leadership frame
4. Leadership screens L1, L8, L2, L5, L9, L10, L11, L7 and Home cards
5. Emails (visual)
6. Frontend checklist
7. Visual QA plan

---

## 0. Shared rules for this step

### 0.1 Breakpoints and what changes
| Width | Requester pages | Leadership pages |
|---|---|---|
| 390 (`sm`, design base; works down to 320) | Single column, gutters `space-4`, sticky action bar (C§22) | App bar + bottom nav; list → push detail |
| 768 (`md`) | Same column centered at `size.form-max`, gutters `space-6`, still the sticky bar (touch devices) | Sidebar rail; list as full-width rows; push detail |
| 1024 (`lg`) | Form becomes a card; step list at left; buttons at the end of the card (not sticky) | Full sidebar; list as a table; detail as full page |
| 1280 (`xl`) | Step list + form card + "Good to know" panel (`size.wizard-max`) | **Split view**: list pane `size.split-list-min` + one-column detail pane |
| 1536 (`2xl`) | as 1280, centered | Split view: list pane `size.split-list` + detail pane with main and side columns |

### 0.2 Large-text contract (requester pages; the owner's hard requirement)
Doris uses a phone with text at 200%. Every R screen must pass all of these, at 390×844 with 200% text **and** at 200% page zoom (≈195 CSS px), and at 320 CSS px with normal text:
1. **No horizontal page scroll.** Long unbroken values (email, street, file names) get `overflow-wrap: anywhere`. Nothing has a fixed width; `min-width: 0` on grid/flex children.
2. **The primary action is always reachable** in the sticky action bar (C§22). Under a `22em` bar width, Back leaves the bar and sits in the form flow after the last field; the bar holds only the primary and stays ≤ 25% of the viewport height. Below the `breakpoint.short` viewport height (landscape) the bar stops being sticky and sits at the end of the form.
3. **Grids collapse by container query**, not viewport: choice cards (C§19) go 2 → 1 column; upload tiles 3 → 2 → 1; review cards 2 → 1.
4. **Controls grow with text:** `min-height` only (`size.control-lg`, `size.choice-card-min`, `size.target-min`), padding in `space-*`, icons in `em` with the `size.icon-*` value as a floor.
5. **No clipping:** no `overflow: hidden` on text containers, no `line-clamp` on requester pages except the R6 description preview (which has "Show all").
6. **The logo bar stays one line:** the app bar keeps the logo at `size.logo-min-height` and nothing else, so it never wraps.

### 0.3 Type rhythm
| Role | Requester pages | Leadership pages |
|---|---|---|
| Page title | `type-h1` (display face), one per screen | `type-h1`; list pages may use `type-display` at ≥1280 |
| Section heading | `type-h2` | `type-h2` (split pane sections: `type-h3`) |
| Main question of a step (fieldset legend) | `type-h2` | — |
| Field label, card title | `type-h3` (one step above body) | `type-label` |
| Body, answers, inputs | `type-body-lg` | `type-body` |
| Helper / hint text | `type-body`, `text.secondary` (never below `type-body`) | `type-small`, `text.secondary` |
| Metadata (ages, times) | `type-body`, `text.secondary` | `type-small`, `text.secondary`, `tabular-nums` |
| Chips | `type-chip` at `size.chip-lg` | `type-chip` at `size.chip` |
| Codes and request numbers on confirmations | `type-code-entry` (tabular, `ss02`) | `type-label` |

Requester pages set `font-feature-settings: "ss02"` on `body` (README Typography). Sentence case everywhere; display face only for h1.

### 0.4 Spacing rhythm
- **Requester, vertical:** eyebrow → h1 `space-2` · h1 → lead paragraph `space-3` · paragraph → paragraph `space-4` · field → field `space-6` · fieldset → fieldset `space-8` · h2 section top `space-10`, h2 → content `space-3` · last content → action bar `space-8`.
- **Leadership, vertical:** page header → tabs `space-4` · tabs → filter bar `space-4` · detail sections `space-8` apart, heading → content `space-3` · card padding `space-4` (<1024) / `space-5` (≥1024).
- Group with space, not boxes (P§4). A card is used only where the UX spec names one (status card, summary cards, action cards, masked block).

### 0.5 Focus, targets, contrast (apply everywhere below)
- Focus ring: `focus.ring` at `size.focus-ring-width` + `size.focus-ring-offset`, `:focus-visible` only. On selected choice cards the ring is checked against `bg.selected` (6.04:1, contrast table).
- Targets: every interactive element ≥ `size.target-min`; requester buttons `size.control-lg`; adjacent targets ≥ `space-2` apart.
- On each step change, focus moves to the new h1 and `<title>` updates (UX §8). On sheet open, focus goes to the sheet heading; on close, back to the trigger.
- Contrast pairs used on these screens all pass AA (README contrast table, v1.3 adds `text.secondary`/`focus.ring`/`border.selected` on `bg.selected`, `action.primary.bg` and `border.strong` on `bg.sunken`). Text on photos never happens (C§24). Amber (`tone.attention`) is never used for body text on white except as `tone.attention.fg` (6.80:1).
- Color is never alone: chips have icons + words; markers have icons + words; errors have `circle-alert` + words; selected cards have a filled control + border + color.
- Motion: `duration-base` for step enter (fade + `space-2` rise), `duration-fast` for card selection; all zero under `prefers-reduced-motion`.

---

## 1. Requester frame

### 1.1 Public shell (reuse step 1 `base_public.html`)
- `public-shell__bar`: `bg.appbar`, `size.appbar-height`, centered brand `logos.onDark` at `size.logo-min-height`, accent stripe (C§1). No nav, no sign-in link.
- `public-card__eyebrow`: "Home Assistance Ministry · {church.name}" (`type-label`, `text.secondary`) on R1, R7, R7N, R10, R11, R12. **Wizard steps R2–R6 and R8 replace it with the step header** (C§21) to save a line.
- Messages (`.messages`) render above the h1 as in step 1.
- Offline: the existing `.offline-banner` directly under the bar, copy per UX R12.

### 1.2 Wizard layout (R2–R6, R8)
New modifier `public-shell__content--wizard`.

**390**
```
┌ app bar: logo ───────────────────────┐
│ Step 2 of 5 · The home               │ type-label, text.secondary
│ ▓▓▓▓▓▓░░░░░░░░░░░░                   │ size.progress-height
│ Where is the home?                   │ type-h1
│ ☁ Your answers are saved.            │ type-body, text.tertiary
│                                      │ space-6
│ [fields … space-6 apart]             │
│                                      │ space-8
├──────────────────────────────────────┤ action bar (C§22), border.default top
│ [ Back ]  [        Continue        ] │ Ghost auto · Primary flex 1, control-lg
└──────────────────────────────────────┘
```
Gutters `space-4`. Action bar inner width = column width.

**390 at 200% text:** the header, fields and cards stack; Back moves into the flow below the last field (full-width Ghost), the bar holds **Continue** only, full width.

**768:** column `size.form-max` centered, gutters `space-6`, same bar (bar background full width, contents constrained to the column).

**1024–1279:** step list (C§21, `size.step-rail`) + form card (`bg.surface`, `radius-lg`, padding `space-8`, max `size.form-max`), gap `space-8`. "Good to know" becomes the last block inside the form card, above the buttons, as a Disclosure (C§31). Buttons at the card's end: Back (Ghost) left, primary right. Not sticky.

**≥1280**
```
┌ app bar: logo (left-aligned at ≥1024, as step 1) ─────────────────────────────────────────────┐
│          size.wizard-max, centered, padding-top space-10                                        │
│ ┌ step-rail ──────┐  ┌ form card (form-max, space-8 pad) ──────────┐  ┌ aside (size.aside) ──┐ │
│ │ ✓ Your need     │  │ Step 2 of 5 · The home                      │  │ Good to know          │ │
│ │ ▌2 The home     │  │ ▓▓▓▓▓▓░░░░░░░░░                              │  │ What happens after    │ │
│ │ ○ Safety        │  │ Where is the home?                          │  │ you ask (3 steps)     │ │
│ │ ○ Reaching you  │  │ ☁ Your answers are saved.                   │  │ ─ space-6 ─           │ │
│ │ ○ Check and send│  │ …fields…                                    │  │ Prefer to talk?       │ │
│ │  (sticky)       │  │                                             │  │ {church.hamPhone}     │ │
│ └─────────────────┘  │ [Back]                          [Continue]  │  │ {church.hamEmail}     │ │
│                      └─────────────────────────────────────────────┘  └───────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```
- Aside: no card; `type-h3` heading, `type-body` text, `text.secondary` meta; sticky like the step list. It's `<aside aria-label="Good to know">`, after the form in DOM order.
- Focus order (all widths): skip link → (≥1024 step list links) → h1 → fields in visual order → Back → Continue → aside links. Back comes before the primary in DOM so keyboard order matches reading order.

### 1.3 Field styling on requester pages
- Label `type-h3`, helper `type-body` `text.secondary` **above** the input (so large-text users read it before typing), input `size.control-lg`, `type-body-lg`, textarea auto-grow.
- "(optional)" suffix in `text.tertiary`, weight 400 (existing `.form-field__optional`).
- Error: C§10 treatment, message `type-body` in `tone.danger.fg` with `circle-alert`, placed between label/helper and input.
- Character counter (R2 description, appears at 1,800): `type-body`, `text.secondary`, right-aligned under the textarea, `aria-live="polite"` only when within 100 of the soft max.

---

## 2. Requester screens

### R1. Ask for help (start)
**Components:** public shell · `inline-alert--attention` (not dismissible, `triangle-alert`) · Primary lg · Link · `tel:` link · C§22 action bar · resume variant uses `inline-alert--info`.

**390**
```
┌ logo bar ────────────────────────────┐
│ Home Assistance Ministry ·           │ eyebrow
│ {church.name}                        │
│ Ask for help with your home          │ type-h1
│ Our church's men's ministry helps …  │ type-body-lg; 3 short paragraphs, space-4
│ ┌──────────────────────────────────┐ │ space-6
│ │ ⚠ In danger right now?           │ │ attention alert: title type-label tone.attention.fg
│ │ Fire, a gas smell, sparking wires│ │ body type-body-lg text.primary
│ │ or flooding: call 911 first.     │ │ "911" is a tel: link
│ └──────────────────────────────────┘ │
│ Takes about 5 minutes. Have your …   │ type-body-lg
│                                      │ space-8
│ Already asked? Check on your request │ Link, target-min row
│ Prefer to talk? Call (305) 555-0100  │ tel: link, target-min row
├──────────────────────────────────────┤
│ [              Start               ] │ Primary lg, full width
└──────────────────────────────────────┘
```
- **Resume variant** (draft in this browser): an `inline-alert--info` (`history` icon) above the danger alert: "You started a request on this browser." The bar becomes **Continue my request** (Primary); **Start over** is a Link under the alert (it opens a small confirm sheet C§32 "Start over? Your saved answers will be erased." Ghost "Keep my answers" · Danger-outline "Start over").
- **768:** same column, centered; the bar stays.
- **≥1024:** single form card (`size.form-max`) holding everything; **Start** sits at the end of the card, right-aligned, `size.control-lg`. **≥1280:** + aside (`size.aside`) "What happens after you ask": the three R7 steps as a numbered list, `type-body`, each with a `size.icon-lg` step circle in `bg.selected`/`text.brand`.
- **States:** loading none (server-rendered); offline: banner, Start still works (the form is cached by the PWA shell); HAM down → R12 maintenance.
- **Focus order:** h1 → body → 911 link → Check on your request → Call → Start. Start is last in DOM but visually sticky; that matches the reading order.
- **Contrast:** alert text `text.primary` on `tone.attention.bg`; title `tone.attention.fg` 6.22:1; icon `tone.attention.icon` 4.22:1.

### R2. Step 1 of 5 · Your need
**Components:** step header (C§21) · choice-card grid with icons (C§19) · textarea · reveal card "This is urgent" (C§19) · 911 line as `inline-alert--attention` (never danger: it's advice, not an error) · choice chips (radio) for urgent reasons · optional textarea · action bar (Ghost **Start over** + Primary **Continue**).

- **Legend** "What kind of help?" `type-h2`; 9 cards, icon + label, no hints. Icons: Roof or ceiling `house` · Plumbing or water `droplet` · Electrical `plug-zap` · Doors, windows or locks `door-closed` · Floors or stairs `layers` · Ramps, rails or grab bars `accessibility` · Painting or walls `paint-roller` · Yard or outside `trees` · Something else or not sure `circle-help` (always last, full width).
- **Grid:** 2 columns at 390 (normal text), 1 column at 200% text, 3 columns at ≥768 (container query at `33em`). Gap `space-2`.
- **"Tell us what's happening":** label `type-h3`, helper (2 sentences) `type-body` `text.secondary`, textarea min 5 rows; the dictation tip below it with a `size.icon-sm` `mic` icon, `type-body`, `text.tertiary`.
- **Urgent card:** full width, `siren` icon in `text.secondary` (becomes `tone.danger.icon` when checked, plus the label stays `text.primary` since red text alone means nothing), hint "It's unsafe or getting worse quickly." When checked the reveal area shows, in order: 911 attention alert → legend "Why is it urgent?" (`type-h3`) → choice chips, **stacked 1 per row** (they're sentences, not tags) → "Anything else about why it's urgent? (optional)" textarea, 2 rows (required only for "Something else": the "(optional)" suffix is removed and the helper says "Please tell us a little more.").
- **390:** single column; the bar: **Start over** (Ghost, opens the confirm sheet) + **Continue**.
- **768:** 3-column category grid; otherwise as 390.
- **≥1280:** wizard layout 1.2; category grid 3 columns inside the 640 card; aside "Good to know": "Big or small, tell us." + what happens next + phone.
- **States:** error on Continue → error summary (C§30) at the top of the card, focused; the category fieldset shows its message above the cards. Offline Continue → the caption changes to `cloud-off` "Saved on this device. We'll finish saving when you're back online." (`type-body`, `tone.attention.fg`), announced once. Loading after Continue: the primary shows its spinner; the next step renders with focus on its h1.
- **Focus order:** h1 → category radios (arrow keys within the group) → description → urgent checkbox → (reveal) reasons → note → Start over → Continue.

### R3. Step 2 of 5 · The home
**Components:** step header · intro line · relationship choice cards (1 column, with hints) · text fields · state text with Link "Change" · property-type choice cards · `inline-alert--info` tenant note.
- **Intro line** under the caption: "Filling this in for someone else? Answer for them." `type-body-lg`, `text.secondary`, `users` icon at `size.icon-md`.
- **"Whose home is it?"** `type-h2` legend; 3 cards, 1 column, icons `key-round` (I own it), `house` (I rent it), `users` (It's a family member's home). Selecting "family" reveals "Owner's full name" (reveal pattern C§19) with helper "The person who owns the home." Selecting "rent" shows the tenant note as an `inline-alert--info` (`file-signature` icon) directly under the cards.
- **Address block:** one `fieldset` "Where is the home?" (`type-h2`) with Street · Apartment or unit (optional) · City · ZIP. At ≥768, City and ZIP sit side by side (`2fr 1fr`, container query at `30em`); at 390 they stack. ZIP input `inputmode="numeric"`; width follows the grid (no fixed width).
- **State:** read-only line "Florida · **Change**" (`type-body-lg`; Change is a Link button, `size.target-min` tall). Change swaps in a native select, focus moves to it.
- **"Type of home"** `type-h2`; 5 cards: House `house`, Townhouse `building`, Apartment or condo `building-2`, Mobile or manufactured home `caravan`, Other `circle-help`; 2-column grid rule as R2.
- **States / focus / widths:** as R2. Back returns to R2 with its answers.

### R4. Step 3 of 5 · Safety at the home
**Components:** step header · helper line with `shield` icon · checkbox-card grid (C§19) · exclusive card "None that I know of" · conditional textarea.
- **Legend** "Is there anything at the home our volunteers should know about?" `type-h2`, hint "Choose at least one." (`type-body`, `text.secondary`) and helper "This keeps everyone safe, including you. It won't stop us from helping." directly under the legend.
- **Cards:** Dogs or other animals `dog` · Mold `droplets` · Exposed or damaged wiring `zap` · Sagging floors, roof or stairs `triangle-alert` · Pests (bees, rodents, insects) `bug` · Something else `circle-ellipsis`. Icons are `text.secondary` at rest, `text.brand` when selected (hazards are information here, so no amber or red on the requester side).
- **Grid:** 2 columns at 390, 1 at 200% text, 3 at ≥768. Then `space-4`, an "or" line (`type-body`, `text.secondary`, centered), then the exclusive card **None that I know of** (`shield-check`), full width.
- Visually hidden `aria-live="polite"` status for "We cleared 'None that I know of'".
- **"Tell us more (optional)"** textarea appears under the exclusive card once any hazard is ticked; required (suffix removed) only for "Something else".
- **Error:** "Please choose at least one, or 'None that I know of'." above the grid; the group gets the C§19 `tone.danger.icon` left rule.
- **≥1280 aside:** "Why we ask" (one paragraph) + phone.

### R5. Step 4 of 5 · Reaching you
**Components:** text/tel/email fields · typo suggestion (AA§A1) · checkbox row "I don't use email" · `inline-alert--info` · radio segmented as two choice cards · availability choice chips · optional textarea.
- **Order:** Your name → Phone number → Email → ☐ I don't use email → How should we contact you? → When could someone visit? → Anything else (optional).
- **Email typo suggestion:** under the field, `inline-alert--info` compact (no title): "Did you mean doris.p@**gmail.com**?" + Link button "Use this" (`size.target-min`). Never auto-corrects.
- **"I don't use email"** is a C§19 choice card (checkbox, full width, `mail-x` icon) placed **directly under** the Email field (`space-3`). Checked: Email collapses (`duration-base`), the info alert "That's OK. A HAM leader will call you…" appears in its place, and the contact preference group shows Phone call selected and locked (read-only card, `bg.sunken`, `lock` at `size.icon-sm`, text "We'll call you").
- **"How should we contact you?"** two choice cards side by side at every width that fits (`auto-fill` minmax `11em`): Email `mail` · Phone call `phone`. Helper under the legend: "HAM's automatic messages always come by email."
- **"When could someone visit?"** choice chips (multi) in two rows: days from the church profile (Sunday… Friday), then Mornings · Afternoons; then, after `space-3`, **Any time works** (single chip, `calendar-check`); selecting it clears the others (same polite announcement pattern as R4).
- Family variant: the helper "We'll contact you about this request and arrange visits with you." sits under the step h1 in `type-body-lg`.
- **States/widths/focus:** as R2. Phone field shows the number formatted on blur, never while typing.

### R6. Step 5 of 5 · Check and send
**Components:** review summary cards (C§23) with Edit · highlighted "We'll send a code to" value · `type-h2` "Please confirm" · two statement choice cards (C§19 `--statement`) · tip line · privacy line with `lock` · error summary · Primary **Send request** with loading.

**390**
```
│ Step 5 of 5 · Check and send         │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                   │
│ Check and send                       │ h1
│ ┌ Your need ───────────────── Edit ┐ │ summary cards, gap space-3
│ │ Roof or ceiling                  │ │
│ │ (Urgent) Water is coming in …    │ │ Urgent chip chip-lg
│ │ "Water comes through my bedroom… │ │ text.secondary, 4-line clamp + Show all
│ └──────────────────────────────────┘ │
│ ┌ The home ────────────────── Edit ┐ │
│ ┌ Safety at the home ──────── Edit ┐ │
│ ┌ Reaching you ────────────── Edit ┐ │
│ │ Doris Pennington · (305) 555-0142│ │
│ │ By email · Any time works        │ │
│ │ We'll send a code to:            │ │ type-body
│ │ doris.p@gmail.com                │ │ type-h3, overflow-wrap:anywhere
│ └──────────────────────────────────┘ │
│ Please confirm                       │ type-h2, space-10 above
│ Filling this in for someone? Please  │ type-body, text.secondary, `info` icon
│ read these to them.                  │
│ ┌ ☐ I own this home, and I give HAM ┐│ statement cards, 1 col, gap space-3
│ └───────────────────────────────────┘│
│ ┌ ☐ If a homeowners' association, … ┐│
│ └───────────────────────────────────┘│
│ 🔒 Your details stay private inside  │ type-body, text.secondary; link text.link
│ HAM. How we use your information     │
├──────────────────────────────────────┤
│ [ Back ]  [      Send request      ] │
```
- **No-email variant:** the Reaching-you card shows "We'll call this number to confirm:" + the phone as the highlighted value.
- **Edit** returns to the step with the primary relabelled **Back to review**.
- **≥1280:** for this step only, the form card spans the form and aside columns (`grid-column: 2 / -1`; no aside on R6), which gives the summary cards a 2×2 grid; "Please confirm", the privacy line and the buttons span the card width below. The step list stays.
- **States:** missing ticks → error summary focused ("Please tick both boxes to send your request."), each statement card with the group error; **sending** → Send shows spinner, `aria-busy`, width locked, Back disabled; **send failed** → `inline-alert--danger` above the buttons: "We couldn't send your request just now. Your answers are still here." + **Try again** (Secondary); **offline** → Send disabled with the reason as text directly above the bar ("You can send your request when you're connected."), `cloud-off`; **form token expired** → page re-renders with answers + `inline-alert--info` "Please tap Send request again."
- **Focus order:** h1 → each card's Edit (after its content) → statement 1 → statement 2 → privacy link → Back → Send.

### R8. Check your email ("Last step")
**Components:** step header ("Last step", bar full) · code input (C§20) · Primary **Confirm** · Secondary **Resend code** with countdown text · Link "Wrong email? Change it" · Disclosure "Didn't get it?" (C§31).

**390**
```
│ Last step                            │ eyebrow, bar full
│ Check your email                     │ h1
│ Your answers are saved. To send your │ type-body-lg
│ request, enter the 6-digit code we   │
│ sent to doris.p@gmail.com.           │ address bold, overflow-wrap:anywhere
│ Or tap Confirm my email in that      │ type-body-lg, "Confirm my email" bold
│ message. It works on any phone or    │
│ computer.                            │
│ Code from your email                 │ type-h3 label
│ ┌──────────────┐                     │ code input, code-input-max, type-code-entry
│ │  4 8 2 9 1 3 │                     │
│ └──────────────┘                     │
│ The code works for {minutes} minutes.│ type-body, text.secondary
│ [ Resend code ] You can resend in    │ Secondary lg (disabled look) + type-body
│   0:24                               │ text.secondary, updated every 5 s
│ Wrong email? Change it               │ Link, target-min row
│ ▸ Didn't get it?                     │ disclosure
├──────────────────────────────────────┤
│ [             Confirm              ] │ Primary lg
```
- **Step-1 look reuse:** this is the step-1 "Check your email" screen (`check-your-email-390.png`) with the step header added and the code field in `type-code-entry`; Resend sits on its own row below the field (step-1 M4 rule), not in the bar.
- **"Didn't get it?" content:** a bulleted list (`type-body-lg`): spam folder · sender "{church.shortName} HAM" · can take a minute; then "Can't get into your email?" paragraph with the Link **Choose 'I don't use email' instead**; then "Still stuck? Call {church.hamPhone}" (`tel:`).
- **New-link variant (from R11a):** eyebrow is the normal Home Assistance Ministry eyebrow (no step header); address shown masked "d•••@gmail.com" (with the visually hidden spoken form, C§25); no "Change it" link.
- **Cross-device confirm page** ("Confirm your request"): public card, h1 "Confirm your request", one sentence, **Continue** Primary lg in the bar. Nothing else (safe against link scanners).
- **≥1024:** wizard layout; the step list shows all five steps with ✓ and **not** as links (editing now goes through "Change it"); aside shows "Didn't get it?" content expanded instead of the disclosure.
- **States:** wrong code → field error "That code doesn't match. You have {n} tries left." (`tone.danger.fg`), field keeps the value selected for easy retype; checking → Confirm loading, field read-only; expired/locked → field disabled, `inline-alert--attention` "This code has expired. Your answers are still saved." + **Send a new code** (Secondary lg), Confirm hidden; resend available → one polite announcement "You can send a new code now."; daily limit → `inline-alert--attention` with the UX R12 copy, Resend removed, `tel:` link; confirmed on another device → when the tab regains focus it navigates to R7.
- **Focus:** on load, h1 (not the code field, so the explanation is read first; the field is the next tab stop). Order: h1 → code → Resend → Change it → Didn't get it → Confirm.
- **Contrast:** the countdown uses `text.secondary` 7.22:1; the disabled Resend uses `action.disabled.*` and is paired with the countdown text, so the reason is never color-only.

### R7. Request received (R10 in welcome mode)
**Components:** success hero (C§26) · request number in `type-code-entry` · `inline-alert--attention` urgent line · "What happens next" numbered list · action card "Add photos" (C§27) with Primary lg · Link "I'll add photos later" · then the R10 sections.

**390**
```
│ Home Assistance Ministry · …         │ eyebrow
│ ✓ (size.icon-xl, tone.success.icon)  │
│ Thank you, Doris. We've received     │ h1 (focused on load)
│ your request.                        │
│ Your request number is               │ type-body-lg
│ HAM #047                             │ type-code-entry, nowrap
│ [Urgent] Because this is urgent, …   │ attention alert (urgent only)
│ What happens next                    │ type-h2
│ 1. Our pastors or Board review …     │ numbered, type-body-lg, space-2
│ 2. If it's approved, someone from …  │
│ We've emailed a link to this page to │ type-body, text.secondary
│ d•••@gmail.com …                     │
│ ┌▌Add photos ──────────────────────┐ │ action card, space-8 above
│ │ Photos help us understand the     │ │
│ │ work. You can add up to {…}.      │ │
│ │ [         Add photos           ]  │ │ Primary lg (the page's only primary)
│ └───────────────────────────────────┘ │
│ I'll add photos later                │ Link, target-min
│ ── then R10 sections from "Your      │
│    request" down ──                  │
```
- The **Add photos** button is inside the card, not in the sticky bar (the page is long and informational; the card sits in the first screen at normal text). At 200% text the card falls below the first screen, so at <768 the action bar **is** used on R7: it carries **Add photos**, and the card's own button is not rendered (one primary in the DOM at a time). At ≥768 the bar is absent and the card's button is the primary.
- **≥1280:** `size.requester-wide-max` container, two columns (`3fr 2fr`, gap `space-8`): left = hero, number, urgent line, what happens next, Add photos card; right = Your request, How to reach us. Focus order follows DOM: left column then right.
- **States:** loading → skeleton of the hero and status card (`bg.sunken` blocks, P§10); offline → cached page + banner, Add photos disabled with "You can add photos when you're connected."

### R7N. Request saved (no email)
**Components:** success hero · number in `type-code-entry` + "Please write it down." · numbered next steps · `tel:` link · `inline-alert--attention` urgent line · Secondary lg **Done** in the action bar.
- Layout as the UX R7N wireframe. The phone number in step 1 of "What happens next" is `type-body-lg` bold, `overflow-wrap: anywhere`.
- "The call may come from a number you don't know…" sits in a quiet `bg.sunken` block (`radius-md`, padding `space-4`, `phone-incoming` icon) so it's noticed without alarm.
- **No primary button** on this screen; **Done** is Secondary lg, full width in the bar.
- **≥1024:** single public card (`size.form-max`), Done right-aligned at its end. No aside (nothing more to read ahead).
- **Focus:** h1 on load → number → list → call link → Done.

### R9. Add photos and videos
**Components:** public card · limits line · pickers (C§24) · drop zone (≥768) · upload summary + tile grid · helper tip · privacy line · Primary **Done** in the bar.

**390**
```
│ Home Assistance Ministry · …         │
│ Add photos                           │ h1
│ You can add up to {…} photos and {…} │ type-body-lg
│ short videos (up to {…} each).       │
│ Try one photo from a distance and one│ type-body, text.secondary, `lightbulb`
│ up close.                            │
│ [📷        Take a photo            ] │ Secondary lg, camera icon (see note)
│ [🖼    Choose from my phone         ] │ Secondary lg
│ 4 of 10 photos · 0 of 3 videos       │ type-label, tabular-nums
│ ┌────┐┌────┐┌────┐                   │ tiles 3-up
│ │img ││img ││img │  each: strip below│
│ └────┘└────┘└────┘  progress + status│
│ 🔒 Only the people handling your     │ type-body, text.secondary
│ request will see these.              │
├──────────────────────────────────────┤
│ [              Done                ] │ Primary lg
```
- **One primary rule:** the UX spec calls Take a photo "Primary-style"; to keep one primary per screen, **Take a photo** is a Secondary lg with a filled `camera` icon and sits first; **Done** is the Primary in the bar. Before any file is chosen, Done reads **Done** and simply returns to R10 (enabled at any time, UX R9).
- **768:** + drop zone above the pickers (pickers inside it). Tiles 4-up.
- **≥1024:** public card at `size.form-max` + aside "Good to know" (who sees photos, the limits, the ministry phone) at ≥1280. Drop zone with **Choose photos or videos** (Secondary); **Take a photo** hidden unless the device supports capture. Tiles 5-up. Done right-aligned at the end of the card.
- **States (tile-level, C§24):** waiting · uploading % · processing · uploaded ✓ · failed + Retry · too big / too long / wrong type (the tile shows the file name, `file-x` icon and the reason; no thumbnail) · removed (tile disappears; polite "Photo 3 removed").
- **States (page-level):** offline → `inline-alert--attention` (`cloud-off`) "Paused. We'll keep going when you're back online. Keep this page open." above the grid; limit reached → pickers disabled + reason text under them; batch closed → pickers and drop zone replaced by `inline-alert--info` "Photo uploads are closed for now. If HAM needs more, we'll ask."; done → R10 with a `role="status"` success alert "Thank you. Your photos are with your request."
- **Focus order:** h1 → Take a photo → Choose → (tiles: each Retry/Remove) → Done. After Remove, focus moves to the next tile's Remove (or to Choose if none remain).

### R10. Secure request page
**Components:** eyebrow · "Hi {first name}" (`type-h3`, `text.secondary`) · h1 "Your request · HAM #047" · status card (C§26) · "Things we need from you (n)" `type-h2` + action cards (C§27) · "Your request" `type-h2` + `kv-list` + photo thumbnails + masked contact (C§25 variant 1) · "How to reach us" `type-h2` · footer lines (`type-body`, `text.secondary`).

- **390:** single column, sections `space-10` apart; photos as a 3-up tile grid without controls (tap opens the image full screen with a Close button). The first action card's button is the only primary; there's **no** sticky bar on R10 unless an action card exists, in which case at 200% text the bar mirrors that button (same rule as R7).
- **768:** same, centered at `size.form-max`.
- **≥1280:** `size.requester-wide-max`, two columns `3fr 2fr`: left = status, things we need, (schedule later); right = your request, how to reach us. Footer spans both.
- **Closed states:** status card neutral tone; the sentence per UX R10 table; "withdrew" adds **Ask for help again** (Secondary lg) inside the card.
- **Empty "Things we need from you":** the section is omitted entirely (not "Nothing needed"); the status card's "What happens next" carries the reassurance.
- **Loading:** skeleton status card + 3 skeleton lines. **Offline:** banner "You're offline. Showing what we had at 3:12 PM."; action buttons disabled with the reason.
- **Masked values:** C§25 variant 1; long masked emails wrap.
- **Focus:** h1 first stop after skip link; order = DOM (left column then right at ≥1280).

### R11a. Link expired · R11b. Check on your request · R12 other states
All use the **step-1 sign-in layout** (`public-card`, `size.form-max`, card at ≥1024, primary in the sticky bar at <768). Nothing new visually.
- **R11a:** `clock-alert` at `size.icon-xl` (`text.secondary`, decorative) → h1 "This link has expired" → body `type-body-lg` → "We'll send a code to **d•••@gmail.com**." → **Send me a code** (Primary lg) → Link "Different email? Check on your request". No-email variant: body + `tel:` link only, no primary, no bar.
- **R11b:** h1 "Check on your request" → Email field (`size.control-lg`) with typo suggestion → **Email me a link** (Primary). After submit, the same screen shape as step-1 "Check your email": h1 "Check your email", the neutral sentence, Link "Didn't get it? Call {church.hamPhone}". Rate-limited → `inline-alert--attention` with AA§A5 copy.
- **R12 not available / maintenance:** step-1 `not_found` shape inside the public shell: `circle-help` at `size.icon-xl`, h1 "We couldn't open this page", body, **Check on your request** (Secondary lg). Maintenance: same with the phone as a `tel:` link and no button.
- **R12 code limit, send failed, offline:** covered in R6/R8.

---

## 3. Leadership frame
- Signed-in `base.html` shell: app bar, bottom nav (<768; "Requests" tab for Director/AD/pastors/Board rep, N§3.1), rail (768–1023), sidebar (≥1024) with the **Requests (n)** count badge = actionable items for the viewer (Director/AD: phone checks; pastors/Board: awaiting approval).
- Page header (`.page-header`): h1 "Requests" left; no header action in step 2.
- Toasts (C§13) for results; inline alerts for errors; impersonation banner as in step 1.
- **Privacy guard in visuals:** list rows, Home cards, tabs, toasts and page titles contain only HAM # + category (Q-132). `<title>` for L2 is "HAM #047 · Requests · {church.shortName} HAM".

---

## 4. Leadership screens

### L1. Requests list (and L8 "Needs a phone check" tab)
**Components:** page header · view tabs with counts (C§29) · filter bar (P§3; search by request number, Category select, Status select on All) · request rows (C§28) / table (1024–1279) · empty states (C§12) · skeleton rows.

**390**
```
┌ app bar: logo · Requests ────────────┐
│ Requests                             │ h1
│ [Needs a phone check 1][Awaiting 4]›│ view tabs, scroll inside the row
│ [ 🔍 Request number ] [Filters · 1 ] │ search 1fr + Secondary md → bottom sheet
│ ┌──────────────────────────────────┐ │
│ │(Urgent) HAM #048 · Plumbing or   │ │ request rows, whole row a link
│ │ water                            │ │
│ │(⌛ Awaiting Approval) · 2 h       │ │ chip outline + age
│ ├──────────────────────────────────┤ │
│ │ HAM #047 · Roof or ceiling       │ │
│ │(⌛ Awaiting Approval) · 3 days    │ │
│ │ ⧉ Earlier request  ▢ 4 photos    │ │ markers
│ └──────────────────────────────────┘ │
├ bottom nav ──────────────────────────┤
```
- Rows sit in one `.card`-style list container (`bg.surface`, `radius-lg`, `border.default`), separators `border.subtle`.
- **768:** same rows full width in the content area beside the rail; filter bar inline (search, Category, Status).
- **1024–1279:** table (C§9): columns Request (Urgent chip + "HAM #047 · Roof or ceiling" link) · Status (chip outline) · Age (right-aligned, tabular) · Notes (markers). Row click opens L2 full page.
- **≥1280 split view** (P§2 v1.3): list pane (`size.split-list-min`; `size.split-list` at ≥1536) with tabs, compact filter bar (search full width, Category and Status as a second row) and request rows; detail pane = L2. The selected row uses the C§28 selected style. When nothing is selected (first visit), the detail pane shows the top row (urgent first) automatically, not an empty panel; on an empty list, the detail pane shows the tab's empty state centered.
- **Phone-check tab (L8):** same rows; line 2 is "Saved Oct 5 · waiting 1 day" instead of a status chip (it's still Submitted, but the useful fact is the wait); marker `phone-call` "Phone check needed" in `tone.attention.fg`. Urgent rows first.
- **Pastors/Board:** single tab "Awaiting approval" (still rendered as a tab row with its count, so step 3 can add "Decided" without a layout change). **Administrator:** tabs Awaiting approval · All; no markers for "Earlier request" (§9 limit).
- **States:** loading = 6 skeleton rows at row height; error = `inline-alert--danger` "Couldn't load requests." + **Try again** in the list area (tabs stay usable); offline = banner + cached rows + "As of 7:40 PM" (`type-small`, `text.tertiary`) under the tabs; empty per tab (UX L1 copy) as C§12 with `inbox` illustration; filtered-empty = compact empty with **Clear filters** Link.
- **Focus order:** h1 → tabs → search → filters → rows. At ≥1280, selecting a row (Enter) moves focus to the detail h1; Esc from the detail pane returns to the row.
- **Contrast/targets:** rows ≥ `size.list-row-min`; tab items `size.target-min`; count pills `text.secondary` on `bg.sunken` 6.35:1.

### L2. Request detail (full page <1280, detail pane at ≥1280)
**Components:** detail header (h1 + chips + meta) · banner by state (`inline-alert--info` / neutral) · L5 earlier-request alert · sections with `type-h2` (`type-h3` in the split pane) · hazard list · photo tiles (read-only) · `kv-list` · masked block (C§25) · status timeline (C§16) · actions (Primary / Secondary / overflow C§31).

**Header anatomy:** chips row (Urgent, status) → h1 "HAM #047 · Roof or ceiling" (`type-h1`; in the split pane `type-h2` visually but still the pane's h1 element) → meta lines (`type-small`, `text.secondary`, `space-1` apart): "Sent Oct 6, 9:14 AM · Public form" · "Email confirmed Oct 6 · Updates by email" (or `phone-call` "Phone check needed" in `tone.attention.fg`; or "Verified by phone call · Marcus B. · Oct 7").

**Section order** (UX L2): Earlier request alert → What's needed → Safety at the home → Photos → The home → Visits and contact preference → Requester & contact → History.
- **Safety at the home:** each hazard as a row with its R4 icon in `tone.attention.icon` + label (`type-label`) + the requester's words (`type-body`, quoted). "None that I know of" is plain `text.secondary` text with `shield-check`, no tone.
- **Photos:** tile grid (C§24, read-only, no strip unless processing), 3-up / 4-up / 5-up; opens a viewer (full-screen modal, `bg.inverse` backdrop, Close at `size.target-min`, arrows, "Photo 2 of 4" text).
- **The home:** tenant reminder as `inline-alert--info` compact "Landlord's written OK needed before work begins."
- **History:** C§16 timeline; certification entry "Agreed to intake statements v1 · Oct 6".

**390**
```
┌ app bar: ‹ back · HAM #047 ──────────┐ compact logo mark per C§1
│ (⌛ Awaiting Approval)                │
│ HAM #047 · Roof or ceiling           │ h1
│ Sent Oct 6, 9:14 AM · Public form    │ type-small
│ Email confirmed Oct 6 · Updates by   │
│ email                                │
│ ┌ ⓘ With the pastors and Board since ┐│ state banner
│ ┌ ⧉ Earlier request found (1) ──────┐│ L5 alert, info
│ ▾ What's needed                      │ collapsible h2 regions (details)
│ ▾ Safety at the home                 │ open by default
│ ▸ Photos (4)                         │
│ ▸ The home                           │
│ ▸ Visits and contact preference      │
│ ▸ Requester & contact 🔒             │
│ ▸ History                            │
│ [Ask for more photos]  [More ⋯]      │ Secondary md row, in flow
├──────────────────────────────────────┤
│ [       Record phone check         ] │ action bar only when a primary exists
├ bottom nav ──────────────────────────┤
```
- Collapsible regions are C§31 disclosures styled as section headers (`type-h3`, `size.choice-card-min` row, `border.subtle` between).
- **768:** same order, sections expanded (no collapsing), side facts as a `kv-list` card after the header.
- **1024–1279 (full page):** two columns per P§2: main (2fr: need, safety, photos, history) + side (1fr: key facts card, visits, masked contact, actions stacked full width). Primary action in the page header, right-aligned.
- **≥1280 split pane (1280–1535):** one column; header with actions right-aligned in the header row (Primary if any, then Secondary, then More); a **key facts strip** under the header: `kv-list` in 3 inline columns (Sent · Source · Contact / Updates). Sections in the order above. The pane scrolls independently.
- **≥1536 split pane:** main + side columns inside the pane (2fr / 1fr): side = key facts, visits, masked contact.

```
1280 · Director · split view
┌ sidebar ┬ list pane (split-list-min) ──┬ detail pane (region "HAM #047 details") ──────────────┐
│         │ Requests                      │ (⌛ Awaiting Approval)                                  │
│         │ [Phone check 1][Awaiting 4]   │ HAM #047 · Roof or ceiling   [Ask for more photos][More⋯]│
│         │ [🔍 Request number]           │ Sent Oct 6, 9:14 AM │ Public form │ Email confirmed · by email│
│         │ [Category ▾] [Status ▾]       │ ⓘ With the pastors and Board since Oct 6.                │
│         │ (Urgent) HAM #048 · Plumbing  │ ⧉ Earlier request found (1). This doesn't rule anything │
│         │  Awaiting Approval · 2 h      │   out. Each request is looked at on its own.   [View]  │
│         │▌HAM #047 · Roof or ceiling    │ What's needed                                          │
│         │  Awaiting Approval · 3 days   │ "Water comes through my bedroom ceiling …"             │
│         │  ⧉ Earlier request ▢ 4 photos │ Safety at the home                                     │
│         │ HAM #046 · Electrical         │ ⚠ Dogs or other animals — "friendly but loud"          │
│         │  Awaiting Approval · 4 days   │ Photos (4)  [▢][▢][▢][▢]                               │
│         │ HAM #044 · Yard or outside    │ The home · Visits · Requester & contact [Show contact…] │
│         │  ☎ Updates by phone           │ History (timeline)                                     │
└─────────┴───────────────────────────────┴────────────────────────────────────────────────────────┘
```
- **Actions by role:** Director/AD: Primary **Record phone check** only in the phone-check state; Secondary **Ask for more photos**; More ⋯ → **Change category** · **Close request…**. Pastors/Board: **Ask for more photos** only. Administrator: no actions, no L5, masked block variant 4, photos shown as a count "4 photos · not shown to the Administrator role" (G6 proposed; `image-off` icon).
- **Change category:** inline — the category text in the header becomes a native select + **Save** (Primary sm) + **Cancel** (Ghost sm) in place; toast "Category changed · 8:02 PM".
- **Cancelled:** state banner `inline-alert--neutral` (new modifier: `tone.neutral.bg`, `tone.neutral.fg`, `tone.neutral.border`, `ban` icon): "Closed Oct 8 · The requester asked us to withdraw it · Marcus B."; no actions.
- **States:** loading = skeleton header + 3 skeleton sections; section error = inline alert inside the section with Try again; not available = neutral N§6 screen (no title); impersonating = actions that are blocked show their reason line (`type-small`, `text.secondary`, `lock`) in place of the button.
- **Focus order:** h1 → header actions → banner → L5 View → sections in order (Show contact details inside Requester & contact) → History.

### L5. Earlier requests (alert + panel)
- **Alert:** `inline-alert--info` with `copy` icon, title "Earlier request found (1)" (`type-label`), body per UX, action **View** (Link button, `size.target-min`) that expands the panel in place (a disclosure, not a new page). Never danger/attention tone.
- **Panel:** list of match cards (`bg.surface`, `border.default`, `radius-md`, padding `space-4`, gap `space-3`): line 1 "HAM #031 · Roof or ceiling · sent Mar 2, 2025" (`type-label`); line 2 reason chips (`chip--tag` style, `bg.sunken`, `text.secondary`, with icons: `map-pin` Same address · `phone` Same phone · `mail` Same email · `id-card` Same name and ZIP); line 3 outcome: status chip + reason text (`type-small`); **Open** Link (opens that request; in the split view it replaces the detail pane and adds a "‹ Back to HAM #047" Link at the pane top).
- **Close this one as a duplicate…** (Director/AD): Secondary md at the panel's end → L10 with preselection.
- No scores, no percentages, no dismiss.

### L9. Record a phone check (sheet, Director/AD)
**Components:** sheet medium (C§32, `size.modal-md`) / full-screen sheet <768 · lock note · revealed contact (C§25 variant 3) · Secondary lg **Call** (`phone`, `tel:`) · Disclosure "What to say" · statement choice card · "What happens next" text · Primary **Verified by phone call** · two Links · footnote.
- **Order and rhythm:** h2 "Record a phone check · HAM #050" → intro `type-body` → lock note (`type-small`) → name + phone `type-h3` → contact note in a `bg.sunken` quote block → **Call (305) 555-0177** (Secondary lg, full width <768) → Disclosure "What to say" (script in `type-body`, `bg.sunken` block) → statement card "I spoke with Ruth Hall by phone, and she confirmed she asked for this help." → "What happens next" `type-label` + one sentence → Primary → `space-4` → Links "They didn't ask for this ›", "They no longer need help ›" (`size.target-min` rows) → footnote `type-small` `text.secondary`.
- **390:** full-screen sheet; Call and the statement card fit in the first screen at normal text; **Verified by phone call** in the action bar. **≥768:** centered modal, footer: Ghost **Cancel** left, Primary right.
- **States:** submitting → Primary loading; success → sheet closes, toast "Verified by phone call · 7:52 PM", L2 re-renders with the Awaiting Approval chip and focus on the h1; the list row leaves the phone-check tab (with a `duration-base` fade); unticked on submit → error on the statement card; impersonating → Primary replaced by the reason line; error → `inline-alert--danger` inside the sheet above the footer.
- **Contrast:** the sheet body is `bg.surface-raised`; quote blocks `bg.sunken` with `text.primary` 15.85:1.

### L10. Close request (sheet small)
- h2 "Close HAM #049" → legend "Why are you closing HAM #049?" (`type-label`) + helper (`type-small`) → 3 radio choice cards (C§19, app size, 1 column) → Note (optional) textarea 3 rows with hint → **consequence box**: `bg.sunken`, `radius-md`, padding `space-4`, `info` icon: "HAM #049 will be closed. Doris will get a short, kind email." / "No email will be sent." + "This can't be undone." (`type-label`) → footer Ghost **Cancel** · **Close request** (Danger variant: it's destructive and final; the only Danger button in intake).
- Preselection from L5/L9 shows the chosen card selected and the note prefilled; focus goes to the sheet heading, not the radio.
- Result: toast "HAM #049 closed · 7:58 PM"; the detail re-renders Cancelled.

### L11. Ask for more photos (sheet small)
- h2 "Ask for more photos" → field "What would help us?" (label `type-label`, hint `type-small`, textarea 3 rows) → consequence line (`type-small`, `text.secondary`) → footer Ghost **Cancel** · Primary **Ask for photos**.
- No-email request: the **Ask for more photos** trigger on L2 is shown disabled with the reason text beside/below it ("Ruth doesn't use email. We'll take photos at the visit.", `type-small`, `text.secondary`), never a tooltip-only reason.

### L7 and Home cards (Home attention, N§8.3 group 4)
- **Director/AD Home:** attention card (C§27) in group "Requests & assessments": `phone-call` icon, "1 request needs a phone check" + context "oldest waiting 1 day" + **Open** (Secondary). Urgent variant pinned first in the group: Urgent chip + "HAM #050 needs a phone check before pastors can see it" + "waiting 3 h" + **Call now** (Primary sm; opens L2 with L9 open). Awaiting-approval rows for the Director are **awareness** variant (muted, uncounted).
- **Pastor/Board Home (Decisions):** urgent requests as their own attention cards ("Urgent · HAM #048 Plumbing or water · waiting 2 h" + **Review**), then one card "2 requests are waiting for a decision" + **Open** → L1 Awaiting approval.
- **App-wide urgent banner (G1, Director/AD):** page banner (C§11) `tone.danger`, `siren` icon, "Urgent request HAM #050 needs a phone check." + Link "Open"; not dismissible until handled; sits under the app bar, above the impersonation banner if both.
- Layout: Home uses the existing `.home-grid` (2fr / 1fr at ≥1280); intake cards live in the left column group list.

---

## 5. Emails (visual)
- Single column at the email builder's standard email width (a named constant in the email builder, not a design token), `bg.surface` on `bg.canvas`, brand `logos.onLight` at `size.logo-min-height` top-left, "Home Assistance Ministry" `type-label` beside it.
- Heading uses the `type-h2` values and body the `type-body-lg` values, inlined by the email builder from `tokens.css` (web fonts fall back to the system sans; never the display face in email). One button: `action.primary.bg` fill, `text.on-primary`, `radius-md`, `size.target-min` tall, full width on mobile clients.
- E1 code: the code on its own line in the `type-code-entry` values (tabular, letter-spaced), then **Confirm my email** button.
- Footer `type-small` values, `text.secondary`: church name, ministry phone and email. No images other than the logo; `alt` from the brand. Plain-text part always included.
- Colors are inlined hex resolved from `tokens.css` at render time by the email builder (never typed by hand in templates).

---

## 6. Frontend checklist (ham-frontend-engineer)
- [ ] Pull `design-system/tokens.css` v1.3 (`make tokens`); drop the fallbacks in `shell.css` for `--ham-size-chip`, `--ham-size-empty-max`, `--ham-size-modal-sm`.
- [ ] Add classes per C§19–§32: `.choice-card` (+ `--exclusive`, `--statement`), `.choice-grid`, `.choice-chip`, `.code-input`, `.step-header`, `.step-list`, `.action-bar`, `.summary-card`, `.dropzone`, `.upload-tile`, `.upload-summary`, `.masked-block` (4 variants), `.status-card`, `.action-card`, `.attention-card`, `.request-row`, `.marker`, `.view-tabs`, `.error-summary`, `.disclosure`, `.inline-alert--neutral`; modifiers `public-shell__content--wizard`, `.sheet--md`, `.sheet--fullscreen`.
- [ ] Container queries for every grid (choice cards, upload tiles, review cards, R3 City/ZIP, action bar Back placement). Use `em` thresholds from this doc.
- [ ] `overflow-wrap: anywhere` on email, address, file-name and masked values; `min-width: 0` on grid/flex children.
- [ ] Sticky action bar per C§22, including the 200%-text Back relocation, the `breakpoint.short` height unstick, `scroll-padding-bottom`, and one primary in the DOM at a time (R7/R10 mirror rule).
- [ ] Requester pages: labels `type-h3`, inputs `type-body-lg` at `size.control-lg`, helpers `type-body`, `ss02` on.
- [ ] Split view at ≥1280 using `size.split-list-min` / `size.split-list`; detail pane is a labelled region; Enter/Esc focus rules.
- [ ] Focus management: step h1 on step change, error summary on submit error, R7/R7N h1 on load, sheet heading on open, trigger on close, revealed heading after "Show contact details".
- [ ] Live regions: "Your answers are saved" once; offline save once; exclusive-card clears; upload summary; resend available; toast.
- [ ] Icons (Lucide) exactly as named in R2, R3, R4, R5, L5.
- [ ] No text over photos; video duration pill on `bg.inverse`.
- [ ] Reduced motion: no step rise, no chevron rotation, no row fade.

## 7. Visual QA plan (ui-designer, once built)
Capture at 390×844, 768×1024, 1280×800 and 1440×900 (light only, Q-016), plus **390×844 with 200% text** and **200% page zoom** for every R screen, into `docs/ux/screenshots/step2/`:
R1 (+ resume) · R2 (+ urgent open, + error summary) · R3 (owner, family, tenant) · R4 (+ None exclusive) · R5 (+ I don't use email, + typo suggestion) · R6 (+ missing ticks, + no-email) · R8 (+ wrong code, expired, daily limit) · R7 (normal, urgent) · R7N · R9 (uploading, failed, offline, limit) · R10 (being reviewed, closed ×3) · R11a (email, no email) · R11b (form, sent) · R12.
L1 (Director default phone-check tab, Awaiting, All, empty, filtered-empty, loading, error) · L2 (Director phone-check state, Awaiting, Cancelled, AD revealed, Administrator) · L5 open · L9 (Director, AD, impersonating) · L10 · L11 (+ disabled no-email) · Home cards (Director urgent + normal, Pastor).
Checks: no horizontal scroll (`document.documentElement.scrollWidth <= innerWidth`), primary visible without scrolling in the bar, axe-core clean, focus order walk-through, contrast spot-checks on chips and banners.
