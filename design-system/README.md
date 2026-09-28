# HAM Design System

Version 1.3.0 · Build-order step 0 (+ step 2 intake additions) · Owner: ham-ui-designer
HAM should feel like a well-made consumer app, warm and trustworthy, not like church admin software. For Miami Temple Seventh-day Adventist Church it looks like part of the church: the logo's three greens, a heavy condensed heading face that echoes the wordmark, and calm neutrals.

## Two layers: HAM core + church brand

V1 serves one church (PRD header, §74, §75). Other churches will adopt HAM later, each running its own copy with its own logo and look (Q-026, decided). So the design system has two layers, and **changing church means changing configuration, never code**:

| Layer | Where | What it holds | Who may change it |
|---|---|---|---|
| **HAM core** | `tokens.json` | Neutrals, semantic colors (danger, attention, success, info, AI), every status tone/label/icon, type scale, spacing, radius, elevation, motion, breakpoints, contrast rules, the brand policy (approved fonts, contrast target) | HAM design owner only. Identical for every church, so safety and status meaning never changes. |
| **Church brand** | `brands/<brand>/brand.json` + logo files | Church name, short name, mission line, one primary color seed + up to two accents, display and UI font (approved list), three logo versions | Each church. See `brands/README.md`. |

`tools/build_tokens.py --brand <brand>` (default `miami-temple`) combines them into `tokens.css`. From the brand's seed color it derives an 11-step scale and **picks the button and link shades automatically** so they pass WCAG AA, writes its reasoning into the "Active brand" section below, runs the full contrast check, and stops with a plain-language error if a brand can't reach AA. There is no multi-tenant data model: one deployment, one brand.

In `tokens.json`, brand slots are empty placeholders (`primitive.color.brand`, `primitive.color.accent`, `font.family.display` / `ui` marked `ham.fromBrand`) and semantic tokens point at **brand roles** (`{brand.action}`, `{brand.link}`…), which the build maps to the picked steps. Components only ever see the usual semantic variables.

## Decided for V1
- **Light theme only (Q-016).** Dark values stay in `tokens.json` for later and apply only with `data-theme="dark"` on `<html>`; automatic OS dark mode is off (`ham.autoDark: false`). The mockup theme toggles are for design review only.
- **Public scoreboard embed (Q-005).** The member scoreboard may also be embedded on the church website: aggregates only, the church's logo and name from the brand layer, no names, and no number small enough to identify a family. Pattern: `patterns.md` §6.
- **Church branding is configuration (Q-026).** See "Two layers" above.

| File | What it is |
|---|---|
| `tokens.json` | **HAM core, source of truth.** Primitives, semantic aliases (light `$value` plus dark in `$extensions["ham.modes"].dark`), every status with its label, tone and icon, and the brand policy. |
| `brands/<brand>/` | **Church brand layer**: `brand.json` + logo files. `brands/README.md` explains how to add a church. |
| `tokens.css` | Generated CSS custom properties for the active brand: `:root` is light; dark values sit under `[data-theme="dark"]`. Do not edit by hand. |
| `components.md` | Visual spec for each V1 core component: anatomy, variants, states, a11y, do/don't. |
| `patterns.md` | Navigation shell, list→detail, cards vs tables, forms, wizards, dashboards (incl. public scoreboard embed), timelines, photo upload, theming. |
| `tools/build_tokens.py` | Builds `tokens.css` for a brand, refreshes the generated tables in this README, and fails (`--check`) if a required contrast pair drops below AA. |

## How to use

1. Load the brand's fonts and the tokens once in the app shell. For Miami Temple (Oswald + Inter):
   ```html
   <link rel="preconnect" href="https://fonts.googleapis.com">
   <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
   <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..700&family=Oswald:wght@500..700&display=swap" rel="stylesheet">
   <link rel="stylesheet" href="/design-system/tokens.css">
   ```
   Because HAM is a PWA that should work offline, the frontend should **self-host** the brand's fonts (each approved font lists its `@fontsource-variable/*` package in `tokens.json` → `ham.brandPolicy.fonts`) when the stack is chosen (Q-003). Read the font names from `brand.json`; don't hard-code them. The Google Fonts link above is for prototypes.
2. Base styles: `body { background: var(--ham-bg-canvas); color: var(--ham-text-primary); font: var(--ham-type-body-weight) var(--ham-type-body-size)/var(--ham-type-body-line-height) var(--ham-font-ui); }`.
3. Use **semantic** variables in components (`--ham-text-secondary`, `--ham-action-primary-bg`, `--ham-status-task-blocked-bg`). Use primitives (`--ham-color-brand-600`) only inside the token files. Church name, mission line, logo files and logo alt text come from the active `brand.json`, never from literals in components.
4. **V1 ships light only (Q-016).** Never set `data-theme="dark"` in the product.
5. To change a core token, edit `tokens.json`; to change a church's look, edit its `brand.json`. Then run `python3 design-system/tools/build_tokens.py --brand miami-temple --check` and commit `tokens.json` / `brand.json`, `tokens.css` and this README.

**Naming:** `--ham-color-*` = primitive color (`brand-*` and `accent-*` come from the brand; `green-*` is HAM's fixed status green) · `--ham-{bg|text|border|action|focus|accent|tone|appbar|badge}-*` = semantic color · `--ham-type-{style}-{family|weight|size|line-height|tracking}` · `--ham-space-*` (4px grid; `space-4` = 16px) · `--ham-radius-*` · `--ham-size-*` · `--ham-shadow-*` · `--ham-duration-*` / `--ham-easing-*` · `--ham-z-*` · `--ham-status-{group}-{status}-{bg|fg|border|icon}`.

## Color decisions

### Active brand (generated)

<!-- brand:start -->
Built for **Miami Temple Seventh-day Adventist Church** (`brands/miami-temple/`). Seed `#0B9444`; display font Oswald, UI font Inter.

| Step | 50 | 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 | 900 | 950 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Hex | `#ECF7ED` | `#D3EDD7` | `#A9DCB2` | `#76C587` | `#40AD60` | `#0B9444` | `#0A7F3A` | `#0A6B30` | `#0B5626` | `#09421D` | `#132E19` |
| Light role | selected-bg |  |  |  |  |  | action | action-hover, link | action-pressed, link-hover |  |  |
| Dark role |  |  | action-pressed, link-hover | action-hover, link | action |  |  |  |  |  | selected-bg |

Why these steps (written by the build):

- Button (light): step 600 #0A7F3A. White text on it is 5.11:1. It is the step closest to the seed that reaches 4.7:1 (checked: 500 #0B9444 gives 3.94:1; 600 #0A7F3A gives 5.11:1). Hover = 700, pressed = 800.
- Links, brand text, outline-button text and focus ring (light): step 700 #0A6B30. It is at least one step deeper than the button fill (text strokes are thinner than a filled button, so they get extra margin) and its weakest pair is 5.85:1 on `bg.sunken`. Hover = 800.
- Dark theme (kept for later, Q-016): button step 400 #40AD60 with ink text 6.32:1; links step 300 #76C587 (weakest 7.06:1 on `bg.selected`).
- Accent stripe (decorative only): light `#8CC63F`, mid `#39B54A`, dark `#0B9444`.
<!-- brand:end -->

### Brand layer (Miami Temple)
- **The seed is the logo's dark leaf (#0B9444).** Against white it reaches only 3.94:1: fine for big display text and graphics, too low for normal text or white button text. The build therefore picks step 600 for the button fill (white text 5.11:1, still reads as "the logo green") and step 700 for links and brand text. These are the same steps the hand-tuned v1.1 palette used; the computed values differ from it by at most a few RGB units, which is invisible.
- **The light green (#8CC63F) and mid green (#39B54A) are accents only** (`accent.brand-light`, `accent.brand-mid`). They appear in the 3px stripe under the app bar, in illustrations and on hero KPI tiles. They are never used for text on white (2.05:1 and 2.66:1) and never carry meaning.

### HAM core (every church)
- **Neutrals** are slightly green-tinted grays built from ink #111814, which is also the required wordmark color of every church's dark-on-light logo. The tint is too slight to clash with other brand colors.
- **Status colors never come from the brand.** The "active" tone (Ready, Scheduled, In Progress) uses HAM's own fixed green (`primitive.color.green`). For Miami Temple it happens to match the brand; for another church, a blue or purple button sits next to the same green "In Progress" chip as everywhere else.
- **"Success" is teal (#0E7C74 / #0B5E58), not green, on purpose.** Green means "act here" (Miami Temple's buttons) and "work under way" (the active tone). If "done" were the same green, a finished task would look like a button, and a volunteer couldn't tell *In Progress* from *Completed* at a glance. Teal still reads as positive. Every success state also carries a check icon, and every chip has a text label, so no one depends on the hue (including people with red-green color blindness).
- **Seven tones cover every state.** Statuses don't each get their own color; each one maps to a tone, and its icon tells it apart. The tones are **neutral** (not started / closed), **info** (moving along, nothing needed from you), **attention** (waiting on a person, amber), **active** (on track or happening now, HAM green), **success** (done or verified, teal), **danger** (blocked, unsafe, expired, red) and **ai** (suggestions only, violet, never a status).
- **A brand color may not be danger red.** The build refuses a primary seed within 25° of hue of the danger red, because a red main button would blur "go ahead" and "stop". Red can still be a decorative accent.
- **The app bar is dark ink in both themes**, so every church shows its white-on-dark logo exactly as issued.

## Typography

The display and UI faces are brand choices from the approved list (`brands/README.md`); the scale below is HAM core and the same for every church. Miami Temple's choices:

| Role | Font | Why |
|---|---|---|
| Display (screen titles `h1`, KPI numbers, requester page hero) | **Oswald** 600 | A heavy condensed sans that echoes the "MIAMI TEMPLE" wordmark. It is free, variable, and includes **Cyrillic** and Latin Extended, which matters because the church site already offers Spanish and Russian. Barlow Condensed has no Cyrillic, so it was ruled out. |
| UI (everything else) | **Inter** (variable, `opsz`) | Very large x-height and open shapes help older requesters and people reading outdoors in sunlight. It has tabular figures for tables and budgets, covers Latin Extended, Cyrillic, Greek and Vietnamese, and is one of the most-tested UI faces. Atkinson Hyperlegible was a strong option, but it lacks Cyrillic and tabular figures. Where the platform supports it, turn on Inter's disambiguation set (`font-feature-settings: "ss02"`) on requester pages and for license numbers, so I/l/1 and 0/O look different. |

Scale (from the `--ham-type-*` tokens): display 40/48 · h1 32/40 · h2 22/30 · h3 18/26 · body-lg 18/28 · **body 16/24 (minimum for body text)** · label 16/24 semibold · small 14/20 (metadata only) · chip 14/20 semibold · kpi 40/44 · nav-compact 12/16 (bottom-nav labels only, always paired with an icon).

- The display face (Oswald for Miami Temple) is for sparse use only. Never set body text, form labels, buttons or long headings in it, and never set whole paragraphs in capitals.
- Sentence case everywhere.
- **Room for translation (~30% longer):** no fixed-width buttons, chips or nav items. Labels wrap rather than truncate, and only record titles may ellipsize (the full title is always repeated on the page). The condensed display face also buys horizontal room for longer headings.

## Status catalog

Labels use the exact PRD names wherever the PRD provides them. Names the PRD doesn't define are proposals: invitation and commitment names are Q-017, and credential verification values are Q-018. Two groups are **not statuses**. *Excused* is a flag with a reason on a cancellation or no-show (Q-022). *Expiring Soon* and *Expired* are badges computed from the credential's expiration date (Q-018). Check-in and check-out are timestamps, not statuses (§37.2). Project **On Hold** is always red; the reason line (for example, "Safety hold · mold") tells safety holds from other holds. This table is generated from `tokens.json`.

<!-- status:start -->
| Group (PRD) | Status label | Tone | Icon | CSS prefix |
|---|---|---|---|---|
| **project** · PRD §52 | Submitted | info | `inbox` | `--ham-status-project-submitted-*` |
|  | Awaiting Approval | attention | `hourglass` | `--ham-status-project-awaiting-approval-*` |
|  | Approved | info | `badge-check` | `--ham-status-project-approved-*` |
|  | Assessment Required | attention | `clipboard-list` | `--ham-status-project-assessment-required-*` |
|  | Assessment Completed | info | `clipboard-check` | `--ham-status-project-assessment-completed-*` |
|  | Planning | info | `pencil-ruler` | `--ham-status-project-planning-*` |
|  | Recruiting | info | `users` | `--ham-status-project-recruiting-*` |
|  | Ready | active | `circle-check` | `--ham-status-project-ready-*` |
|  | Scheduled | active | `calendar-check` | `--ham-status-project-scheduled-*` |
|  | In Progress | active | `hammer` | `--ham-status-project-in-progress-*` |
|  | Completed – Follow-Up Required | attention | `flag` | `--ham-status-project-completed-follow-up-required-*` |
|  | Completed | success | `circle-check-big` | `--ham-status-project-completed-*` |
|  | Rejected | neutral | `circle-x` | `--ham-status-project-rejected-*` |
|  | Reconsideration Pending | attention | `rotate-ccw` | `--ham-status-project-reconsideration-pending-*` |
|  | On Hold | danger | `octagon-pause` | `--ham-status-project-on-hold-*` |
|  | Cancelled | neutral | `ban` | `--ham-status-project-cancelled-*` |
|  | Not Executable | neutral | `circle-slash` | `--ham-status-project-not-executable-*` |
| **task** · PRD §15.5 | Planned | neutral | `circle-dashed` | `--ham-status-task-planned-*` |
|  | Ready | info | `circle` | `--ham-status-task-ready-*` |
|  | Assigned | info | `user-check` | `--ham-status-task-assigned-*` |
|  | In Progress | active | `hammer` | `--ham-status-task-in-progress-*` |
|  | Blocked | danger | `octagon-alert` | `--ham-status-task-blocked-*` |
|  | Completed | success | `circle-check-big` | `--ham-status-task-completed-*` |
|  | Cancelled | neutral | `ban` | `--ham-status-task-cancelled-*` |
| **invitation** · PRD §28 (names PRD-GAP Q-017) | Invited | attention | `mail` | `--ham-status-invitation-invited-*` |
|  | Accepted | success | `circle-check-big` | `--ham-status-invitation-accepted-*` |
|  | Declined | neutral | `circle-x` | `--ham-status-invitation-declined-*` |
|  | No Response | neutral | `clock-alert` | `--ham-status-invitation-no-response-*` |
| **commitment** · PRD §29, §32, §33 (names PRD-GAP Q-017 except Pending Confirmation) | Waitlisted | info | `list-ordered` | `--ham-status-commitment-waitlisted-*` |
|  | Pending Confirmation | attention | `hourglass` | `--ham-status-commitment-pending-confirmation-*` |
|  | Confirmed | success | `circle-check-big` | `--ham-status-commitment-confirmed-*` |
|  | Reconfirmation Needed | attention | `calendar-clock` | `--ham-status-commitment-reconfirmation-needed-*` |
|  | Released | neutral | `log-out` | `--ham-status-commitment-released-*` |
|  | Cancelled | neutral | `ban` | `--ham-status-commitment-cancelled-*` |
|  | No-Show | danger | `user-x` | `--ham-status-commitment-no-show-*` |
| **commitment-flag** · PRD §33 — a flag + reason on a cancellation/no-show, NOT a status (PRD-GAP Q-022) | Excused | neutral | `shield-check` | `--ham-status-commitment-flag-excused-*` |
| **attendance** · PRD §37.2 (check-in/check-out are timestamps, not statuses) | Present | success | `circle-check-big` | `--ham-status-attendance-present-*` |
|  | Late | attention | `clock-alert` | `--ham-status-attendance-late-*` |
|  | Absent | danger | `user-x` | `--ham-status-attendance-absent-*` |
| **credential** · PRD §24 verification status (values PRD-GAP Q-018) | Unverified | attention | `shield-question` | `--ham-status-credential-unverified-*` |
|  | Verified | success | `shield-check` | `--ham-status-credential-verified-*` |
|  | Could Not Verify | danger | `shield-alert` | `--ham-status-credential-could-not-verify-*` |
| **credential-expiry** · PRD §24.1 — computed from the expiration date; badges, NOT statuses (PRD-GAP Q-018) | Expiring Soon | attention | `calendar-clock` | `--ham-status-credential-expiry-expiring-soon-*` |
|  | Expired | danger | `shield-x` | `--ham-status-credential-expiry-expired-*` |
| **priority** · PRD §10, §52 (attribute, not a status) | Urgent | danger | `siren` | `--ham-status-priority-urgent-*` |
<!-- status:end -->

## Contrast table (computed)

WCAG 2.x relative-luminance ratios for every text and background pair the system defines, in both themes. Text must reach 4.5:1 and UI components/icons 3:1 (WCAG 2.2 AA). This table is generated by `tools/build_tokens.py`. **All required pairs pass** (the build fails otherwise). The "Info" rows are listed to show why those colors are restricted.

<!-- contrast:start -->
| Pair (foreground on background) | Use | Min | Light | Dark | Result |
|---|---|---|---|---|---|
| `text.primary` on `bg.canvas` | text | 4.5:1 | 16.90 | 16.88 | Pass |
| `text.primary` on `bg.surface` | text | 4.5:1 | 18.03 | 15.09 | Pass |
| `text.primary` on `bg.surface-raised` | text | 4.5:1 | 18.03 | 13.63 | Pass |
| `text.primary` on `bg.sunken` | text | 4.5:1 | 15.85 | 15.85 | Pass |
| `text.secondary` on `bg.canvas` | text | 4.5:1 | 6.77 | 10.26 | Pass |
| `text.secondary` on `bg.surface` | text | 4.5:1 | 7.22 | 9.18 | Pass |
| `text.secondary` on `bg.surface-raised` | text | 4.5:1 | 7.22 | 8.29 | Pass |
| `text.secondary` on `bg.sunken` | text | 4.5:1 | 6.35 | 9.64 | Pass |
| `text.tertiary` on `bg.canvas` | text | 4.5:1 | 5.30 | 7.34 | Pass |
| `text.tertiary` on `bg.surface` | text | 4.5:1 | 5.65 | 6.56 | Pass |
| `text.tertiary` on `bg.surface-raised` | text | 4.5:1 | 5.65 | 5.93 | Pass |
| `text.tertiary` on `bg.sunken` | text | 4.5:1 | 4.97 | 6.89 | Pass |
| `text.link` on `bg.canvas` | text | 4.5:1 | 6.23 | 9.24 | Pass |
| `text.link` on `bg.surface` | text | 4.5:1 | 6.65 | 8.26 | Pass |
| `text.link` on `bg.surface-raised` | text | 4.5:1 | 6.65 | 7.46 | Pass |
| `text.link` on `bg.sunken` | text | 4.5:1 | 5.85 | 8.68 | Pass |
| `text.primary` on `bg.selected` | text | 4.5:1 | 16.40 | 12.89 | Pass |
| `text.primary` on `bg.hover` | text | 4.5:1 | 15.85 | 13.63 | Pass |
| `text.brand` on `bg.selected` | text | 4.5:1 | 6.04 | 7.06 | Pass |
| `text.link` on `bg.hover` | text | 4.5:1 | 5.85 | 7.46 | Pass |
| `text.on-primary` on `action.primary.bg` | text | 4.5:1 | 5.11 | 6.32 | Pass |
| `text.on-primary` on `action.primary.bg-hover` | text | 4.5:1 | 6.65 | 8.68 | Pass |
| `text.on-primary` on `action.primary.bg-pressed` | text | 4.5:1 | 8.85 | 11.65 | Pass |
| `text.on-danger` on `action.danger.bg` | text | 4.5:1 | 6.57 | 4.73 | Pass |
| `text.on-danger` on `action.danger.bg-hover` | text | 4.5:1 | 7.78 | 5.73 | Pass |
| `action.secondary.fg` on `action.secondary.bg` | text | 4.5:1 | 6.65 | 8.26 | Pass |
| `action.secondary.fg` on `action.secondary.bg-hover` | text | 4.5:1 | 6.04 | 7.06 | Pass |
| `text.on-appbar` on `bg.appbar` | text | 4.5:1 | 18.03 | 18.03 | Pass |
| `text.on-inverse` on `bg.inverse` | text | 4.5:1 | 18.03 | 14.54 | Pass |
| `appbar.text-muted` on `bg.appbar` | text | 4.5:1 | 9.64 | 9.64 | Pass |
| `appbar.text-muted` on `appbar.field-bg` | text | 4.5:1 | 7.56 | 7.56 | Pass |
| `text.on-appbar` on `appbar.field-bg` | text | 4.5:1 | 14.14 | 14.14 | Pass |
| `badge.fg` on `badge.bg` | text | 4.5:1 | 6.57 | 6.57 | Pass |
| `text.secondary` on `bg.selected` | text | 4.5:1 | 6.57 | 7.84 | Pass |
| `action.primary.bg` on `bg.canvas` | UI | 3.0:1 | 4.79 | 6.73 | Pass |
| `action.primary.bg` on `bg.surface` | UI | 3.0:1 | 5.11 | 6.02 | Pass |
| `action.danger.bg` on `bg.surface` | UI | 3.0:1 | 6.57 | 3.63 | Pass |
| `action.secondary.border` on `bg.surface` | UI | 3.0:1 | 5.11 | 6.02 | Pass |
| `border.strong` on `bg.surface` | UI | 3.0:1 | 3.69 | 4.65 | Pass |
| `border.strong` on `bg.canvas` | UI | 3.0:1 | 3.46 | 5.20 | Pass |
| `border.selected` on `bg.surface` | UI | 3.0:1 | 5.11 | 6.02 | Pass |
| `focus.ring` on `bg.canvas` | UI | 3.0:1 | 6.23 | 9.24 | Pass |
| `focus.ring` on `bg.surface` | UI | 3.0:1 | 6.65 | 8.26 | Pass |
| `appbar.status-ok` on `bg.appbar` | UI | 3.0:1 | 11.42 | 11.42 | Pass |
| `appbar.field-border` on `bg.appbar` | UI | 3.0:1 | 4.89 | 4.89 | Pass |
| `border.selected` on `bg.selected` | UI | 3.0:1 | 4.65 | 5.14 | Pass |
| `focus.ring` on `bg.selected` | UI | 3.0:1 | 6.04 | 7.06 | Pass |
| `action.primary.bg` on `bg.sunken` | UI | 3.0:1 | 4.49 | 6.32 | Pass |
| `border.strong` on `bg.sunken` | UI | 3.0:1 | 3.24 | 4.89 | Pass |
| `tone.neutral.fg` on `tone.neutral.bg` | chip text | 4.5:1 | 8.90 | 9.94 | Pass |
| `tone.neutral.fg` on `bg.surface` | text on card | 4.5:1 | 10.12 | 12.06 | Pass |
| `tone.neutral.icon` on `tone.neutral.bg` | chip icon | 3.0:1 | 6.35 | 7.56 | Pass |
| `tone.neutral.icon` on `bg.surface` | icon on card | 3.0:1 | 7.22 | 9.18 | Pass |
| `tone.info.fg` on `tone.info.bg` | chip text | 4.5:1 | 7.14 | 9.79 | Pass |
| `tone.info.fg` on `bg.surface` | text on card | 4.5:1 | 8.14 | 10.73 | Pass |
| `tone.info.icon` on `tone.info.bg` | chip icon | 3.0:1 | 5.28 | 9.79 | Pass |
| `tone.info.icon` on `bg.surface` | icon on card | 3.0:1 | 6.02 | 10.73 | Pass |
| `tone.attention.fg` on `tone.attention.bg` | chip text | 4.5:1 | 6.22 | 9.96 | Pass |
| `tone.attention.fg` on `bg.surface` | text on card | 4.5:1 | 6.80 | 11.48 | Pass |
| `tone.attention.icon` on `tone.attention.bg` | chip icon | 3.0:1 | 4.22 | 9.96 | Pass |
| `tone.attention.icon` on `bg.surface` | icon on card | 3.0:1 | 4.61 | 11.48 | Pass |
| `tone.active.fg` on `tone.active.bg` | chip text | 4.5:1 | 8.04 | 9.52 | Pass |
| `tone.active.fg` on `bg.surface` | text on card | 4.5:1 | 8.87 | 11.11 | Pass |
| `tone.active.icon` on `tone.active.bg` | chip icon | 3.0:1 | 4.64 | 7.08 | Pass |
| `tone.active.icon` on `bg.surface` | icon on card | 3.0:1 | 5.11 | 8.26 | Pass |
| `tone.success.fg` on `tone.success.bg` | chip text | 4.5:1 | 6.67 | 9.21 | Pass |
| `tone.success.fg` on `bg.surface` | text on card | 4.5:1 | 7.62 | 10.87 | Pass |
| `tone.success.icon` on `tone.success.bg` | chip icon | 3.0:1 | 4.43 | 9.21 | Pass |
| `tone.success.icon` on `bg.surface` | icon on card | 3.0:1 | 5.06 | 10.87 | Pass |
| `tone.danger.fg` on `tone.danger.bg` | chip text | 4.5:1 | 6.80 | 8.75 | Pass |
| `tone.danger.fg` on `bg.surface` | text on card | 4.5:1 | 7.78 | 9.26 | Pass |
| `tone.danger.icon` on `tone.danger.bg` | chip icon | 3.0:1 | 5.01 | 8.75 | Pass |
| `tone.danger.icon` on `bg.surface` | icon on card | 3.0:1 | 5.73 | 9.26 | Pass |
| `tone.ai.fg` on `tone.ai.bg` | chip text | 4.5:1 | 7.51 | 9.90 | Pass |
| `tone.ai.fg` on `bg.surface` | text on card | 4.5:1 | 8.54 | 10.52 | Pass |
| `tone.ai.icon` on `tone.ai.bg` | chip icon | 3.0:1 | 5.76 | 9.90 | Pass |
| `tone.ai.icon` on `bg.surface` | icon on card | 3.0:1 | 6.55 | 10.52 | Pass |
| `accent.brand-light` on `bg.surface` | decorative only | n/a | 2.05 | 8.39 | Info |
| `accent.brand-mid` on `bg.surface` | decorative only | n/a | 2.66 | 6.44 | Info |
| `accent.brand-dark` on `bg.surface` | decorative / large display only | n/a | 3.94 | 4.36 | Info |
| `text.disabled` on `bg.surface` | WCAG-exempt (disabled) | n/a | 2.62 | 2.38 | Info |
<!-- contrast:end -->

## Logo usage

Each brand supplies three logo versions, listed in its `brand.json` (`logos.onDark`, `logos.onLight`, `logos.mark`); requirements are in `brands/README.md`. Miami Temple's files:

| File | Use on | Notes |
|---|---|---|
| `brands/miami-temple/logo-white-on-dark.png` (`onDark`) | The app bar (always dark ink `--ham-bg-appbar`), dark photos, dark-theme splash | The original, official artwork. **Only on dark backgrounds**: ink #111814 or darker, or a dark photo with ≥4.5:1 behind the wordmark. |
| `brands/miami-temple/logo-dark-on-light.png` (`onLight`, + `@small` 843×175) | White or light surfaces: sign-in card, requester pages printed/exported, emails, PDF reports | Only the wordmark is recolored, to ink #111814. The leaves are unchanged. |
| `brands/miami-temple/logo-mark.png` (`mark`) | Favicon/PWA icon, compact app bar on detail screens, avatars for system messages | The pin mark alone. It works on light and on dark backgrounds. |

Rules:
- **Clear space:** keep empty space around the lockup of at least **25% of the logo's height** on every side (8px at the 32px app-bar size). Keep other text, icons and edges out of it.
- **Minimum size:** the full lockup is at least **32px tall on screen** (≈154px wide) and at least 12mm tall in print. Below 32px, use the `mark` logo, which needs at least 24px of height. At smaller sizes the "SEVENTH-DAY ADVENTIST" line becomes unreadable.
- **Never recolor the leaves** or the "SEVENTH-DAY ADVENTIST" green. The only approved change is the dark wordmark variant that already exists.
- Never stretch, rotate, outline, add shadows or effects, place on the brand accent colors or on busy mid-tone photos, rebuild the wordmark in a font, or crop the mark differently.
- Put the logo on a solid background. On light UI use the dark-wordmark file, and on dark use the original. Don't place the white original on light gray to "make it work".
- HAM's own name appears as text beside the church logo (e.g. "Home Assistance Ministry" in the sidebar header, `type-label`), never merged into the logo artwork.
- For the PWA icon, put the `mark` logo centered on white at 80% safe zone (maskable). Generating the icon files happens in the frontend build.

## Accessibility checklist (applies to every screen)
- Every pair in the contrast table passes AA in both themes (V1 ships light only, Q-016), and focus rings are 3px, reach ≥3:1 and are always visible with `:focus-visible`.
- Targets are at least 48×48px (`--ham-size-target-min`, matching `docs/ux`). Body text is at least 16px, and inputs are 16px so iOS doesn't zoom.
- Status always shows an icon plus its text label. Errors always show an icon plus a message tied to the field (`aria-describedby`).
- Motion stays between 150 and 250ms, and the tokens drop to 0ms under `prefers-reduced-motion`.
- Pages work at 200% zoom and at 320px width with no horizontal page scroll (the budget table is the only horizontal scroller, and it has a sticky first column).
