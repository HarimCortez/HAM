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
