# Step 1 visual QA: foundation + auth

Reviewer: ham-ui-designer · 2026-09-28 · branch `feature/step-1-foundation` @ `4bd48fa`
Checked against `design-system/` (tokens.css, components.md, patterns.md, README brand and logo rules), `docs/ux/navigation.md` and `docs/ux/auth-and-access.md` §4.
Screenshots: `docs/ux/screenshots/step1-qa/<screen>-<width>.png` at 390, 768 and 1280 (full page, light theme only per Q-016). An in-page audit (target size, computed font and size of controls, text contrast on the effective background, horizontal overflow) ran on every capture. axe-core isn't installed offline, so this is a stand-in for axe, not a replacement.

**What's good.** Every `var(--ham-*)` in `shell.css` resolves to a real token. Text contrast passes on every screen (0 failures). Oswald is used only for `h1`, as specified. The app bar is dark ink with the brand stripe and the white-on-dark logo. Primary and secondary buttons are 48px tall with the correct fills. The users table at 1280 is dense but calm. The 390 bottom nav for Volunteers is correct in content.

**The main problems.** The shell doesn't yet follow the navigation spec for the Administrator on mobile and tablet. The impersonation banner disappears on the not-found page. Some form controls fall back to browser defaults (Arial 13px, 21px tall, blue checkboxes). The auth screens use a centered card rather than the specified public column.

---

## Critical

**C1. The impersonation banner is missing on the neutral not-found page**
- Where: 390 / 768 / 1280. Screenshots: `63-impersonation-banner-not-found-*.png`, compared with `61-impersonation-banner-home-*.png`.
- Why it matters: the spec requires the banner on every route, "including errors and J3" (auth-and-access I2; PRD §59). Here Nadia, acting as Kevin, lands on a page with no sign that she is acting as someone else and no **Return to my account** button.
- Cause: `not_found.html` (and `server_error.html`) extend `base_public.html`, which has no banner slot.
- Fix:
  1. Move the banner markup from `base.html` into a partial, `web/_impersonation_banner.html`.
  2. Include that partial in both `base.html` and `base_public.html`, directly under the bar.
  3. For a signed-in viewer, render J3 inside `base.html` (nav kept, "Go home" still primary), so a signed-in person never drops out of the shell. Use `base_public` only when nobody is signed in.

**C2. The Administrator's mobile bottom nav has 7 items and overflows**
- Where: 390. Screenshots: `11-home-admin-390.png`, `30-users-list-390.png`, `40-audit-list-390.png`.
- What's wrong: "Rules" is cut off at the right edge. Audit log and Me can't be reached.
- Spec: navigation.md §3.1 caps the bottom nav at 5 items. For the Administrator it is **Home · Admin · Inbox · More**. Users & roles, Church settings, Integrations, Rules and Audit log belong under an **Admin** hub (or **More**), not in separate tabs.
- Fix (whoever builds `nav_items`): give the nav builder a `bottom_nav_items` list capped at 5 per §3.1, and render `_nav_items.html` from that list for `.nav--bottom` only. The sidebar keeps the full list.
- CSS safety net: `.nav--bottom > .nav { overflow: hidden }` stops the clipping from reaching the page, but it doesn't fix the navigation itself.

## Major

**M1. Filter-bar and audit filter inputs are unstyled browser defaults**
- Where: all widths. Screenshots: `40-audit-list-*.png` and `30-users-list-*.png`.
- What's wrong:
  - The audit log's date and text inputs are **21px tall, 13.3px Arial or monospace** (tap targets far below 44px, off the type scale).
  - The users-list search and selects are 48px tall but also 13.3px Arial.
- Fix in `shell.css`:
  - Extend the `.filter-bar select, .filter-bar input[type="search"]` rule to cover `.filter-bar input` (all types), and add `font: var(--ham-type-body-weight) var(--ham-type-body-size)/var(--ham-type-body-line-height) var(--ham-font-ui)`. The 16px size also stops iOS from zooming.
  - Give every text-like input the same base font by adding `input, select, textarea, button { font: inherit; }` next to the `body` rule.
  - Add `input[type="date"]` to the `.form-field input[...]` list.
- Also, per patterns.md §3, give each audit filter a visible label or a meaningful placeholder. "mm/dd/yyyy" twice doesn't say which is From and which is To.

**M2. Checkboxes are browser blue (off-palette)**
- Where: all widths. Screenshots: `20-me-*.png`, `31-user-detail-*.png`, `03-two-step-challenge-*.png`.
- Fix: add `accent-color: var(--ham-action-primary-bg);` to `.form-field--toggle input[type="checkbox"], .role-row input[type="checkbox"]`, or globally to `input[type="checkbox"], input[type="radio"]`.
- Also make the whole label row at least 48px tall (`min-height: var(--ham-size-target-min)` on `.form-field--toggle label`, `.role-row`), as components.md §10 requires ("24px box, 48px row").

**M3. The audit log crams the table into a 420px column at 1280, with an empty right pane**
- Where: 1280. Screenshot: `40-audit-list-1280.png`.
- What's wrong: dates wrap across 5 lines and UUIDs across 4. The `.list-detail` grid is applied, but no detail pane is rendered, and the detail opens as a full page (`41-audit-detail-1280.png`).
- Fix, either:
  - (a) Render the selected event in a second grid child (`<aside class="list-detail__pane">`), per auth-and-access H2 and patterns.md §2, or
  - (b) until then, drop the `list-detail` wrapper in `audit_log_list.html` so the table fills the width.
- Also:
  - Add `white-space: nowrap` to the When cell (`.data-table td.is-nowrap`).
  - Show the subject as a person's name or a short "User · Kevin T." rather than a raw UUID.
  - Right-size the Action column.

**M4. The auth screens don't match the public-layout spec**
- Where: 390 / 768 / 1280. Screenshots: `01-sign-in-email-*.png`, `02-sign-in-code-*.png`, `03-two-step-challenge-*.png`, `04-step-up-*.png`, `05-two-step-setup-*.png`.
- Spec (auth-and-access §4 preamble; patterns.md §1): single column at `--ham-size-form-max`, **left-aligned**, `control-lg` inputs and buttons, `body-lg` text, primary button in a sticky bottom action bar on mobile and inline on desktop, logo lockup above, no marketing card.
- What the build does instead:
  - `.public-card` sets `text-align: center`. Labels, helper text and the h1 are centered while the inputs and the primary button sit left, so there are two alignment axes. This is most visible on `02-sign-in-code-390.png`: **Sign in** is at the left and **Resend email** is centered below it.
  - Inputs are 48px (`control-md`), not 52px (`control-lg`).
  - Body text is 16px, not 18px (`body-lg`).
  - The primary button isn't full width or sticky on mobile.
  - The form is vertically centered, which leaves about 180px of dead space above the h1 on a phone.
  - The "Home Assistance Ministry · {church.name}" eyebrow is missing.
- Fix:
  - `.public-card`: remove `text-align: center`, `box-shadow` and the card background below `lg`. Keep a quiet `bg.surface` card with `radius-lg` only at ≥1024.
  - `.public-shell__content`: `align-items: flex-start`, `padding-top: var(--ham-space-8)`.
  - Add `.public-shell .form-field input { min-height: var(--ham-size-control-lg) }`, and set `.public-shell .btn { min-height: var(--ham-size-control-lg) }` and `.public-shell p { font-size: var(--ham-type-body-lg-size); line-height: var(--ham-type-body-lg-line-height) }`.
  - Below 768, make `.public-shell .form-actions` a sticky bottom bar (`position: sticky; bottom: 0; background: var(--ham-bg-surface); border-top: 1px solid var(--ham-border-default); padding: var(--ham-space-3) var(--ham-space-4) calc(var(--ham-space-3) + env(safe-area-inset-bottom))`) with `.btn--primary { width: 100% }`.
  - Add the eyebrow to `base_public.html` above `{% block public_content %}`: `<p class="public-card__eyebrow">Home Assistance Ministry · {{ church.name }}</p>` (`type-label`, `text.secondary`).
  - Secondary actions after the form (**Resend email**, **Sign out** on setup) sit left-aligned in their own `.form-actions` row. **Sign out** on setup should be Ghost (C1–C3: "Ghost link Sign out"). A `.btn--ghost` class doesn't exist yet: add it (`background: transparent; color: var(--ham-action-ghost-fg)`).

**M5. The public logo is 28px, below the brand minimum**
- Where: all public screens, all widths. Screenshots: `01-*`, `90-*`.
- Rule: the README logo rules set the full lockup at **32px minimum**. `.public-shell__bar .app-bar__logo { height: 28px }` and the `height="28"` attribute in `base_public.html` both break it.
- Fix: set both to 32px, and delete the override rule.
- Spec extra (auth §4, "logo lockup above the column" on desktop): at ≥1024 you may also show `logos.onLight` at 40px above the column on `bg.canvas`. That's optional this step.

**M6. The empty phone number shows as "or call ."**
- Where: sign-in, all widths. Screenshot: `01-sign-in-email-*.png`.
- Cause: `church.phone` is blank in dev (Church settings has the ministry phone empty), so the requester pointer ends with a dangling period.
- Fix in `sign_in.html`: `{% if church.phone %}, or call {{ church.phone }}{% endif %}.`, falling back to `church.ham_email` if present. The same guard will be needed anywhere `{church.hamPhone}` appears.

**M7. Rail (768–1023) is icon-only with no labels or tooltips**
- Where: 768. Screenshots: `11-home-admin-768.png`, `10-home-volunteer-768.png`.
- What's wrong: the Administrator sees 8 look-alike icons (Rules and Audit log are both book shapes). `.nav--rail .nav__label` is moved off-screen, and there is no tooltip.
- Fix: show the label under the icon, like the bottom nav: `.nav--rail .nav__label { position: static; font: nav-compact tokens; text-align: center }` with `.nav--rail .nav__link { min-height: 64px; gap: var(--ham-space-1) }`. This matches navigation.md §3.2 ("labels on long-press/hover" is the minimum; visible labels are kinder at 72px).

**M8. Buttons squeeze and overflow in `.form-actions` on mobile**
- Where: 390. Screenshots: `31-user-detail-390.png` and `60-impersonate-confirm-390.png`.
- What's wrong: on user detail, "Reset two-step sign-in" wraps into 5 lines and "Troubleshoot as…" spills out of the card, so the page overflows horizontally (the audit flags `overflow=true`). On impersonate confirm, "Start troubleshooting" wraps onto 2 lines.
- Fix: `.form-actions { flex-wrap: wrap; }`. Below 768, stack secondary account actions full width: `.card .form-actions .btn { flex: 1 1 100%; }`. Button labels must never wrap mid-word, so add `.btn { white-space: normal; text-wrap: balance; }` and rely on wrapping rows rather than narrow buttons.

**M9. The impersonation banner scrolls away and shows a short name**
- Where: all widths. Screenshots: `61-*`, `62-*`.
- Fix:
  - Make it sticky under the app bar: `.impersonation-banner { position: sticky; top: calc(var(--ham-size-appbar-height) + env(safe-area-inset-top, 0px)); z-index: var(--ham-z-appbar); }`.
  - The I2 copy is "Acting as **Kevin Thompson**" with the full name, not "Kevin T."
  - Add the `user-cog` icon, 20px, `tone.attention.icon`, before the text. Colour is never the only signal.
  - On desktop, I2 asks for one line. Put the reason and idle text inline after a " · " separator at ≥1024 (`.impersonation-banner__reason, __idle { display: inline }`).

**M10. Home and every shell page have two h1 elements, and Home has none of its own**
- Where: all widths. Screenshots: `10-*`, `11-*`, `20-*`, `30-*`.
- What's wrong: `base.html` renders the app-bar title as `<h1 class="app-bar__title">`, and pages add their own `<h1>` ("Me", "Users & roles"), which breaks patterns.md §1 "One h1 per screen". On desktop the bar title repeats the page h1 right above it.
- Fix:
  - Change the app-bar title to `<p class="app-bar__title" aria-hidden="true">`, or to `<span>`.
  - Hide it at ≥1024 (`.app-bar__title { display: none }`), where components.md §1 puts search, notifications and the avatar there instead.
  - Give Home a real page h1 (e.g. "Hi Kevin", as navigation.md §7.5 shows).

**M11. The Home empty state is too bare, and desktop is a stretched phone**
- Where: 1280. Screenshots: `10-home-volunteer-1280.png`, `11-home-admin-1280.png`.
- Home is the product's front door. components.md §12 asks for a 96px line illustration (brand accents plus neutrals), an `h3` title, one sentence and one action. The build shows grey centered text in an empty 1016px canvas.
- Fix now (it's a placeholder, but the product owner will see it):
  - Add the illustration slot and one Secondary action ("Update my profile" → Me).
  - Put a greeting h1 above it, left-aligned at the page gutter.
  - At ≥1280, lay Home out as the two-column grid from navigation.md §3.3, even with placeholders ("What needs attention", "Coming up"), so the desktop shape is established.
- The empty-state `h3` sits in `text.secondary`. Titles should be `text.primary`, so set `.empty-state h3 { color: var(--ham-text-primary) }`.

## Minor

1. **Bottom-nav items cluster left instead of sharing the width.** Seen at 390 in `10-home-volunteer-390.png` and `20-me-390.png`. The `<li>` isn't the flex child that grows. Fix: `.nav--bottom > .nav > li { flex: 1; }`. The selected item also needs the 32×4px `border.selected` pill above the icon (components.md §2), not only the `bg.selected` fill.
2. **The sidebar selected item lacks the 4px left bar, and the header is wrong** (components.md §3). Add `box-shadow: inset 4px 0 0 var(--ham-border-selected)` to `.nav--sidebar .nav__link[aria-current]`. The header reads "HAM" in 14px `text.secondary`; the spec is "Home Assistance Ministry" in `type-label`. Group the admin items under an "Admin" group label (`type-small`, `text.tertiary`), and move Me to the bottom above **Sign out**. Sign out currently exists only inside Me → Sign-in & security.
3. **The logo link is a 154×32px target**, flagged on every shell page. Add `.app-bar__logo-link { min-height: var(--ham-size-target-min); padding-block: var(--ham-space-2); }`.
4. **Chips have no icon** (components.md §5: "icon is always present"). Seen on the Active/Invited/Turned off chips in `30-users-list-1280.png` and `31-user-detail-1280.png`. Add a 16px `circle-check-big`, `mail` or `ban` icon, or the matching status icon, to `.chip`, with `.chip__icon { width: 16px; height: 16px }`. Role chips are labels, not statuses; use a plain `tag` style (`bg.sunken`, no border) so they don't read as status.
5. **The mobile stacked table rows are too airy**: roughly 170px per person, and the unlabeled "On" or "Not needed" loses its "Two-step" header (`30-users-list-390.png`, `40-audit-list-390.png`). Fix per components.md §9 ("title, chip, 1 meta line"): `.data-table td { padding-block: var(--ham-space-1) }`, `tr { background: var(--ham-bg-surface) }`, and prefix non-obvious cells with a `data-label` (`td::before { content: attr(data-label) ": "; color: var(--ham-text-secondary) }`). Scope the hover to real pointers with `@media (hover: hover)` so the first card isn't left stuck grey.
6. **The rules page** (`52-rules-1280.png`): each section's table has different column widths. Use `table-layout: fixed` with `col` widths (60/20/20). Show "Not decided yet…" as an `attention` chip ("Not decided") with the Q-number as text, so open decisions stand out. Give section `h2` elements `margin-top: var(--ham-space-8)`.
7. **The integrations page** (`51-integrations-1280.png`): user-facing copy cites "(PRD §70.3)"; drop it. The empty table should use the compact empty state (components.md §12) instead of an empty row under headers.
8. **The audit event detail** (`41-audit-detail-1280.png`): the h1 is a raw code (`auth.sign_in.succeeded`) in Oswald, and "After: {'first_sign_in': False}" is a Python repr. Map actions to a human label ("Signed in") with the code in `text.tertiary` beneath. Render before/after as a `kv-list`. Show the time in local time with the zone (PRD §70.5); the list and detail currently show UTC.
9. **The two-step setup screen** (`05-two-step-setup-*.png`) lacks "Step 1 of 3 · …" and a progress bar (patterns.md §5). The key should be in 4-character groups with a **Copy key** button. On phones the QR belongs in a disclosure, below an "Open my authenticator app" Secondary lg button (C2). `.recovery-codes` and the key use a raw `ui-monospace` stack; add a `--ham-font-mono` token rather than a literal.
10. **Step-up** (`04-step-up-*.png`) renders as a full public page with an `h2` and no `h1`. D specifies a bottom sheet on mobile and a 480px modal on desktop over the page being confirmed. For this step at least, use `h1` and **Use a recovery code instead** as a Link, and make **Cancel** a Ghost button per D. Behaviour note for ham-ux-designer: impersonation asks for the reason, then step-up, then the reason **again** (the form re-renders empty after step-up).
11. **The mobile app-bar title wraps to 2 lines**, e.g. "Troubleshoot as someone else" (`60-impersonate-confirm-390.png`). Add `.app-bar__title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0 }` (components.md §1 allows an ellipsis for titles only).
12. **Hard-coded values**: inline `style=` attributes in `admin_user_detail.html` (lines 20, 57, 130); `.sheet { max-width: 480px }`, `.empty-state { max-width: 360px }` and `.chip { height: 28px }` in `shell.css`; `.impersonation-banner__text { min-width: 200px }`. Move these into classes or size tokens (`--ham-size-modal-sm`, `--ham-size-empty-max`, `--ham-size-chip`), which I'll add to `tokens.json` in the next design-system pass.
13. **No hover, pressed or disabled states** for `.btn--secondary` (`-bg-hover`), `.btn--primary:active` (`-bg-pressed`), or `[disabled]` (`action.disabled.*`), and no `transition` on `--ham-duration-fast`.
14. **An unknown URL shows Django's DEBUG 404** (`91-not-found-404-*.png`) because the dev server runs with `DEBUG=True`. Confirm that `handler404` renders `not_found.html` in production (and with C1's banner).
15. **The sign-in email's link is relative** (`/sign-in/link/<token>`, no host), seen in the server log. That's for the email template or integrations owner, not visual, but it will be broken in real inboxes.

## Focus and contrast

Focus rings are visible and on-token: a 3px `focus.ring` with offset on inputs, seen in `95-focus-ring-me-390.png` and `96-focus-ring-sign-in-390.png`. On inputs, the ring plus the green border reads as a double outline, which is acceptable. Text contrast has zero failures across all 69 captures.

## Screenshots for the product owner

- **Sign-in:** `docs/ux/screenshots/step1-qa/01-sign-in-email-390.png`. Mobile first, logo and brand clear. Show it after M4, M5 and M6 if possible; today it has the "or call ." bug and centered alignment.
- **Home:** `docs/ux/screenshots/step1-qa/11-home-admin-1280.png`. Shows the full desktop shell (dark app bar with stripe, sidebar, selected state). Present it as "shell, content arrives in step 2", because the canvas is the M11 placeholder.

## Implementation checklist (ham-frontend-engineer)

- [ ] C1: move the impersonation banner into a shared partial for both bases, and render J3 in the signed-in shell.
- [ ] C2: cap the bottom nav at 5 items with the Administrator set Home · Admin · Inbox · More.
- [ ] M1: set the `font: inherit` base on controls, style every `.filter-bar input`, and add date inputs to `.form-field`.
- [ ] M2: `accent-color` on checkboxes, plus 48px rows.
- [ ] M3: add the audit detail pane, or drop `.list-detail`; add nowrap on dates and human subject labels.
- [ ] M4: rework the public layout (left-aligned column, control-lg, body-lg, sticky mobile action bar, eyebrow, `.btn--ghost`).
- [ ] M5: public logo at 32px.
- [ ] M6: guard the empty phone number.
- [ ] M7: rail labels.
- [ ] M8: `.form-actions` wrap and full-width buttons on mobile.
- [ ] M9: sticky banner, full name, icon, one line on desktop.
- [ ] M10: a single h1 per page, and hide the app-bar title at ≥1024.
- [ ] M11: Home empty state with illustration and action, greeting h1, desktop two-column skeleton.
- [ ] Minor items 1–14.
