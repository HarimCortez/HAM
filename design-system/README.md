# HAM Design System

Version 1.1.0 · Build-order step 0 · Owner: ham-ui-designer
HAM is a ministry of Miami Temple Seventh-day Adventist Church, so it looks like part of the church: the logo's three greens, a heavy condensed heading face that echoes the wordmark, and calm neutrals. It should feel like a well-made consumer app, warm and trustworthy, not like church admin software.

| File | What it is |
|---|---|
| `tokens.json` | **Source of truth.** Primitives, semantic aliases (light `$value` plus dark in `$extensions["ham.modes"].dark`) and every status with its label, tone and icon. |
| `tokens.css` | Generated CSS custom properties: `:root` is light; dark values sit under `[data-theme="dark"]`. Automatic OS dark mode is switched off while Q-016 is open (`ham.autoDark: false` in `tokens.json`). Do not edit by hand. |
| `components.md` | Visual spec for each V1 core component: anatomy, variants, states, a11y, do/don't. |
| `patterns.md` | Navigation shell, list→detail, cards vs tables, forms, wizards, dashboards, timelines, photo upload, theming. |
| `tools/build_tokens.py` | Regenerates `tokens.css` and the tables in this README, and fails (`--check`) if a required contrast pair drops below AA. |
| `assets/` | Logo files (see Logo usage). |

## How to use

1. Load the fonts and tokens once in the app shell:
   ```html
   <link rel="preconnect" href="https://fonts.googleapis.com">
   <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
   <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..700&family=Oswald:wght@500..700&display=swap" rel="stylesheet">
   <link rel="stylesheet" href="/design-system/tokens.css">
   ```
   Because HAM is a PWA that should work offline, the frontend should **self-host** both fonts (e.g. `@fontsource-variable/inter` and `@fontsource-variable/oswald`) when the stack is chosen (Q-003). The Google Fonts link above is for prototypes.
2. Base styles: `body { background: var(--ham-bg-canvas); color: var(--ham-text-primary); font: var(--ham-type-body-weight) var(--ham-type-body-size)/var(--ham-type-body-line-height) var(--ham-font-ui); }`.
3. Use **semantic** variables in components (`--ham-text-secondary`, `--ham-action-primary-bg`, `--ham-status-task-blocked-bg`). Use primitives (`--ham-color-brand-600`) only inside the token files.
4. **V1 ships light only (proposed default of Q-016, pending).** The dark values are kept, ready for later, and apply only when `data-theme="dark"` is set on `<html>`. The mockups' theme toggle exists for review only. If Q-016 is decided in favor of dark, set `ham.autoDark` to `true` and rebuild so the theme follows the OS.
5. To change a token, edit `tokens.json`, then run `python3 design-system/tools/build_tokens.py --check` and commit all three files.

**Naming:** `--ham-color-*` = primitive color · `--ham-{bg|text|border|action|focus|accent|tone|appbar|badge}-*` = semantic color · `--ham-type-{style}-{family|weight|size|line-height|tracking}` · `--ham-space-*` (4px grid; `space-4` = 16px) · `--ham-radius-*` · `--ham-size-*` · `--ham-shadow-*` · `--ham-duration-*` / `--ham-easing-*` · `--ham-z-*` · `--ham-status-{group}-{status}-{bg|fg|border|icon}`.

## Color decisions

- **Brand green comes from the logo's dark leaf (#0B9444), used carefully.** Against white it reaches only 3.94:1, which is fine for big display text and graphics but too low for normal text or for white text on a button. So:
  - **Primary button fill = `brand-600` #087F3A**: white text on it is 5.11:1, and it still reads as "the logo green".
  - **Links and brand text = `brand-700` #066B31** (6.66:1 on white).
  - Dark theme (pending Q-016): the button becomes `brand-400` #34AE66 with ink text (6.35:1), and links use `brand-300`.
- **The light green (#8CC63F) and mid green (#39B54A) are accents only.** They appear in the 3px leaf stripe under the app bar, in illustrations and on hero KPI tiles. They are never used for text on white (2.05:1 and 2.66:1) and never carry meaning.
- **Neutrals** are slightly green-tinted grays built from the wordmark ink #111814, so the grays sit naturally beside the greens.
- **"Success" is teal (#0E7C74 / #0B5E58), not brand green, on purpose.** HAM uses green everywhere for "act here" (buttons, selected nav) and for "work under way" (Ready, Scheduled, In Progress). If "done" were the same green, a finished task would look like a button, and a volunteer couldn't tell *In Progress* from *Completed* at a glance. Teal still reads as positive. Every success state also carries a check icon, and every chip has a text label, so no one depends on the hue (including people with red-green color blindness).
- **Seven tones cover every state.** Statuses don't each get their own color; each one maps to a tone, and its icon tells it apart. The tones are **neutral** (not started / closed), **info** (moving along, nothing needed from you), **attention** (waiting on a person, amber), **active** (on track or happening now, brand green), **success** (done or verified, teal), **danger** (blocked, unsafe, expired, red) and **ai** (suggestions only, violet, never a status). Fewer colors are easier to learn, and the icon always tells statuses apart.
- **The app bar is dark ink in both themes**, which lets HAM show the church's original white logo exactly as issued.

## Typography

| Role | Font | Why |
|---|---|---|
| Display (screen titles `h1`, KPI numbers, requester page hero) | **Oswald** 600 | A heavy condensed sans that echoes the "MIAMI TEMPLE" wordmark. It is free, variable, and includes **Cyrillic** and Latin Extended, which matters because the church site already offers Spanish and Russian. Barlow Condensed has no Cyrillic, so it was ruled out. |
| UI (everything else) | **Inter** (variable, `opsz`) | Very large x-height and open shapes help older requesters and people reading outdoors in sunlight. It has tabular figures for tables and budgets, covers Latin Extended, Cyrillic, Greek and Vietnamese, and is one of the most-tested UI faces. Atkinson Hyperlegible was a strong option, but it lacks Cyrillic and tabular figures. Where the platform supports it, turn on Inter's disambiguation set (`font-feature-settings: "ss02"`) on requester pages and for license numbers, so I/l/1 and 0/O look different. |

Scale (from the `--ham-type-*` tokens): display 40/48 · h1 32/40 · h2 22/30 · h3 18/26 · body-lg 18/28 · **body 16/24 (minimum for body text)** · label 16/24 semibold · small 14/20 (metadata only) · chip 14/20 semibold · kpi 40/44 · nav-compact 12/16 (bottom-nav labels only, always paired with an icon).

- Oswald is for sparse use only. Never set body text, form labels, buttons or long headings in it, and never set whole paragraphs in capitals.
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
| `text.link` on `bg.canvas` | text | 4.5:1 | 6.24 | 9.24 | Pass |
| `text.link` on `bg.surface` | text | 4.5:1 | 6.66 | 8.26 | Pass |
| `text.link` on `bg.surface-raised` | text | 4.5:1 | 6.66 | 7.47 | Pass |
| `text.link` on `bg.sunken` | text | 4.5:1 | 5.85 | 8.68 | Pass |
| `text.primary` on `bg.selected` | text | 4.5:1 | 16.36 | 12.93 | Pass |
| `text.primary` on `bg.hover` | text | 4.5:1 | 15.85 | 13.63 | Pass |
| `text.brand` on `bg.selected` | text | 4.5:1 | 6.04 | 7.08 | Pass |
| `text.on-primary` on `action.primary.bg` | text | 4.5:1 | 5.11 | 6.35 | Pass |
| `text.on-primary` on `action.primary.bg-hover` | text | 4.5:1 | 6.66 | 8.68 | Pass |
| `text.on-primary` on `action.primary.bg-pressed` | text | 4.5:1 | 8.87 | 11.67 | Pass |
| `text.on-danger` on `action.danger.bg` | text | 4.5:1 | 6.57 | 4.73 | Pass |
| `text.on-danger` on `action.danger.bg-hover` | text | 4.5:1 | 7.78 | 5.73 | Pass |
| `action.secondary.fg` on `action.secondary.bg` | text | 4.5:1 | 6.66 | 8.26 | Pass |
| `action.secondary.fg` on `action.secondary.bg-hover` | text | 4.5:1 | 6.04 | 7.08 | Pass |
| `text.on-appbar` on `bg.appbar` | text | 4.5:1 | 18.03 | 18.03 | Pass |
| `text.on-inverse` on `bg.inverse` | text | 4.5:1 | 18.03 | 14.54 | Pass |
| `appbar.text-muted` on `bg.appbar` | text | 4.5:1 | 9.64 | 9.64 | Pass |
| `appbar.text-muted` on `appbar.field-bg` | text | 4.5:1 | 7.56 | 7.56 | Pass |
| `text.on-appbar` on `appbar.field-bg` | text | 4.5:1 | 14.14 | 14.14 | Pass |
| `badge.fg` on `badge.bg` | text | 4.5:1 | 6.57 | 6.57 | Pass |
| `action.primary.bg` on `bg.canvas` | UI | 3.0:1 | 4.79 | 6.76 | Pass |
| `action.primary.bg` on `bg.surface` | UI | 3.0:1 | 5.11 | 6.04 | Pass |
| `action.danger.bg` on `bg.surface` | UI | 3.0:1 | 6.57 | 3.63 | Pass |
| `action.secondary.border` on `bg.surface` | UI | 3.0:1 | 5.11 | 6.04 | Pass |
| `border.strong` on `bg.surface` | UI | 3.0:1 | 3.69 | 4.65 | Pass |
| `border.strong` on `bg.canvas` | UI | 3.0:1 | 3.46 | 5.20 | Pass |
| `border.selected` on `bg.surface` | UI | 3.0:1 | 5.11 | 6.04 | Pass |
| `focus.ring` on `bg.canvas` | UI | 3.0:1 | 6.24 | 9.24 | Pass |
| `focus.ring` on `bg.surface` | UI | 3.0:1 | 6.66 | 8.26 | Pass |
| `appbar.status-ok` on `bg.appbar` | UI | 3.0:1 | 11.42 | 11.42 | Pass |
| `appbar.field-border` on `bg.appbar` | UI | 3.0:1 | 4.89 | 4.89 | Pass |
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
| `accent.leaf-light` on `bg.surface` | decorative only | n/a | 2.05 | 8.39 | Info |
| `accent.leaf-mid` on `bg.surface` | decorative only | n/a | 2.66 | 6.44 | Info |
| `accent.leaf-dark` on `bg.surface` | large display / graphics only | n/a | 3.94 | 4.36 | Info |
| `text.disabled` on `bg.surface` | WCAG-exempt (disabled) | n/a | 2.62 | 2.38 | Info |
<!-- contrast:end -->

## Logo usage

| File | Use on | Notes |
|---|---|---|
| `assets/logo-white-on-dark.png` | The app bar (always dark ink `--ham-bg-appbar`), dark photos, dark-theme splash | The original, official artwork. **Only on dark backgrounds**: ink #111814 or darker, or a dark photo with ≥4.5:1 behind the wordmark. |
| `assets/logo-dark-on-light.png` (+ `@small` 843×175) | White or light surfaces: sign-in card, requester pages printed/exported, emails, PDF reports | Only the wordmark is recolored, to ink #111814. The leaves are unchanged. |
| `assets/logo-mark.png` | Favicon/PWA icon, compact app bar on detail screens, avatars for system messages | The pin mark alone. It works on light and on dark backgrounds. |

Rules:
- **Clear space:** keep empty space around the lockup of at least **25% of the logo's height** on every side (8px at the 32px app-bar size). Keep other text, icons and edges out of it.
- **Minimum size:** the full lockup is at least **32px tall on screen** (≈154px wide) and at least 12mm tall in print. Below 32px, use `logo-mark.png`, which needs at least 24px of height. At smaller sizes the "SEVENTH-DAY ADVENTIST" line becomes unreadable.
- **Never recolor the leaves** or the "SEVENTH-DAY ADVENTIST" green. The only approved change is the dark wordmark variant that already exists.
- Never stretch, rotate, outline, add shadows or effects, place on the leaf greens or on busy mid-tone photos, rebuild the wordmark in a font, or crop the mark differently.
- Put the logo on a solid background. On light UI use the dark-wordmark file, and on dark use the original. Don't place the white original on light gray to "make it work".
- HAM's own name appears as text beside the logo (e.g. "Home Assistance Ministry" in the sidebar header, `type-label`), never merged into the logo artwork.
- For the PWA icon, put `logo-mark.png` centered on white at 80% safe zone (maskable). Generating the icon files happens in the frontend build.

## Accessibility checklist (applies to every screen)
- Every pair in the contrast table passes AA in both themes (dark pending Q-016), and focus rings are 3px, reach ≥3:1 and are always visible with `:focus-visible`.
- Targets are at least 48×48px (`--ham-size-target-min`, matching `docs/ux`). Body text is at least 16px, and inputs are 16px so iOS doesn't zoom.
- Status always shows an icon plus its text label. Errors always show an icon plus a message tied to the field (`aria-describedby`).
- Motion stays between 150 and 250ms, and the tokens drop to 0ms under `prefers-reduced-motion`.
- Pages work at 200% zoom and at 320px width with no horizontal page scroll (the budget table is the only horizontal scroller, and it has a sticky first column).
