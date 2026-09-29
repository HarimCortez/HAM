# HAM Patterns — V1 core

How components combine into screens. Breakpoints: `sm` 390 (design base) · `md` 768 · `lg` 1024 · `xl` 1280 · `2xl` 1536 (PRD §70.1; CLAUDE.md › Design).
Page gutters: 16px (`space-4`) mobile, 24px (`space-6`) tablet, 32px (`space-8`) desktop. Content max width `--ham-size-content-max`; long text and single-column forms max `--ham-size-form-max`.

## 1. Navigation shell
| Width | Shell |
|---|---|
| < 768 | App bar (top) + **bottom nav** (4–5 role-based destinations). Secondary destinations under Profile/"More". |
| 768–1023 | App bar + **sidebar rail** (72px, icons + tooltips). No bottom nav. |
| ≥ 1024 | App bar (logo, global search, notifications, avatar) + **full sidebar** (264px). |
- The requester's secure request page (PRD §7.2) has **no nav**: app bar with logo only, single column, `body-lg` text, `control-lg` inputs, one task per screen.
- Primary action on mobile lives in a sticky bottom action bar (above the bottom nav, `bg.surface`, top `border.default`, safe-area padding). On desktop it sits in the page header, right-aligned.
- One `h1` per screen (`type-h1`, the brand's display face; Oswald for Miami Temple). Desktop list/overview pages may use `type-display`.

## 2. List → detail
- **Mobile:** list screen → push detail screen (back button in app bar). Keep scroll position on return.
- **Tablet:** same as mobile, lists as 2-column cards where cards are used.
- **Desktop (≥ 1280): split view.** List pane 400px (resizable 360–520) + detail pane fills the rest. Selecting a row updates the URL. Detail pane has its own header (h1 + chips + primary action). At 1024–1279 open detail as full page (split view too cramped).
- **Split-view widths (v1.3, from intake):** with the 264px sidebar, 1280 leaves ~950px of content. At 1280–1535 the list pane is `--ham-size-split-list-min` and the detail pane is **one column** (key facts as a compact strip under the header). At ≥1536 the list pane is `--ham-size-split-list` and the detail pane splits into main + side columns (2fr / 1fr). The list pane scrolls independently (`position: sticky`, `max-height: calc(100vh - appbar)`), the detail pane is a labelled region (`aria-labelledby` its h1).
- **Decision split view (v1.4, from approvals).** On the Requests split view at 1280–1535 the sidebar shows as the rail (`--ham-size-sidebar-collapsed`, with its expand control) so the detail pane gets ~850px; the full sidebar returns at ≥1536. The detail is a size container (`container-name: detail`): at `min-width: 42em` it becomes two columns, `minmax(0, 1fr)` main + `--ham-size-aside` side, gap `space-6`, and the side column's Decision card (components §33) is sticky. Below 42em (tablet, 200% text, 400% zoom) it is one column with the Decision card first. The same container rule gives the 1024–1279 full-page detail its two columns. This supersedes the "one-column detail at 1280–1535" line above for the Requests area only.
- Detail layout (desktop): main column (2/3: tasks, timeline, comments) + side column (1/3: key facts, people, budget summary, attention items). Mobile: side column content moves *above* main content as a compact "Key facts" card.

## 3. Cards vs tables
- **Cards** when the viewer acts on one item at a time, content is mixed, or on mobile: volunteer's invitations and projects, attention items, KPI tiles, project board.
- **Tables** (desktop only) when leaders compare many similar records: requests, projects list, volunteers, credentials, budget lines, audit log. Dense-but-calm: 52px rows, no zebra, no vertical lines, `tabular-nums`, sticky header, max 7 visible columns (column picker for more).
- **Persistent filters (desktop):** a filter bar above tables (search + 3–4 filter chips + "More filters" sheet) with active-filter summary and "Clear". On mobile, filters open in a bottom sheet with an "Apply" primary button and a count on the trigger ("Filters · 2").
- Saved views (e.g. "Needs volunteers") appear as tabs above the table — use for §64 areas.

## 4. Forms
- Single column, labels above, max `--ham-size-form-max`. Group with `h3` headings + `space-8` between groups, not boxes.
- Minimize fields (PRD §3.1): prefill from profile/prior project/template; hide optional fields behind "Add details" when rarely used.
- Validate on blur and on submit; on submit error, focus an error summary alert at top listing links to each field.
- Sticky save bar on long forms (mobile bottom, desktop bottom of form column). Autosave drafts where the UX spec allows; show "Draft saved · 2:14 PM" in `text.tertiary`.
- Consequential actions (approve, reject, override, excuse, clear hold) end in a confirm sheet showing *what will happen* and *who will be notified*; the actor and time are recorded (PRD §3.3).
- **Undo window (v1.4, Q-156/Q-176).** Where the rules allow the actor to undo (decisions, urgency certification), the record shows at once with a pending notice (components §37) and an **Undo…** button that opens a small confirm sheet. No undo inside toasts: a 6-second toast is too short and hard to reach by keyboard for a consequential reversal.

## 5. Wizards (intake, site assessment, project planning)
- Steps: 3–7. Header: "Step 2 of 5 · Property" (text, not dots alone) + thin progress bar (`action.primary.bg` on `bg.sunken`).
- One topic per step; mobile shows Back (ghost) + Continue (primary, full width, `control-lg`) in the sticky action bar.
- Desktop: at 1024–1279 left step list (`--ham-size-step-rail`) + form card; the help panel moves below the form. At ≥ 1280 step list + form card (`--ham-size-form-max`) + right help panel (`--ham-size-aside`), in a `--ham-size-wizard-max` container. Components: step indicator (components §21), sticky action bar (§22), choice cards (§19), review summary cards (§23).
- **Large text (requester):** see the large-text contract at the top of components.md "Additions for step 2". Test every requester screen at 390px with 200% text and at 200% zoom: no horizontal scroll, the primary always reachable.
- Final step = review summary with "Edit" links per section, then submit. Save & exit available on every step.
- Requester intake uses `body-lg` + `control-lg` everywhere and plain-language helper text; hazard disclosure step (PRD §39) uses large checkbox cards with icons.

## 6. Dashboards
**Leadership dashboard (PRD §64)** — desktop:
- Row 1: "What needs attention" — AI summary card (suggestion styling, §17 components) + attention list sorted by severity (danger → attention → info).
- Row 2: KPI tiles, 4 across at ≥ 1280, 2 across below (no horizontal carousels).
- Row 3: queue widgets as compact tables/cards, each with count chip + "View all": awaiting approval, awaiting assessment, in planning, needing volunteers, missing qualifications, upcoming, reconfirmation problems, blocked tasks, on hold, credential alerts, budget risks, incidents, follow-ups, recent completions. Hide widgets with zero items behind a "All clear (5)" collapsed row.
- Mobile: attention list first, then KPI tiles 2-up, then queues as collapsible sections.

**Member scoreboard (PRD §63):** hero KPIs Families Served + Volunteer Hours (hero tile variant), then 4 supporting tiles; This Month / This Year / All-Time segmented control. Aggregates only; no names, photos of people or addresses. Warm, celebratory but calm: brand accent stripe, display-face numerals, no confetti. Also available as a public embed on the church website (Q-005); see below.

**Public scoreboard embed (PRD §63, §68; Q-005 decided).** The member scoreboard, read-only, for an `<iframe>` on the church's own website.
- **Brand:** the church's logo (`logos.onLight`, 32px tall, on `bg.surface`) and `church.name` come from the brand layer (`brands/<brand>/brand.json`), with "Home Assistance Ministry" beneath in `type-label`, `text.secondary`. The mission line is optional (`type-small`). Never hard-code a church's name or logo in the embed.
- **Content, aggregates only:** the two hero tiles (Families Served, Volunteer Hours) and the four supporting tiles, the This Month / This Year / All-Time control, and "Updated <date>" (`type-small`, `text.tertiary`). Nothing else: no names, initials, photos of people, addresses, neighborhoods, project titles, dates of individual projects, testimonials or per-project breakdowns.
- **Nothing small enough to identify a family:** if a period's Families Served is below the minimum count from the rules module (`PRD-GAP`: value not yet decided), that period's tiles show "Fewer than N" in `text.secondary` instead of numbers, and Cost of Assistance and Satisfaction Rating are hidden for that period (one family's aid amount or rating would be identifiable). The time control keeps working; This Year and All-Time normally carry the numbers.
- **Layout:** sized by the iframe, not the viewport (container queries). Under 480px: one column, heroes stacked; 480–799px: heroes side by side, supporting tiles 2-up; 800px and wider: heroes side by side, supporting tiles 4-up. Its own `bg.surface` card with `radius-lg` and `space-6` padding, so it reads well on any host page color. Light theme only.
- **Accessibility:** the host `<iframe>` needs `title="<shortName> Home Assistance Ministry scoreboard"`. KPIs are real text (not images), each with its label; the time control is a labelled radio group.
- **Don't:** add a sign-in prompt, cookies, tracking, or links into member areas.

**Volunteer home:** a to-do list in the fixed order of `docs/ux/navigation.md` §7.3: project-day card → blocking items → needs response → next up → heads-up → later → ministry impact line. The reliability score is not on Home; it lives in Me (PRD §34).

## 7. Status display and timelines
- Everywhere a record appears, its current state is the status chip (components §5) with exact PRD label. Group lists by status using the same chips as section markers.
- Detail screens: chip in header + status timeline (components §16) in main column or a "History" tab.
- Holds, blocks, rejections: chip + reason line + banner on the detail page explaining what happens next and who can act.
- Credential expiry (PRD §24.1): *Expiring Soon* / *Expired* are computed badges, not statuses (Q-018). Show days-remaining text ("Expires Nov 3 (28 days)") next to the badge; never a color-only progress ring.

## 8. Photo capture and upload (PRD §45–§48, §69)
- **Mobile:** primary button "Take photo" (`camera` icon, opens camera via `capture`) + secondary "Choose from library". Allow multi-select.
- Thumbnails grid 3-up (mobile) / 5-up (desktop), 1:1, `radius-md`. Each: per-file progress bar overlay, retry on failure (`tone.danger` icon + "Retry"), remove (48px `x` button with `aria-label="Remove photo 3"`).
- Uploads continue in background; offline-queued files show `cloud-off` icon + "Will upload when online".
- Show limits before picking (count/size/types from the rules module — never hard-coded in UI copy). Videos show duration and retention note where the UX spec requires (PRD §47).
- Media consent (PRD §48): consent state displayed as a text line + icon under the grid, not as a color on the thumbnails.
- Requester uploads via secure link: large dashed drop zone (`border.strong`, `radius-lg`, 160px tall) with clear instruction text; works without drag-and-drop.

## 9. Check-in (PRD §37)
- Full-screen mobile flow: big `control-lg` "Check in" primary; QR scanner view with high-contrast frame; location permission asked only at this moment with plain-language reason.
- Result states use full-width alerts: success (teal, `circle-check-big`) "Checked in 8:02 AM", attention "You're a bit far from the site — ask your Project Leader to confirm you".

## 10. Loading, offline, errors
- Skeletons (`bg.sunken`, `radius-sm`, pulse opacity 0.6→1 at `duration-slow`, off with reduced motion) for lists/cards; spinner only inside buttons.
- Offline (PWA): top banner `tone.attention` "You're offline. Changes will sync when you reconnect." Queued changes show `cloud-off` icon.
- Integration down (PRD §70.3): info banner on affected screens only; never block the user's work.
- Error pages: friendly title, what happened, one action; include logo on requester-facing pages.

## 11. Theming
- **V1 is light only (Q-016, decided).** The dark tokens are kept for later and apply only via `data-theme="dark"` **on `<html>` only** (status aliases resolve at `:root`). Automatic OS dark mode is off (`ham.autoDark: false`). The mockup theme toggles are for review only; the app ships no theme switch.
- The app bar stays dark ink in both themes, so every church's white-on-dark logo works there. Photos are never tinted. Illustrations use the brand accent colors (`accent.brand-*`) + neutrals only.
- **Church brand:** components never name a church, a logo file or a brand hex. They use semantic tokens (`action.primary.bg`, `text.link`, `accent.brand-*`, `--ham-font-display`) and read name, mission line and logos from the active brand's `brand.json`. See `brands/README.md`.
