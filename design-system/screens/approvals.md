# Approvals: hi-fi screen specs (build-order step 3)

Owner: ham-ui-designer · 2026-09-29 · Design system v1.4 (components; tokens unchanged at 1.3.0)
Behaviour, copy and rules come from `docs/ux/approvals.md` (screens A1–A13, R13–R19, emails E8–E15 / L-E5–L-E12; cited **UX A3** etc.). **The owner-decisions box at the top of that file (and of `docs/architecture/approvals.md`) overrides the body.** Where the UX body and the owner box differ, this spec follows the box, and §0.1 lists each place. Components are `design-system/components.md` (**C§n**; §26a and §33–§40 are new in v1.4), patterns `design-system/patterns.md` (**P§n**), step-2 screens `design-system/screens/intake.md` (**S§n**, L1, L2, R10).

Tokens only: every colour, size, space, radius, shadow and duration below is a token name without the `--ham-` prefix (`space-6`, `text.secondary`, `type-body-lg`, `size.aside`). Copy in quotes is from the UX spec unless marked *(proposed copy)*; `{rules.X}` and `{church.X}` are filled at runtime, never literals. Sample "today" is Tuesday, Oct 6, 2026 (America/New_York); names are fictional.

Contents
0. Shared rules for this step
1. A1 Request detail with the Decision card
2. Decision sheets (A2, A2u, A2n, A2c, A3, U1 undo, A4, A5, A6, A9 with take-over, A11, A12)
3. A7 Requests list tabs
4. A8 Home, Inbox and the urgent banners
5. Requester screens R13–R19
6. Emails (visual deltas)
7. Accessibility names and focus order (reference table)
8. Frontend checklist
9. Visual QA plan
10. Open visual questions

---

## 0. Shared rules for this step

### 0.1 Owner box vs UX body: what this spec does
| UX body says | Owner box (wins) | Visual consequence here |
|---|---|---|
| No undo (UX §2 item 10, G3-7) | Decider may undo for 30 minutes; requester email held; others can't decide in the window (Q-156, Q-176) | Pending notice C§37 in the Decision card; **Undo decision…** + undo sheet U1; "Decision pending" for others; row marker; requester page unchanged during the window (§10 OQ-1) |
| Reconsider window 30 days | 14 days, ending at the end of the church-local day printed (Q-155, Q-174) | Sample date: decided Tue Oct 6 → "until Tue, Oct 20" |
| Decline reasons (UX A3 list) | Q-154 list: Family or others may be able to help · The owner or landlord is responsible for this repair · This isn't the kind of help HAM offers · We couldn't confirm what we needed · Another reason | The five radio cards in A3/A9 use these labels |
| "Note for HAM leadership" on approve, decline and not-urgent | One optional **"Why approved (leaders only)"** note, on approval only (Q-169) | Field only in A2/A2b/A2u/A9-approve; none in A3, A2n |
| "What Doris will read", "Ask Doris…" | "the requester" until this viewer uses Show contact details (Q-170); the Director always sees the name | Copy slot `{requester}` (0.5) |
| Change category: Director/AD (UX) vs +pastors/Board (arch body) | Director and AD only; allowed while impersonating (Q-109, Q-172) | A6 only in the Director/AD More menu |
| Board approval of urgent = "not certified" | Board approval leaves urgency **awaiting certification**; a pastor may certify later (Q-160, Q-161) | New sheet A2c "Certify as urgent" on Approved requests; Urgent chip stays with reason line "Not yet certified" |
| A10 take-over is its own step | One step: required tick + decide (Q-157) | Take-over is a statement card at the top of the A9 sheet |
| Close… on Rejected (window open) | Close as "requester withdrew" only from Approved or Reconsideration Pending (Q-165) | No Close… on Rejected |
| "Left for normal review" in-app update (L-E12) | Not sent (Q-168) | No Inbox row for it; the pastor urgent banner simply clears |
| Reconsideration asked by phone: any leader | Director/AD only (Q-159) | A12 only in the Director/AD More menu |
| Approval copy | Keeps §11: "the visit helps us plan; it doesn't yet promise the work" | R14/R18a "What happens next" carries the line |
| Text limits | Question 500, answer 1,000, reconsideration note 1,000 | Soft counters (0.6) |

### 0.2 Breakpoints and layouts (leadership)
| Width | Shell | A1 detail | Decision actions |
|---|---|---|---|
| 390 (`sm`, works to 320) | App bar + bottom nav | Full page, one column, Decision card first | Sticky action bar above the bottom nav (C§22, C§34) |
| 768 (`md`) | App bar + rail | Full page, one column (content < 42em) | Sticky action bar at the viewport bottom (no bottom nav) |
| 1024–1279 (`lg`) | App bar + full sidebar | Full page, **two columns** by container query (main + `size.aside`) | In the sticky Decision card, top of the side column; no bottom bar |
| 1280–1535 (`xl`) | App bar + **rail** on Requests (P§2 v1.4) | **Split view**: list pane `size.split-list-min` + detail pane (~850px) with two columns | Sticky Decision card in the pane's side column |
| ≥1536 (`2xl`) | Full sidebar | Split view: list pane `size.split-list` + two-column detail | Same |

Two columns are decided by the detail's **container** width (`@container detail (min-width: 42em)`), never by viewport alone, so at 200% text or 400% zoom the detail falls back to one column with the Decision card first.

### 0.3 Large-text rules for step 3 (step-2 lessons applied)
Every A and R screen must pass at 390×844 with 200% text, at 195 CSS px (200% zoom) and at 320 CSS px:
1. **No horizontal scroll.** `overflow-wrap: anywhere` on every quote block, message, question, answer and note (C§35); `min-width: 0` on grid children; the HAM # is `nowrap`, nothing else is.
2. **The sticky bar holds only the primary under `22em`** (C§22). Back, Cancel, the consequence line and any non-primary decision button move into the flow (C§34, C§39). A normal Approve/Decline pair has no primary, so under 22em the bar disappears and the pair stacks in the Decision card, which is the first thing after the header. Bar ≤ 18% of the viewport (step-2 N6 measurement).
3. **No mid-word breaks:** decorative icons in choice cards (A6 categories, decline reasons have none) are dropped under `22em` (step-2 NM1). Reason and category labels wrap between words only (`overflow-wrap: break-word`, not `anywhere`, on labels).
4. **Full-screen sheets have no bottom nav** (C§39), so the bar is never under it.
5. **Short pages and sheets pin the bar to the bottom** (flex column, body `flex: 1`); no floating mid-screen bar.
6. **Container queries** for: the detail two-column split (42em), the Decision pair (22em), the sticky bars (22em), the choice grids (22em), the urgent banner sticky/static (22em), the requester two-column page (P§2 rules unchanged).
7. The urgent banner is **static** under 22em (C§40) and the bottom nav shows icon-only tabs under 20em (step-2 NM3), so app bar + banner + bar never take more than about a third of the viewport.

### 0.4 Status language for step 3
- **Staff chips** (C§5, `tokens.json › status.project`): Awaiting Approval (attention, `hourglass`) · Approved (info, `badge-check`) · Rejected (neutral, `circle-x`) · Reconsideration Pending (attention, `rotate-ccw`) · Cancelled (neutral, `ban`). **Rejected · Final** = Rejected chip + reason line "Final" (`type-small`, `text.secondary`), never a new chip.
- **Urgent chip** (`status-priority-urgent-*`, `siren`) before the status chip. Reason lines after it: "Not yet certified" (Board-approved, Q-160) · none once certified. When a pastor leaves it for normal review the chip is removed everywhere.
- **Requester chips:** C§26a.
- **Markers** (C§28, `type-small`, 16px icon + word): `message-circle-question` "Question open · 2 days" · `message-circle` "New answer" (`tone.attention.fg`, only for the asker) · `timer` "Undo until 3:45 PM" (decider) / "Decision pending" (others) · `user-round-check` "Yours" (`tone.attention.fg`) / "Goes to Pastor Ruth A." / "Goes to the Board" · `phone-outgoing` "Call to share a decision" (`tone.attention.fg`, Director/AD) · `calendar-clock` "Can ask until Oct 20" · `rotate-ccw` "After reconsideration" (Decided tab). Existing: `copy` "Earlier request", `image` "4 photos", `phone` "Updates by phone".

### 0.5 Names in leadership copy (Q-170, Q-171)
- `{requester}` = "the requester" (sentence start: "The requester") until this viewer opens **Show contact details** on this page; then the first name ("Doris"). The Director always sees the first name (reveal not logged, Q-024). The swap happens in place, without re-layout beyond the text itself; no announcement (the reveal already moved focus to the contact heading).
- Button accessible names use the neutral form always ("Ask the requester a question about HAM #047") so they don't change under the user's cursor.
- Lists, cards, toasts, banners, `<title>` and Inbox rows: HAM # + category only, never a name (Q-132). Decider names in rows use the short form "Pastor Ruth A.".
- The requester never sees who decided: R-screens say "we", "HAM", "our pastors or Board".

### 0.6 Text fields in this step
- App textareas: label `type-label`, hint `type-small` `text.secondary` **above** the field, `type-body` input text, auto-grow, `min-height` by rows. Requester textareas: C§10 at requester sizes (label `type-h3`, hint `type-body`, `type-body-lg`, `control-lg` minimum).
- Soft limits (no hard `maxlength`): question 500, answer 1,000, reconsideration note 1,000, decline message 600 (UX A3), "Why approved" 200 *(proposed)*. Counter "412 of 500" (`type-small` / `type-body` on requester pages, `text.secondary`, `tabular-nums`, right-aligned under the field) appears at 90%; over the limit it turns `tone.danger.fg` with `circle-alert` and the submit shows the field error. Announced politely once at 90%.
- Prefilled decline message: under the field, `text.tertiary` `type-small` "Suggested wording for 'Family or others may be able to help'. Edit it as you like." (C§10 "prefilled" note).

### 0.7 Impersonation-blocked treatment (Q-172)
While acting as someone else: every decide, certify, not-urgent, undo, take-over, ask, withdraw, record-answer, record-reconsideration and told-by-phone control is **removed** and replaced by one `.locked-note` in the Decision card: `lock` 16px + "Decisions and questions can't be recorded while acting as someone else." (`type-small`, `text.secondary`). **Change category** stays available. The sticky bar is not rendered. The impersonation banner (C§1) stays under the app bar. If a sheet was open when impersonation started (another tab), its submit returns the same line as an `inline-alert--attention` in the sheet footer, and the text is kept.

---

## 1. A1 Request detail with the Decision card (extends L2)

### 1.1 Anatomy and DOM order (all widths)
1. Header (L2 anatomy): chips row (Urgent + reason line, status) → h1 "HAM #047 · Roof or ceiling" → meta lines. Header actions (≥1024, right-aligned): **Ask for more photos** (Secondary) · **More ▾** (C§31). Pastors and Board rep see no More; Director/AD More holds **Change category…**, **Record a request to reconsider…** (Rejected, window open), **Close…** (Approved / Reconsideration Pending, "requester withdrew" only).
2. **Decision card** (C§33) — in the side column at two columns, but always here in DOM order.
3. **Reconsideration banner** (Reconsideration Pending only): `inline-alert--attention`, `rotate-ccw`, title "The requester asked us to reconsider · Oct 10" (`type-label`), then their note as a §35 quote block captioned "What they told us" or the line "(no note)" in `text.secondary`, then "Asked on the request page" / "Asked by phone · recorded by Marcus Bell".
4. Earlier-request alert (L5; rows now carry the decision chip + reason label, Q-167).
5. **Why it's urgent** (urgent only): its own block, not a card: `h2` "Why it's urgent" with `siren` 20px `tone.danger.icon` → reason label (`type-label`) → the requester's words (§35 quote, caption "In their words"). Left `size.accent-bar` in `tone.danger.icon` on the block, padding-inline-start `space-4`. Never merged with What's needed (step-2 N-M1).
6. What's needed · 7. Safety at the home · 8. Photos (read-only tiles) · 9. **Questions and answers** (C§38) · 10. The home · 11. Visits and contact preference · 12. Requester & contact (C§25) · 13. History (C§16, with the decision entries of 1.6).

Sections are `space-8` apart, heading → content `space-3` (L2). At 390 sections 10–13 are collapsible regions (L2); Questions and answers is open when it has an open question or a new answer, collapsed otherwise.

### 1.2 390 · Pastor · normal request, awaiting
```
┌ app bar: ‹ Requests · HAM #047 ────── (🔔2) ┐
│ (⌛ Awaiting Approval)                       │ chip, size.chip
│ HAM #047 · Roof or ceiling                  │ h1 type-h1
│ Sent Oct 1, 9:14 AM · 5 days                │ type-small text.secondary
│ Email confirmed · Updates by email          │
│ ┌▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔┐ │ accent bar tone.attention.icon
│ │ Decision               waiting 5 days   │ │ h2 type-h3 · type-small
│ │ Any pastor, or the Board rep for the    │ │ type-body
│ │ Board. One decision is needed.          │ │
│ │ ? Waiting on the requester's answer ·   │ │ marker--attention (only if open)
│ │   asked by Andre W. · 2 days            │ │
│ │ [ Ask a question ]                      │ │ Secondary md
│ └─────────────────────────────────────────┘ │
│ ⧉ Earlier request found (1) … [View]        │ L5 alert
│ What's needed                               │ h2
│ ┃ "Water comes through my bedroom…"         │ quote block
│ Safety at the home …                        │
│ Photos (4) [▢][▢][▢]                        │
│ Questions and answers (1) ▾                 │
│ ▸ The home  ▸ Visits  ▸ Requester 🔒  ▸ History │
│                                  space-8    │
├─────────────────────────────────────────────┤ action bar (C§22), shadow-bar-top when scrolled
│ [ ✓ Approve… ]        [ ✕ Decline… ]         │ C§34 pair: 2 × Secondary lg, 1fr 1fr, gap space-3
├─────────────────────────────────────────────┤
│  ⌂ Home   ▤ Requests   ✉ Inbox   ◯ Me        │ bottom nav
└─────────────────────────────────────────────┘
```
- Gutters `space-4`. Card top margin `space-4` after the meta. The bar sits directly above the bottom nav; the bottom nav hides on scroll-down (C§2) and the bar follows it down.
- **Urgent variant:** the chips row reads `(siren Urgent) (⌛ Awaiting Approval)`; the card's accent bar is `tone.danger.icon`; state line "Urgent: needs a pastor to certify. Any pastor can approve it directly." (`type-body`, `siren` icon not repeated); the card's secondary row is **Ask a question** + **More ▾** (More: "Not urgent: leave for normal review…"). The bar holds **Approve as urgent…** (Primary lg, `2fr`) + **Decline…** (Secondary lg, `1fr`). Directly under the card: the Why it's urgent block (1.1 item 5).
- **Board rep:** the pair reads **Board approved…** / **Board didn't approve…** (same C§34 pair, no icons change). On an urgent request the card adds `type-small` `text.secondary` "Only a pastor can certify urgency. The Board can approve it; a pastor can certify it later."
- **Director/AD:** state line "With the pastors and Board since Oct 1 (5 days)." (urgent: "Waiting for a pastor to certify. You'll be alerted when it's approved."). Actions: **Ask a question** (Secondary md) + **More ▾**. No bar.
- **Administrator:** state line only, no actions area, no bar.
- **Dual role (Pastor + Board rep):** the pair reads **Approve…** / **Decline…**; the route is chosen in the sheet (Q-164).

**390 at 200% text / 195 px:** the bar's container is under 22em, so the normal pair **leaves the bar**; the card shows the pair stacked full width (Approve first, `control-lg`, gap `space-2`) above Ask a question. Urgent: the bar keeps **Approve as urgent…** only (full width, 1–2 lines), and **Decline…** is full width in the card. The bottom nav is icon-only (step-2 NM3). Measured targets: bar ≤ 18% of the viewport; no horizontal scroll.

### 1.3 390 · after a decision: pending, decided, final, reconsideration
```
Decider, inside the undo window            Other approver, same moment
┌▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔┐        ┌▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔┐
│ Decision                         │        │ Decision                        │
│ (◈ Approved)                     │        │ (◈ Approved)                    │
│ You · pastoral route · 3:15 PM   │        │ Pastor Ruth Alvarez · pastoral  │
│ ┌ ⏲ Can be undone until 3:45 PM ┐│        │ route · Oct 6, 3:15 PM          │
│ │ Nothing has been sent to the  ││        │ ┌ ⏲ Decision pending (Pastor   ┐│
│ │ requester yet.                ││        │ │ Ruth, can be undone until    ││
│ │ [↶ Undo decision…]            ││        │ │ 3:45 PM)                     ││
│ └───────────────────────────────┘│        │ │ You can't decide while it can││
│ Why approved (leaders only) 🔒   │        │ │ still be undone.             ││
│ ┃ No family nearby; roof leak    │        │ └──────────────────────────────┘│
│ ┃ getting worse.                 │        │ [ Ask a question ]              │
│ Next: site assessment (HAM       │        └─────────────────────────────────┘
│ leadership).                     │
└──────────────────────────────────┘
```
- **Decider, pending:** accent bar `tone.info.icon`; chip = the new status (Approved / Rejected); decider line "You · pastoral route · 3:15 PM"; pending notice C§37 with **Undo decision…**; then the quote blocks that apply. **No sticky bar.** The toast "Approved · 3:15 PM · Undo until 3:45 PM" (`role="status"`, no Undo action, P§4) carries the Link **Next waiting request ›**.
- **Others, pending:** same chip and decider line, the "Decision pending (…)" notice, no decide buttons, no bar. **Ask a question** stays where the A1 table offers it (see OQ-2).
- **Decided (window passed):** accent bar per outcome; chip row; decider line; urgency line "Urgency certified" / "Urgency not certified" (`type-small`, `text.secondary`) when the request was urgent; for Board: "The Board's decision · recorded by Elder Samuel Okafor · Board decided Sun, Oct 4 · recorded Oct 6, 9:10 PM"; quote blocks: **What we told the requester** (rejections) and **Why approved (leaders only)** (approvals, `--leaders-only`; Administrator sees `--hidden`); closing line:
  - Approved: "Next: site assessment (HAM leadership)." (`type-small`, `text.secondary`)
  - Approved, urgent not yet certified (pastor viewer): `inline-alert--attention` compact "Urgent, not yet certified. The Board approved it; a pastor can certify it." + **Certify as urgent…** (Primary lg in the bar at <768; Primary md in the card at ≥1024) → A2c.
  - Rejected, window open: `calendar-clock` "The requester can ask us to reconsider until Tue, Oct 20." (`type-body`)
  - Rejected · Final: chip + reason line "Final"; `ban` "Final. The request is closed." (`type-body`, `text.secondary`)
- **Reconsideration Pending, the pastor who declined (or Board rep on the Board route):** accent bar `tone.attention.icon`, chip Reconsideration Pending, state line "The requester asked us to reconsider on Oct 10. It comes back to you." The bar holds the C§34 pair **Approve…** / **Decline…** (Board: **Board approved on reconsideration…** / **Board still didn't approve…**), both opening A9.
- **Reconsideration Pending, another pastor:** state line "Goes to Pastor Ruth Alvarez, who declined it. If she isn't available, you can take it over when you decide." The same pair shows; the accessible names are "Take over and approve HAM #046" / "Take over and decline HAM #046"; A9 opens with the take-over tick first.
- **Reconsideration Pending, Board route, pastor viewer / Director / AD:** "The Board is reconsidering this. Elder Samuel will record the outcome." No actions.
- **"Call to share a decision" (no-email requester, Director/AD):** under the decider line, `.marker--attention` `phone-outgoing` "Call to share a decision · not yet told" + **Tell by phone…** (Secondary md) → A11. Once told: `phone` "Told by phone · Marcus Bell · Oct 7, 6:40 PM" (`type-small`).

### 1.4 768
- Same order and card as 390 at full content width (rail beside it, gutters `space-6`). Pair in the sticky bar at the viewport bottom (no bottom nav), the bar's inner width capped at `size.form-max` and left-aligned with the content column. Sections expanded (L2 768 rule).

### 1.5 1024–1279 (full page) and 1280+ (split view): two columns, sticky Decision card
```
1280 · Elder Samuel · split view (rail) · HAM #047 awaiting
┌rail┬ list pane (split-list-min) ─────┬ detail pane (region "HAM #047 details", scrolls) ──────────────────────┐
│ ⌂  │ Requests                        │ (⌛ Awaiting Approval)                    [Ask for more photos]         │
│ ▤  │ [Awaiting approval 4][Waiting 1]›│ HAM #047 · Roof or ceiling                                              │
│ ✉  │ [🔍 Request number]              │ Sent Oct 1, 9:14 AM · Public form · Email confirmed · by email          │
│ ◯  │ [Category ▾] [Status ▾]          │ ┌ main (1fr) ─────────────────────────┐ ┌ side (size.aside), sticky ───┐ │
│    │ (Urgent) HAM #048 · Plumbing    │ │ What's needed                       │ │▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔│ │
│    │  Awaiting Approval · 2 h        │ │ ┃ "Water comes through my bedroom   │ │ Decision     waiting 5 days│ │
│    │▌HAM #047 · Roof or ceiling      │ │ ┃ ceiling when it rains…"           │ │ Any pastor, or you for the │ │
│    │  Awaiting Approval · 5 days     │ │ Safety at the home                  │ │ Board. One decision is     │ │
│    │  ? Question open · ▢ 4 photos   │ │ ⚠ Dogs or other animals             │ │ needed.                    │ │
│    │ HAM #046 · Yard or outside      │ │   "friendly but loud"               │ │ [ ✓ Board approved…      ] │ │
│    │  Awaiting Approval · 4 days     │ │ Photos (4) [▢][▢][▢][▢]             │ │ [ ✕ Board didn't approve…] │ │
│    │ HAM #044 · Electrical           │ │ Questions and answers (1)           │ │ [ Ask a question ]         │ │
│    │  Awaiting Approval · 6 days     │ │ Andre Whitfield asked · Oct 2       │ └────────────────────────────┘ │
│    │  ✉ New answer                   │ │ ┃ "Only when it rains, or also on…" │   ⧉ Earlier request (1) [View] │
│    │                                 │ │ The requester answered · Oct 3      │   The home · Visits            │
│    │                                 │ │ ┃ "Only when it rains…"             │   Requester & contact 🔒       │
│    │                                 │ │ History                             │   [Show contact details]       │
│    │                                 │ └─────────────────────────────────────┘                                │
└────┴─────────────────────────────────┴─────────────────────────────────────────────────────────────────────────┘
```
- **Grid:** the detail pane (padding `space-6`) is `container-name: detail`. At ≥42em: `grid-template-columns: minmax(0, 1fr) var(--ham-size-aside)`, `column-gap: space-6`, `row-gap: 0`; the header spans both columns. Main holds Why it's urgent, the reconsideration banner, What's needed, Safety, Photos (tiles 4-up in the ~456px main at 1280, 5-up at 1440), Questions and answers, History. Side holds the Decision card, then (not sticky) Earlier requests, The home, Visits, Requester & contact, each `space-6` apart, headings `type-h3`.
- **Sticky:** only the Decision card is sticky (`top: space-6` in the pane's scroll container; on the 1024–1279 full page `top: calc(size.appbar-height + space-6)`); the rest of the side column scrolls under it (the card has `bg.surface` and `shadow-sm` while stuck, so content passes cleanly beneath). Not sticky under `breakpoint.short` viewport height.
- **Decision card at this size:** padding `space-5`; the pair stacks full width at `control-md` (C§34), Approve first; Ask a question full-width Secondary md under it; More ▾ (Director/AD) as a full-width Secondary md. Urgent: **Approve as urgent…** Primary full width, **Decline…** Secondary full width, then Ask a question / More.
- **No bottom bar** at ≥1024. The toast is bottom-right (C§13) and carries **Next waiting request ›**, which loads the next row into the same pane (URL `?tab=…&id=…`) and moves focus to the pane h1.
- **Selecting a row** (split view) keeps the list scroll; the selected row uses C§28 selected style (`box-shadow` inset bar, step-2 minor 16).
- 1024–1279 full page: same two columns (the content box is ~696px ≥ 42em), main ~352px: photos 3-up.
- **1440 (QA width):** rail still (≤1535); pane ~1008px, main ~616px.

### 1.6 History entries added (C§16)
Icons in a 24px tone circle on the rail: Approved `badge-check` (info) · Declined `circle-x` (neutral) · Urgency certified `siren` (danger) · Urgency not certified `siren` (neutral) · Question asked `message-circle-question` (info) · Answer received `message-circle` (info) · Withdrawn `message-circle-x` (neutral) · Reconsideration asked `rotate-ccw` (attention) · Taken over `user-round-check` (info) · Category changed `tag` (neutral) · Told by phone `phone` (info) · **Undone**: shown as a nested entry under the decision it reverses ("Undone · Pastor Ruth Alvarez · 3:31 PM", `undo-2`, `text.secondary`), like an amendment; the original entry is never removed or struck through.

### 1.7 States (A1, A13)
| State | Visual |
|---|---|
| Loading | L2 skeleton (header + 3 sections, `bg.sunken`, P§10) + the Decision card skeleton (C§33) that resolves last; no bar until resolved |
| Error (whole page) | Neutral N§6 page, as step 2 |
| Error (decision only) | C§33 error state in the card; the rest of the page usable; no bar |
| Offline | `offline-banner` "You're offline. Showing what we had at 7:40 PM."; card actions `action.disabled.*` with the `cloud-off` reason line; bar buttons disabled with the same reason line shown in the card (never a tooltip) |
| Impersonation-blocked | 0.7 |
| Concurrency (someone decided first) | On submit the sheet closes; `inline-alert--attention` (`circle-alert`, `role="alert"`, focused, `tabindex="-1"`) directly **above** the Decision card: "Pastor Ruth Alvarez approved HAM #047 at 3:15 PM, while you were looking. Nothing was changed." + disclosure **See what you wrote** (their text in a §35 quote block, read-only). The card shows the real decision (pending or decided) |
| Status changed underneath | Same alert pattern: "HAM #049 was closed at 7:58 PM. Nothing was changed." |
| Undo refused (window passed) | In the undo sheet footer: `inline-alert--attention` "The 30 minutes to undo ended at 3:45 PM. The decision stands." + only **Close**; on close the card shows the decided state |
| Not ready (Submitted, Needs phone check; Director/AD only) | Card without accent bar, `type-body` `text.secondary` "Not ready for a decision yet: needs a phone check." |
| Reconsideration window ended | Rejected card closing line becomes `ban` "The requester could ask to reconsider until Oct 20. That time has passed, so the decline is final." |
| Empty (no questions) | Questions and answers section omitted |

### 1.8 Focus order (A1)
Skip link → app bar → (urgent banner actions) → h1 → header actions (Ask for more photos, More) → **Decision card** (h2 → marker → pair / primary → Ask a question → More → Undo) → reconsideration banner → L5 View → Why it's urgent → sections in order (Show contact details inside Requester & contact) → History → sticky bar buttons (<1024; they're the last DOM children of `main`, matching their visual place at the screen bottom). At two columns the DOM order is: header, Decision card, main column, rest of side column — so a keyboard user reaches the decision before the long content, as UX §9 requires.

---

## 2. Decision sheets

### 2.0 Frame (all sheets)
C§39 at every width: full-screen sheet <768 (no bottom nav), centered modal 768–1023, right side sheet ≥1024 (`size.modal-sm` unless noted). Header h2 + "HAM #047 · Roof or ceiling"; body fields `space-6` apart; consequence line in the footer (≥22em) or in the flow (under 22em); **one Primary** per sheet (the record button), Ghost **Cancel**. On success: sheet closes, toast (`role="status"`), the Decision card re-renders and its h2 takes focus. On failure: `inline-alert--danger` above the footer "That didn't go through. Your decision hasn't been recorded yet. Your text is still here." and the Primary stays enabled as the retry (label unchanged). Validation: C§30 error summary at the top of the body, focused; inline errors per field; radio-group errors on the legend's `aria-describedby`.

Shared blocks used by several sheets:
- **Route choice (dual role only, Q-164):** fieldset legend "Record this as" (`type-label`), two app-size choice cards 1 column: "My decision as a pastor" / "The Board's decision". **Nothing preselected**; required.
- **Board date (Board route):** "Date the Board decided" native date input (`control-md`), prefilled today, hint "It can't be in the future." (`type-small`).
- **Told by phone (no-email requests only):** a C§19 statement card (app size, unticked) "I've already told the requester by phone." with hint "If you don't tick this, the Director and Assistant Director get a card to call them."
- **Consequence line** copy is listed per sheet; the time in "at 3:45 PM" is the end of the undo window.

### 2.1 A2 Approve (also A2b Board approval)
- **Width:** `size.modal-sm`.
- **Body order:** [Route choice] → [Board date] → one-line summary (`type-body`): "Roof or ceiling · waiting 5 days" → field **"Why approved (leaders only)" (optional)**: single-line input `control-md`, hint "A few words for HAM leaders. The requester won't see this. Don't include personal details." (`lock` 16px before the hint) → [Told by phone].
- **Consequence line** *(proposed copy, reflects the undo window)*: "The requester's email goes out at 3:45 PM, after your 30 minutes to undo. Marcus and Andre are told so they can arrange the site visit." Open question on the request: add "The open question to the requester will be withdrawn." No email: "The requester doesn't use email. HAM leaders will get a card to call them, unless you've told them."
- **Primary:** **Approve HAM #047** · Board: **Record Board approval**. Ghost **Cancel**.
- **Result:** toast "Approved · 3:15 PM · Undo until 3:45 PM" + Link **Next waiting request ›**; card → pending (1.3).
- **Board on an urgent request (A2b-urgent):** an `inline-alert--info` at the top of the body: "The Board can approve this. Only a pastor can certify it as urgent, and a pastor can do that later." (Q-160). The Urgent chip then carries "Not yet certified".

```
390 · A2 full-screen sheet (normal text)          1280 · A2 side sheet (modal-sm), scrim over the split view
┌─────────────────────────────────────┐          ┌──────────────────────────────────────────┐
│ ✕  Approve HAM #047                 │          │ Approve HAM #047                      ✕  │ h2
├─────────────────────────────────────┤          │ HAM #047 · Roof or ceiling               │
│ Roof or ceiling · waiting 5 days    │          ├──────────────────────────────────────────┤
│                                     │          │ Roof or ceiling · waiting 5 days         │
│ Why approved (leaders only)         │          │ Why approved (leaders only) (optional)   │
│ (optional)                          │          │ 🔒 A few words for HAM leaders…           │
│ 🔒 A few words for HAM leaders. The │          │ [                                      ] │
│ requester won't see this.           │          │                                          │
│ [                                 ] │          │                                          │
│                  (body flex: 1)     │          ├──────────────────────────────────────────┤ sticky footer
├─────────────────────────────────────┤          │ ⓘ The requester's email goes out at      │
│ ⓘ The requester's email goes out at │          │ 3:45 PM, after your 30 minutes to undo.  │
│ 3:45 PM, after your 30 min to undo. │          │ Marcus and Andre are told…               │
│ [ Cancel ] [   Approve HAM #047   ] │          │               [ Cancel ] [Approve HAM #047]│
└─────────────────────────────────────┘          └──────────────────────────────────────────┘
```
**200% text:** the consequence line and a full-width Ghost **Cancel** become the last items of the body; the bar holds **Approve HAM #047** only.

### 2.2 A2u Approve as urgent (pastor)
- **Width:** `size.modal-sm`.
- **Body order:** h2 "Approve HAM #048 as urgent?" → **Why it's urgent** repeated: reason label (`type-label`) with `siren` `tone.danger.icon` + the requester's words in a §35 quote ("In their words") → `type-body`: "By approving as urgent, you certify that this is urgent. HAM can go ahead without waiting for the Board." → "Why approved (leaders only)" (optional) → [Told by phone] → Link button **Approve, but not as urgent** (`size.target-min` row, `text.link`; switches the sheet to A2 in place, keeping the note; focus moves to the new h2 and a polite status says "Switched to a normal approval.").
- **Consequence line:** "Marcus and Andre are alerted right away, on every channel. The requester's email goes out at 8:34 PM, after your 30 minutes to undo. If you undo, Marcus and Andre get a note."
- **Primary:** **Certify and approve** (Primary). Ghost **Cancel**.
- **Result:** toast "Approved as urgent · 8:04 PM · Undo until 8:34 PM"; the pastor urgent banner clears for all pastors; the Director/AD `--approved` banner appears at once (not held, Q-176).
- **Accessible name of the primary:** "Certify HAM #048 as urgent and approve".

### 2.3 A2n Not urgent: leave for normal review (pastor)
- **Entry:** More ▾ → "Not urgent: leave for normal review…". **Width:** `size.modal-sm`.
- **Body:** `type-body` "HAM #048 will stay with the pastors and Board as a normal request. The Urgent label comes off and it moves into the normal order. The requester's page switches to the normal wording. No one is emailed." No note field (Q-169). Not undoable (Q-176 doesn't list it), so no pending notice after.
- **Primary:** **Leave for normal review**. Result: toast "Left for normal review · 8:06 PM"; Urgent chip removed; pastor urgent banner clears; no Inbox update (Q-168).

### 2.4 A2c Certify as urgent (after a Board approval; pastor) — new in this spec
- **Entry:** the Approved card's attention line (1.3) or the pastor Home urgent card. **Width:** `size.modal-sm`.
- **Body:** h2 "Certify HAM #048 as urgent?" → Why it's urgent (as A2u) → `type-body` "The Board approved this on Oct 5. Certifying tells HAM it's urgent, so work can be arranged quickly."
- **Consequence:** "Marcus and Andre are alerted right away, on every channel."
- **Primary:** **Certify as urgent**. Result: toast "Certified as urgent · 8:10 PM · Undo until 8:40 PM"; pending notice in the card (Q-176 covers certification).

### 2.5 A3 Decline (also Board "didn't approve")
- **Width:** `size.modal-md` (the preview needs it).
- **Body order:** [Route choice] → [Board date] → **fieldset "Why can't HAM help?"** (legend `type-label`): five app-size choice cards, 1 column, **no icons**, labels `type-label`, `min-height: size.choice-card-min`: Family or others may be able to help · The owner or landlord is responsible for this repair · This isn't the kind of help HAM offers · We couldn't confirm what we needed · Another reason → **"What we'll tell the requester"** textarea (5 rows, prefilled on choosing a reason; "Another reason" leaves it empty with placeholder "Tell the requester why, kindly and simply.") + prefill note (0.6) + counter at 540/600 → **replace prompt** when the reason changes after an edit: an inline row under the field (not a dialog), `bg.sunken`, `radius-md`, padding `space-3`: "Replace your message with the suggested one?" [**Replace**] (Secondary sm) [**Keep mine**] (Ghost sm) → **Message preview** (C§36) → tip `type-small` `text.secondary` with `phone` icon: "If you know the requester, a call first can be kind. The email goes after your 30 minutes to undo." → [Told by phone].
- **Preview content (WYSIWYG with R15):** "We're sorry. After looking carefully at your request, we aren't able to help with this one." → "Here's why:" → quote with the message → "We know this isn't the answer you hoped for." → "If you think we've missed something, you can ask us to reconsider, once. You can ask until **Tue, Oct 20**." (Board route same wording: requesters never see the route.)
- **Consequence line:** "The requester's email goes out at 3:51 PM, after your 30 minutes to undo. They can ask us to reconsider once, until Tue, Oct 20." (Board: "…and the Board will reconsider if they ask.")
- **Primary:** **Decline HAM #046** (Primary, **not** Danger) · Board: **Record Board decision**. Ghost **Cancel**.
- **Errors:** "Choose why HAM can't help." (on the fieldset) · "Write what we'll tell the requester." (on the textarea).
- **Result:** toast "Declined · 3:21 PM · Undo until 3:51 PM"; card → pending (Rejected chip).

```
390 · A3 (normal text)                          1280 · A3 side sheet (modal-md)
┌─────────────────────────────────────┐        ┌───────────────────────────────────────────────────────┐
│ ✕  Decline HAM #046                 │        │ Decline HAM #046                                    ✕ │
├─────────────────────────────────────┤        │ HAM #046 · Yard or outside                            │
│ Why can't HAM help?                 │        ├───────────────────────────────────────────────────────┤
│ ┌ ◉ Family or others may be able ─┐ │        │ Why can't HAM help?                                   │
│ │   to help                       │ │        │ ◉ Family or others may be able to help                │
│ ┌ ○ The owner or landlord is      ┐ │        │ ○ The owner or landlord is responsible for this repair│
│ │   responsible for this repair   │ │        │ ○ This isn't the kind of help HAM offers              │
│ ┌ ○ This isn't the kind of help   ┐ │        │ ○ We couldn't confirm what we needed                  │
│ │   HAM offers                    │ │        │ ○ Another reason                                      │
│ ┌ ○ We couldn't confirm what we…  ┐ │        │ What we'll tell the requester                         │
│ ┌ ○ Another reason                ┐ │        │ Kind and plain. They read this in the email and on    │
│ What we'll tell the requester       │        │ their page. Don't include anyone else's details.      │
│ Kind and plain. They read this in   │        │ ┌───────────────────────────────────────────────────┐ │
│ the email and on their page.        │        │ │From what you've shared, it sounds like family or  │ │
│ ┌─────────────────────────────────┐ │        │ │others may be able to help… We hope your son is    │ │
│ │From what you've shared, it      │ │        │ │home soon.                                         │ │
│ │sounds like family or others…    │ │        │ └───────────────────────────────────────────────────┘ │
│ └─────────────────────────────────┘ │        │ Suggested wording for "Family or others…". Edit it.   │
│ Suggested wording… Edit it as you   │        │ ✉ What the requester will read                        │
│ like.                               │        │ ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐ │
│ ▾ What the requester will read      │        │   We're sorry. After looking carefully at your        │
│ ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐ │        │   request, we aren't able to help with this one.      │ type-body-lg
│   We're sorry. After looking        │        │   Here's why:                                         │
│   carefully at your request, we     │        │   ┃ From what you've shared…                          │
│   aren't able to help with this one.│        │   We know this isn't the answer you hoped for.        │
│   Here's why:                       │        │   …You can ask until Tue, Oct 20.                     │
│   ┃ From what you've shared…        │        │ └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘ │
│   …You can ask until Tue, Oct 20.   │        │ ☎ If you know the requester, a call first can be kind.│
│ └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘ │        ├───────────────────────────────────────────────────────┤
│ ☎ If you know the requester, a call │        │ ⓘ The requester's email goes out at 3:51 PM, after    │
│ first can be kind…                  │        │ your 30 minutes to undo. They can ask us to reconsider│
├─────────────────────────────────────┤        │ once, until Tue, Oct 20.                              │
│ ⓘ Email goes at 3:51 PM, after your │        │                    [ Cancel ] [ Decline HAM #046 ]    │
│ 30 minutes to undo. They can ask…   │        └───────────────────────────────────────────────────────┘
│ [ Cancel ] [   Decline HAM #046   ] │
└─────────────────────────────────────┘
```
**200% text:** reason cards 1 column (already), labels wrap between words; the preview disclosure stays open; the consequence line and Cancel move into the flow; the bar holds **Decline HAM #046** only.

### 2.6 U1 Undo (decider only, inside the window) — new
- **Entry:** **Undo decision…** in the pending notice. **Width:** `size.modal-sm`. Scrim click does nothing (explicit choice only); Esc = Keep.
- **Body:** h2 "Undo your approval of HAM #047?" (decline: "Undo your decline of HAM #046?"; certification: "Undo the urgent certification of HAM #048?") → `type-body` list (`ul`, `space-2`):
  - "Nothing has been sent to the requester. Their email is cancelled."
  - "HAM #047 goes back to Awaiting Approval, and anyone who can decide may decide it."
  - Urgent: "Marcus and Andre were already alerted. They'll get a note that it was undone."
  - "The decision and the undo stay in the history."
  → `type-small` `text.secondary` "You can undo until 3:45 PM."
- **Footer:** Ghost **Keep my decision** · Primary **Undo approval** / **Undo decline** / **Undo certification** (Primary, not Danger: undoing is safe and reversible by deciding again).
- **Result:** toast "Approval undone · 3:31 PM"; card back to the awaiting state; focus on the card h2. If the window has passed: 1.7 "Undo refused".

### 2.7 A4 Ask a question
- **Who:** Pastors, Board rep, Director, AD. **Width:** `size.modal-sm`.
- **Body:** (if a question is open) `inline-alert--info` compact: "Andre asked the requester a question 2 days ago and they haven't answered yet." + the question in a §35 quote → textarea **"What would you like to ask the requester?"** (4 rows; hint "One clear question works best. The requester sees exactly what you write. Don't include anyone else's details. Need photos? Use Ask for more photos instead."; counter at 450/500).
- **Consequence:** "The requester gets an email and a card on their request page. You'll hear when they answer."
- **Primary:** **Send question**. Result: toast "Question sent · 3:02 PM"; thread item (C§38) open; row marker.
- **No-email variant (Q-159/Q-162, arch `phone_answer`)** *(proposed layout)*: the consequence becomes "The requester doesn't use email. Call them to ask, then record what they said." Below the question field: the C§25 masked block (hidden → **Show contact details**, logged per L9; revealed: phone as `tel:` + **Call** Secondary lg, full width <1024) → textarea **"What did they say?" (optional)** hint "Leave empty if you couldn't reach them; the question stays open." → statement card "I spoke with the requester by phone." (required only when an answer is typed). Primary **Save question**.

### 2.8 A5 Record their answer (phone)
- **Entry:** **Record their answer** on an open thread item. **Width:** `size.modal-sm`.
- **Body:** the question (§35, caption "Andre asked · Oct 6") → C§25 masked block with **Call** → textarea **"What did they say?"** (required, 4 rows, counter at 900/1,000) → statement card "I spoke with the requester by phone." (required).
- **Primary:** **Save answer**. Result: toast "Answer saved · 6:40 PM"; thread "Answer taken by phone · Marcus Bell · Oct 7, 6:40 PM".

### 2.9 A6 Change category (Director, AD)
- **Entry:** More ▾ → **Change category…**. **Width:** `size.modal-md` at ≥768 (nine cards); full-screen <768.
- **Body:** fieldset legend "Category" → 9 app-size radio choice cards in `.choice-grid` (`minmax(min(100%, 12em), 1fr)`: 2 columns in the sheet at ≥768, 1 column at 390), R2 icons at `size.icon-lg` in `text.secondary` (`text.brand` selected), **icons dropped under 22em**; current category preselected with the `type-small` note "Current" under its label.
- **Consequence:** "Lists, notices and emails to leaders will use the new category. The requester's page shows it too. They aren't emailed."
- **Primary:** **Save category**. Before a different card is chosen, submitting shows the inline message "Choose a different category to save." on the fieldset (C§4: enabled button + explanation, instead of a silently disabled one). Allowed while impersonating.
- **Result:** toast "Category changed · 7:12 PM"; the h1 updates; History entry.

### 2.10 A9 Reconsideration decision (with take-over, Q-157)
- **Entry:** the pair on a Reconsideration Pending card. **Width:** `size.modal-sm` (approve) / `size.modal-md` (decline).
- **Body order:**
  1. **Take-over block** (only when the viewer isn't the original decider): `type-body` "This reconsideration goes to Pastor Ruth Alvarez, who declined HAM #046 on Oct 6." → statement card (required, unticked) "**Pastor Ruth** isn't available to decide this." → `type-small` `text.secondary` "Pastor Ruth will be told you've taken it over." Separated from the rest by `space-6` and a `border.subtle` rule (the one divider allowed).
  2. Context: the requester's note (§35, caption "What they told us · Oct 10") or "(no note)".
  3. [Board date] (Board route).
  4. **Approve mode:** textarea **"Reason"** (required, 3 rows) hint "A short reason for the record, for example 'No family nearby after all.' Leaders see this. The requester doesn't." → "Why approved (leaders only)" is **not** repeated (the Reason is leaders-only already) → [Told by phone].
     **Decline mode:** A3's reason cards + "What we'll tell the requester" + preview in the **final** wording (R18b: "We looked at your request again, and we're sorry, we're still not able to help with this one." … "You're welcome to send a new request in the future if things change.") → [Told by phone].
- **Consequence:** approve: "The requester's email goes out at 3:45 PM, after your 30 minutes to undo. Marcus and Andre are told so they can arrange the site visit." Decline: an `inline-alert--attention` compact in the footer (not the plain line): "This is final. The request will close and the requester can't ask again. They can send a new request in the future."
- **Primary:** **Approve HAM #046** / **Decline HAM #046 (final)**; with take-over: **Take over and approve** / **Take over and decline (final)** (accessible names add "HAM #046"). The primary may wrap to 2 lines at 390; it never truncates.
- **Errors:** "Tick to confirm Pastor Ruth isn't available." · "Add a short reason. Every reconsideration decision needs one." plus A3's.

### 2.11 A11 Tell by phone ("Call to share a decision"; Director, AD)
- **Width:** `size.modal-sm`. Body: h2 "Tell the requester by phone · HAM #050" → "What to say" (`type-label`) + a §35 quote with the script (approved: "Your request has been approved. Someone from HAM will call you to arrange a visit. The visit helps us plan; it doesn't yet promise the work." / declined: the message + "You can ask us to reconsider once, until Tue, Oct 20.") → C§25 masked block with **Call** → statement card "I told the requester by phone." (required).
- **Primary:** **Mark as told**. No answer: Ghost **Cancel**; the card stays with its age.

### 2.12 A12 Record a request to reconsider (phone; Director, AD)
- **Entry:** More ▾ on a Rejected request inside the window. **Width:** `size.modal-sm`. Body: textarea **"What did they say?" (optional)** (counter at 900/1,000) → statement card "The requester asked us by phone to reconsider." (required) → `type-small` "They can ask until Tue, Oct 20."
- **Consequence:** "It goes back to Pastor Ruth Alvarez, who declined it." / "It goes to the Board."
- **Primary:** **Record request to reconsider**.

---

## 3. A7 Requests list tabs

### 3.1 Tabs (C§29) by role
- Pastors, Board rep: **Awaiting approval** · **Waiting on requester** · **Reconsideration** · **Decided**.
- Director, AD: **Needs a phone check** · **Awaiting approval** · **Waiting on requester** · **Reconsideration** · **Decided** · **All**.
- Administrator: **Awaiting approval** · **Decided** · **All**.
- Each tab always renders with its count (0 included) so the row never shifts. Count pills `bg.sunken`, `type-chip` (fix step-2 minor 18: not 12px). At 390 the tab row scrolls inside itself with 24px fade masks and the current tab scrolled into view; at 200% text it still scrolls, the page never does.

### 3.2 Rows (C§28) per tab
| Tab | Line 1 | Line 2 | Line 3 markers | Sort |
|---|---|---|---|---|
| Awaiting approval | Urgent chip + HAM # · category | status chip (outline) + age | Question open · Earlier request · photos · Decision pending / Undo until | urgent first, then oldest |
| Waiting on requester | HAM # · category | status chip + "asked by Andre W. · 2 days" | New answer (asker only) | oldest question first |
| Reconsideration | HAM # · category | Reconsideration Pending chip + "asked Oct 10" | **Yours** (`tone.attention.fg`) or "Goes to Pastor Ruth A." / "Goes to the Board" | Yours first, then oldest |
| Decided | HAM # · category | outcome chip (+ "Final" reason line) + "Pastor Ruth A. · Oct 6" | Undo until 3:45 PM (decider) / Decision pending · Can ask until Oct 20 · After reconsideration · Call to share a decision (Dir/AD) | newest first |
- Decided tab: a filter-chip row above the list (C§10 filter chips, 36px pill / 48px hit): **All** · **Approved** · **Rejected** · **Final**; default last 12 months, **Show older** (Secondary md) at the end of the list.
- **1024–1279 table** (C§9, 52px rows, chips `outline`): Awaiting: Request · Status · Age · Notes. Waiting on requester: Request · Asked by · Waiting · Notes. Reconsideration: Request · Asked · Goes to · Notes. Decided: Request · Outcome · Decided by · Date · Notes. Numbers and dates right-aligned, `tabular-nums`.
- **≥1280:** split view (1.5); rows as above; the selected row opens in the pane.

```
390 · Pastor · Reconsideration tab
┌ Requests ───────────────────────────────┐
│ [Awaiting 4][Waiting 1][Reconsider 2]›  │ tabs, fade mask right
│ ┌─────────────────────────────────────┐ │
│ │ HAM #046 · Yard or outside          │ │
│ │ (↻ Reconsideration Pending) Oct 10  │ │ chip outline + type-small
│ │ ☺ Yours                             │ │ marker, tone.attention.fg
│ ├─────────────────────────────────────┤ │
│ │ HAM #039 · Electrical               │ │
│ │ (↻ Reconsideration Pending) Oct 8   │ │
│ │ ☺ Goes to Pastor David K.           │ │ marker, text.secondary
│ └─────────────────────────────────────┘ │
├ bottom nav ─────────────────────────────┤
```

### 3.3 States
- **Empty** (C§12 compact inside the list card, `inbox` illustration at full size only when the tab is the whole page): Waiting on requester "No questions are waiting for an answer." · Reconsideration "No one has asked us to reconsider." · Decided "No decisions yet. Approved and declined requests will show up here." At ≥1280 the detail pane shows the same empty state centered.
- **Filtered-empty:** compact + **Clear filters** Link.
- **Loading:** 6 skeleton rows at `size.list-row-min`. **Error:** `inline-alert--danger` "Couldn't load requests." + **Try again**, tabs stay usable. **Offline:** banner + cached rows + "As of 7:40 PM".
- **Focus:** h1 → tabs → filter chips (Decided) → search → filters → rows → Show older.

---

## 4. A8 Home, Inbox and the urgent banners

### 4.1 Pastor Home (C§27 attention cards, fixed group order)
```
390 · Pastor Ruth · Home
┌ app bar ─────────────────────────────────┐
│ ▌siren Urgent request needs a pastor ·    │ C§40 --needs-pastor (sticky ≥22em)
│  HAM #048 Plumbing or water               │
│  [Open] [I've seen this]                  │
├───────────────────────────────────────────┤
│ Hi Ruth · 4 things need you.              │ type-h1
│ ┌▌(Urgent) HAM #048 · Plumbing or water ─┐│ urgent card: bar tone.danger.icon
│ │ waiting 2 h                            ││ type-small
│ │ [          Review                    ] ││ Primary md, full width (first only)
│ └────────────────────────────────────────┘│
│ ┌▌↻ Asked to reconsider · HAM #046 ──────┐│ bar tone.attention.icon
│ │ Yard or outside · you declined it Oct 6││
│ │ [          Review                    ] ││ Secondary md
│ └────────────────────────────────────────┘│
│ ┌▌✉ Answer received · HAM #047 ──────────┐│ bar tone.info.icon
│ │ Roof or ceiling                        ││
│ │ [          Open                      ] ││
│ └────────────────────────────────────────┘│
│ ┌▌⌛ 4 requests waiting for a decision ──┐│ bar tone.attention.icon
│ │ oldest 6 days                          ││
│ │ [        Open list                   ] ││
│ └────────────────────────────────────────┘│
├ bottom nav ───────────────────────────────┤
```
- Groups: 1 Urgent (one card per request; cap 3 + "N more urgent ›" Link; only the first **Review** is Primary, the rest Secondary — step-2 new minor 1) · includes Board-approved-not-certified urgent requests: "Urgent · HAM #048 · Approved by the Board · not yet certified" [**Review**] · 2 Reconsideration for you · 3 Answer received (asker) · 4 Waiting for a decision (summary card; 1–2 requests are listed as rows instead).
- Cards gap `space-3`, groups `space-6`; context lines `type-small` `text.secondary` with `&nbsp;` in ages ("waiting 2&nbsp;h").
- ≥1024: cards use Secondary sm right-aligned actions (C§27); `.home-grid` 2fr/1fr at ≥1280, cards in the left column.
- Empty: C§12 "Nothing needs a decision right now. We'll let you know when a request comes in."
- **Board rep:** no urgent group (sees urgent requests in the list only); group 2 is "Asked to reconsider (Board) · HAM #045 · the Board declined it Sep 30".

### 4.2 Director / AD Home
- Actionable (counted): **Call to share a decision** cards (`phone-outgoing`, bar `tone.attention.icon`): "Call to share a decision · HAM #050 · Ramps, rails or grab bars · decided Oct 6" [**Open**] → A1 with A11 open; **Answer received** (if they asked); step-2 phone-check cards.
- Awareness (C§27 `--muted`: no bar, no button, not counted): "Waiting for a decision (4) · oldest 6 days · owner: pastors & Board" · "Reconsideration (1) · owner: Pastor Ruth A." · "Approved, waiting for a site visit (2)" · "Waiting on requester (1)".
- Banners: C§40 `--approved` and `--undone`.

### 4.3 Inbox
- **Needs response** mirrors the Home cards (same components, list layout). **Updates** rows (no badge): "HAM #047 approved · Pastor Ruth A." · "HAM #046 declined · Pastor Ruth A." · "Pastor David K. took over the reconsideration of HAM #046" · "The urgent approval of HAM #048 was undone · Pastor Ruth A." (`undo-2`, `tone.attention.fg` title). Decision updates appear only once the undo window has passed (Q-176); "left for normal review" never appears (Q-168).
- Row: `size.target-min` minimum, padding `space-3` / `space-4` (step-2 minor 19), 20px icon, title `type-label`, time `type-small` `text.secondary`, `border.subtle` separators.

### 4.4 Urgent banners
C§40. Order under the app bar: urgent banner → impersonation banner. At 390 the text wraps to 2 lines and actions sit on their own row (≈ 129px, step-2 N5); under 22em it's static. `--approved` (Director/AD) sample: "Urgent request approved · HAM #048 Plumbing or water. Arrange the site visit." [**Open**] [**Got it**].

---

## 5. Requester screens (R13–R19)

### 5.0 Frame
R10 rules (S R10): public shell with the church logo, no nav; eyebrow; "Hi {first name}" (`type-h3`, `text.secondary`); h1 "Your request · HAM #047"; `type-body-lg`, `control-lg`, chips at `size.chip-lg`; sections `space-10` apart; ≥1280 two columns `3fr 2fr` in `size.requester-wide-max` (left: status card, things we need, decision content; right: your request, questions and answers, how to reach us). **During the undo window the requester page does not change** (the email is held; see OQ-1).

**Status card (C§26) per state** (accent bar = tone `-icon`):
| State | Chip row | Sentence (`type-body-lg`) | Then |
|---|---|---|---|
| Awaiting + question | (⌛ Being reviewed) info | "Our pastors or Board are reviewing your request." | "We have a question for you below. Your answer helps us decide." |
| Approved | (✓ Approved) success | "Good news: your request is approved." | What happens next (R14) |
| Approved, urgent certified | (siren Urgent) (✓ Approved) | same | urgent next steps |
| Not approved | (⊗ Not approved) neutral | "We're sorry. After looking carefully at your request, we aren't able to help with this one." | "Here's why:" + quote + "We know this isn't the answer you hoped for." |
| Taking another look | (↻ Taking another look) info | "We're taking another look at your request." | "We'll let you know what we decide, by email and on this page." |
| Closed (final after reconsideration) | (⊘ Closed) neutral | "We looked at your request again, and we're sorry, we're still not able to help with this one." | "Here's why:" + quote + new-request line |
| Closed (window passed) | (⊘ Closed) neutral | "We weren't able to help with this request." | same |

### 5.1 R13 HAM has a question (action card)
```
390 · R10 with an R13 card
┌ [church logo] ───────────────────────┐
│ Hi Doris                             │ type-h3 text.secondary
│ Your request · HAM #047              │ h1
│ ┌▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔┐ │ status card, bar tone.info.icon
│ │ (⌛ Being reviewed)                │ │ chip-lg
│ │ Our pastors or Board are          │ │
│ │ reviewing your request.           │ │
│ │ We have a question for you below. │ │
│ └───────────────────────────────────┘ │
│ Things we need from you (1)          │ h2
│ ┌▌HAM has a question for you ───────┐ │ action card, bar tone.attention.icon
│ │ From HAM · Oct 6                  │ │ figcaption type-body text.secondary
│ │ ┃ Does the water come in only     │ │ quote block, type-body-lg
│ │ ┃ when it rains, or also on dry   │ │
│ │ ┃ days?                           │ │
│ │ Your answer                       │ │ label type-h3
│ │ ┌───────────────────────────────┐ │ │ textarea control-lg min, 4 rows
│ │ │                               │ │ │
│ │ └───────────────────────────────┘ │ │
│ │ 🎤 Tip: tap the microphone on your │ │ type-body text.tertiary, mic icon
│ │ keyboard to speak instead.        │ │
│ │ [          Send answer          ] │ │ Primary lg, full width
│ │ Prefer to talk? Call              │ │ type-body, tel: link
│ │ (305) 555-0100 and mention HAM    │ │
│ │ #047.                             │ │
│ └───────────────────────────────────┘ │
│ Your request …                       │
```
- **Button placement:** **Send answer** sits in the card directly after the textarea at every width; **no sticky bar on R10 for question cards** (the R10 mirror rule is not used here: a bar button far from its textarea would submit text the person can't see; with the keyboard open, the button scrolls into view under the field). If there are several open questions, each card has its own **Send answer**; only the first is Primary, the rest Secondary lg (one Primary per screen).
- **Counter:** at 900 "900 of 1,000" (`type-body`).
- **Sending:** button loading, `aria-busy`, width locked; textarea read-only.
- **Sent:** the card keeps its place and changes in place: bar turns `tone.success.icon`; `circle-check` 24px `tone.success.icon` + "Thank you. We've got your answer." (`type-h3`, `tabindex="-1"`, focused) + her answer (§35, caption "Your answer · Oct 7, 9:12 AM") + "Want to add something? Call us at (305) 555-0100." On the next visit it lives under **Your request › Questions and answers** (C§38 requester variant).
- **Failed:** `inline-alert--danger` inside the card above the button: "We couldn't send your answer just now. It's still here. Please try again." Text kept; button stays enabled.
- **Offline:** button `action.disabled.*` + reason directly above it with `cloud-off`: "You're offline. Your answer is saved on this device. You can send it when you're connected." (`type-body`).
- **Withdrawn while typing:** on submit, the card is replaced by `inline-alert--info` (not error): "Thanks. We don't need this answer anymore, because we've made a decision. See the update above." Focus on it.
- **200% text:** card padding `space-4`; quote and textarea full width; the button is full width and 1 line; no horizontal scroll.
- **≥1280:** the card is in the left column under the status card; textarea max `size.form-max`.
- **Focus order:** h1 → status card → "Things we need" h2 → question → Your answer → Send answer → phone link → rest.

### 5.2 R14 Approved
- Status card, accent `tone.success.icon`; on the first visit after approval, `circle-check-big` at `size.icon-xl` in `tone.success.icon` above the chip (decorative; no animation beyond the normal enter).
- "What happens next" (`type-label` heading) + numbered list (`type-body-lg`, `space-2`): 1 "Someone from HAM will call you to arrange a visit to look at the work." 2 "The visit helps us plan; it doesn't yet promise the work." 3 "You don't need to do anything right now."
- Urgent certified: the Urgent chip before Approved + `inline-alert--attention` "Because it's urgent, HAM's leaders have been told right away and will contact you soon. If anyone is in danger, call 911." (911 as `tel:`).
- Photo line: `inline-alert--info` compact "Photo uploads are closed for now. If HAM needs more, we'll ask."
- No primary, no bar. Page is short: content only (no pinned empty bar).

### 5.3 R15 Not approved (+ reconsider block)
```
390 · R15                                   1280 · R15 (requester-wide-max, 3fr | 2fr)
┌ [church logo] ──────────────────────┐     ┌──────────────────────────────────────────────────────────┐
│ Hi Doris                            │     │ Hi Doris                                                  │
│ Your request · HAM #046             │     │ Your request · HAM #046                                   │
│ ┌▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔┐ │     │ ┌▔ status card ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔┐  Your request        │
│ │ (⊗ Not approved)                │ │     │ │ (⊗ Not approved)                   │  Yard or outside     │
│ │ We're sorry. After looking      │ │     │ │ We're sorry. After looking …       │  "please mow my…"    │
│ │ carefully at your request, we   │ │     │ │ Here's why:                        │  Photos (2)          │
│ │ aren't able to help with this   │ │     │ │ ┃ From what you've shared…         │                      │
│ │ one.                            │ │     │ │ We know this isn't the answer you  │  How to reach us     │
│ │ Here's why:                     │ │     │ │ hoped for.                         │  (305) 555-0100      │
│ │ ┃ From what you've shared, it   │ │     │ └────────────────────────────────────┘  ham@…               │
│ │ ┃ sounds like family or others  │ │     │ Ask us to look again                                      │
│ │ ┃ may be able to help… We hope  │ │     │ If you think we've missed something, you can ask us to    │
│ │ ┃ your son is home soon.        │ │     │ reconsider, once.                                         │
│ │ We know this isn't the answer   │ │     │ 📅 You can ask until Tue, Oct 20.                         │
│ │ you hoped for.                  │ │     │ [ Ask us to reconsider ]   Or call us at (305) 555-0100.  │
│ └─────────────────────────────────┘ │     └──────────────────────────────────────────────────────────┘
│ Ask us to look again                │ h2
│ If you think we've missed           │ type-body-lg
│ something, you can ask us to        │
│ reconsider, once.                   │
│ 📅 You can ask until Tue, Oct 20.   │ type-body-lg, date weight 600, calendar icon
│ [     Ask us to reconsider        ] │ Secondary lg, full width <768
│ Or call us at (305) 555-0100.       │ tel: link
│ We're glad to talk it through.      │
│ Your request …  How to reach us …   │
```
- Status card accent `tone.neutral.icon`; chip neutral (never red). "Here's why:" is the `figcaption` of the §35 quote (requester sizes).
- **Deadline line:** `calendar-clock` 20px `text.secondary` + "You can ask until " + `<time datetime="2026-10-20T23:59:59-04:00">Tue, Oct 20</time>` at `font-weight-semibold`. The date never wraps internally (`nowrap` on the `<time>`).
- **Ask us to reconsider:** Secondary lg (not Primary, UX R15), full width <768, auto width ≥768; it's a link to R16. It's the page's only filled-looking action, but not a Primary: there is no Primary on R15.
- ≥768: button auto width, with the phone line beside it at ≥1024 when it fits (wraps below otherwise).
- **200% text:** everything in one column; the button is full width; the date line wraps between words, the date itself stays whole.
- Focus: h1 → status card → "Ask us to look again" h2 → Ask us to reconsider → phone link.

### 5.4 R16 Ask us to reconsider (page)
- Public card (S R11 shape, `size.form-max`); h1 "Ask us to reconsider" → `type-body-lg` "We'll look at your request again. You can only ask once, so if there's anything new or anything we may have missed, please tell us." → textarea **"Anything you'd like us to know? (optional)"** (label `type-h3`, 5 rows, `type-body-lg`, counter at 900/1,000) → mic tip (`type-body`, `text.tertiary`) → `calendar-clock` "You can ask until Tue, Oct 20." (`type-body`, `text.secondary`) → Link **Not now** (back to R10), `size.target-min` row, **in the flow at every width <1024** (so the bar only holds the primary).
- **<1024 action bar:** **Send my request to reconsider** (Primary lg, full width; may take 2 lines at 390 with 200% text, still ≤ 18% of the viewport). Short page: the card is a flex column so the bar pins to the viewport bottom (step-2 M2).
- **≥1024:** the card holds everything; **Not now** (Ghost) left and **Send my request to reconsider** (Primary) right at the card's end. **≥1280:** + aside (`size.aside`) "Good to know": "What happens next" numbered list (We'll look at it again · We'll email you and update your page · You can only ask once) + "Prefer to talk? {church.hamPhone}".
- **Sending:** primary loading + locked after one tap (double-send guard). **Failed:** `inline-alert--danger` above the field "We couldn't send your request just now. Please try again, or call us at (305) 555-0100." **Already asked** (other tab) → R17 without error. **Window passed** (stale page) → R18c with `inline-alert--info` "The time to ask us to reconsider has passed. You're welcome to send a new request, or call us."
- Focus: on load the h1; order h1 → intro → textarea → Not now → Send.

### 5.5 R17 Taking another look (R10 after sending)
- At the top of the content, before the status card: `inline-alert--success` (`circle-check`) "Thank you. We've received your request to reconsider." (`tabindex="-1"`, focused on arrival, `role="status"`). Shown on arrival only; later visits omit it.
- Status card accent `tone.info.icon`, chip "Taking another look" (info, `rotate-ccw`), sentence and next line from 5.0.
- "What you told us" (`type-label`) + her note as a §35 quote (caption "Sent Oct 10"), or nothing if she left it empty.
- No action, no bar.

### 5.6 R18 Outcomes
- **R18a Approved after another look:** as R14; sentence "Good news: after taking another look, we've approved your request."
- **R18b Still not approved (final):** status card accent `tone.neutral.icon`, chip "Closed" (`ban`); sentence; "Here's why:" + quote; `type-body-lg` "You're welcome to send a new request in the future if things change." → **Ask for help** (Secondary lg, full width <768; links to R1; UX says Ghost — Secondary is used so it reads as a real button on a page with no other action) → "Questions? Call us at (305) 555-0100." → footer `type-body` `text.secondary` "This page will stay available until {date}." (the final close + `{rules.REQUESTER_ACCESS_AFTER_CLOSE}`, Q-116; the date is `nowrap`).
- **R18c Window passed:** as R18b with the sentence "We weren't able to help with this request." and the reason; no reconsider button.

### 5.7 R19 States (summary)
| State | Visual |
|---|---|
| Answer / reconsider send failed | `inline-alert--danger` above the button, text kept, auto-retry once, then the button again |
| Offline | `offline-banner` with the as-of time; action buttons disabled with the `cloud-off` reason line above them |
| Question withdrawn | card removed; mid-typing → the info alert in 5.1 |
| Already asked (another tab) | R17 |
| Stale reconsider after the window | R18c + the info alert in 5.4 |
| Link expired after a final close | R11a (step 2) |
| Loading | skeleton status card + 3 lines (S R10) |

---

## 6. Emails (visual deltas from S§5)
- Every requester email: neutral subject "Update on your HAM request #047"; one Primary-style button **Open my request page**.
- **E10 / E13 (decline):** the message sits in a quoted block inlined from tokens: `bg.sunken` fill, 4px left border `border.strong`, padding `space-3` / `space-4`, `type-body-lg` values, preceded by "Here's why:". The deadline date in E10 is bold. No red anywhere.
- **E9 / E12 (approved):** the three "What happens next" lines of R14, including the §11 line.
- **E8 (question):** the question in the same quoted block, caption "Our question:".
- Leadership emails (L-E5 … L-E11) stay text-only per S§5: HAM # + category + link, never a reason, question, answer or name.

---

## 7. Accessibility names and focus (reference)

| Control | Visible label | Accessible name |
|---|---|---|
| Decision pair (pastor) | Approve… / Decline… | "Approve HAM #047" / "Decline HAM #047" |
| Decision pair (Board) | Board approved… / Board didn't approve… | "Board approved HAM #047" / "Board didn't approve HAM #047" |
| Urgent primary | Approve as urgent… | "Approve HAM #048 as urgent" |
| Take-over pair | Approve… / Decline… | "Take over and approve HAM #046" / "Take over and decline HAM #046" |
| Certify later | Certify as urgent… | "Certify HAM #048 as urgent" |
| Undo | Undo decision… | "Undo the approval of HAM #047" (decline: "Undo the decline of HAM #046") |
| Ask a question | Ask a question | "Ask the requester a question about HAM #047" |
| Record their answer | Record their answer | "Record the requester's answer to the question asked Oct 6" |
| Withdraw | Withdraw | "Withdraw the question asked Oct 6" |
| Tell by phone | Tell by phone… | "Tell the requester by phone about HAM #050" |
| Sheet ✕ | ✕ | "Close" (returns focus to the trigger) |
| Reconsider (requester) | Ask us to reconsider | same (link) |
| Send answer (several cards) | Send answer | "Send your answer to the question from Oct 6" |

- **Regions:** Decision card `section aria-labelledby`; at two columns the side column is `<aside aria-label="Decision and request facts">` inside the detail region; message preview `role="region"`; urgent banner `role="region" aria-label="Urgent"`.
- **Live regions:** toasts `role="status"`; concurrency alert `role="alert"` + focus; prefill "Message filled in from the reason you chose. You can edit it." (polite); counters at 90% (polite, once); undo-window end (polite); preview `aria-live="off"`.
- **Focus after actions:** sheet open → sheet h2; sheet close/cancel → trigger; recorded/undone/taken over → Decision card h2; requester send → the confirmation text.
- **Targets:** every control ≥ `size.target-min`; pair buttons ≥ `space-2` apart (they use `space-3`); Link buttons in sheets get the 48px row.
- **Contrast:** all pairs used here are in the README table: `text.primary` on `bg.sunken` (quotes), `tone.*.fg` on `tone.*.bg` (chips, alerts), `text.secondary` on `bg.surface-raised` (sheet hints), `text.tertiary` on `bg.surface-raised` (prefill note). The dashed preview border and the accent bars are decorative. No new colour pairs.
- **Colour never alone:** every chip, marker and alert has an icon and words; Approve/Decline differ by words and icon shape, not colour.
- **Reduced motion:** no sheet slide (fade only), no chevron rotation, no row fade.

---

## 8. Frontend checklist (ham-frontend-engineer)
- [ ] Add classes per C§33–§40: `.decision-card` (+ state modifiers `--awaiting`, `--urgent`, `--pending`, `--approved`, `--rejected`, `--reconsideration`, `--readonly`), `.decision-card__actions`, `.decision-pair` (+ `--urgent`), `.quote-block` (+ `--leaders-only`, `--muted`, `--hidden`), `.message-preview`, `.qa-thread`, `.sheet--side` (+ `--sm`, `--md`), `.urgent-banner--needs-pastor|--approved|--undone`, `.urgent-banner-slot` (size container).
- [ ] Detail container: `.request-detail { container: detail / inline-size }`; two columns at `@container detail (min-width: 42em)` with `minmax(0,1fr) var(--ham-size-aside)`; Decision card sticky only there and only when `(min-height: 480px)` (`breakpoint.short`).
- [ ] Requests split view at 1280–1535 renders the sidebar as the rail (P§2 v1.4); full sidebar at ≥1536.
- [ ] Decision buttons rendered twice (card + <768 bar) from one include; container query on the bar at `22em` decides which copy shows (`display: none` on the other). Normal pair leaves the bar under 22em; urgent keeps only the Primary.
- [ ] Sheets: C§39 frames at <768 / 768–1023 / ≥1024; no bottom nav under full-screen sheets; consequence line + Cancel move into the flow under 22em; body `flex: 1` so the bar pins to the bottom.
- [ ] Undo: pending notice C§37 with an absolute time; remove on window end with a polite status; U1 sheet; no Undo inside toasts.
- [ ] `{requester}` copy slot (0.5) switches to the first name only after Show contact details (Director: always).
- [ ] Decline sheet: prefill + inline Replace/Keep row (no `confirm()`), debounced preview, counter at 90%.
- [ ] Owner-box copy: Q-154 reason labels, "until Tue, Oct 20" from the stored deadline, §11 line on R14/R18a/E9/A11 script.
- [ ] Requester chips per C§26a; R15 neutral; R13 Send answer inside the card, no mirror bar; R16 Not now in the flow <1024.
- [ ] `overflow-wrap: anywhere` on `.quote-block blockquote`, textareas' rendered text, thread items; `overflow-wrap: break-word` (not anywhere) on choice-card labels; decorative choice-card icons dropped under 22em.
- [ ] Icons to add to `icons.svg` (Lucide names): `badge-check`, `circle-x`, `rotate-ccw`, `timer`, `undo-2`, `check`, `x`, `message-circle-question`, `message-circle`, `message-circle-x`, `user-round-check`, `phone-outgoing`, `calendar-clock`, `tag`, `mail`, `cloud-off`, `mic`, and `image` / `house` if not already in the sprite.
- [ ] Rows: new markers (0.4); Decided filter chips; tab counts at `type-chip`.
- [ ] Home: urgent cap 3 with one Primary; Board-approved-not-certified card; Director "Call to share a decision"; banners `--approved` (must acknowledge) and `--undone`.
- [ ] No hard-coded colours, sizes or the 30-minute / 14-day values: times and dates come from the server (rules module).

## 9. Visual QA plan (ui-designer, once built)
Capture at 390×844, 768×1024, 1280×800, 1440×900 (light only, Q-016), plus **390 + 200% text** (assert root 32px) and **195 px** for every A and R screen, into `docs/ux/screenshots/step3/`:
- A1: pastor normal, pastor urgent, Board rep, dual role, Director, Administrator; pending (decider + other); decided approved / rejected / final / Board; urgent not yet certified; reconsideration (decider, other pastor, Board route); impersonating; offline; concurrency alert; loading.
- Sheets: A2, A2b (+ urgent notice), A2u (+ switch), A2n, A2c, A3 (+ replace prompt, errors), U1 (+ refused), A4 (+ no-email), A5, A6, A9 approve/decline/take-over, A11, A12.
- A7 tabs × roles (+ empty, filtered-empty, loading); Home pastor / Board / Director; Inbox; banners ×3.
- R13 (open, sent, failed, offline, withdrawn), R14 (+ urgent), R15, R16 (+ failed), R17, R18a/b/c.
Checks: `scrollWidth <= innerWidth`; bar ≤ 18% of the viewport at 200% text; exactly one Primary (or the equal pair) visible; sticky Decision card never overlaps the header; no mid-word breaks (per-word Range rects); targets ≥ 44px; axe-core clean at 390 and 1280; keyboard walk of the focus orders in §1.8 and §7.

---

## 10. Open visual questions
- **OQ-1 (for architect + ux-designer):** during the 30-minute undo window, the requester page shows nothing new (this spec's assumption, since the email is held and an undo would otherwise flip what she already saw). Confirm the requester projection also waits for the window.
- **OQ-2 (ux-designer):** while another approver's decision is pending, should **Ask a question** stay available? This spec keeps it (behaviour unchanged), but a question asked during a pending decline would be withdrawn when the decline takes effect.
- **OQ-3 (ux-designer):** consequence and toast copy now mention the undo window ("The requester's email goes out at 3:45 PM, after your 30 minutes to undo"; "Approved · 3:15 PM · Undo until 3:45 PM"). These are proposed; the UX body predates D4.
- **OQ-4 (ux-designer):** pastor Home card for a Board-approved urgent request that awaits certification (4.1). Q-160 allows certifying later but no attention item is specified; this spec proposes it as an urgent card.
- **OQ-5 (all):** the Requests split view uses the sidebar rail at 1280–1535 so the two-column detail fits (P§2 v1.4). The alternative is keeping the full sidebar and going one column until 1536, which loses the side-by-side Decision card the brief asks for at 1280.
- **OQ-6 (ux-designer):** A4 for a no-email requester is laid out as one sheet (question + optional phone answer), matching the architect's `phone_answer` parameter; the UX body had two steps (Save question, then A5).
- **OQ-7 (rules-engineer):** the undo window is written `{rules.DECISION_UNDO_WINDOW}` here; use whatever name the rules module adopts.
- **OQ-8 (ux-designer):** R18b's **Ask for help** is Secondary lg here, not Ghost, so it reads as a real action on a page with no other button.
