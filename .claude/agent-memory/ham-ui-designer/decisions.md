# ham-ui-designer design-system decisions

## v1.3.0 (step 2 intake, 2026-09-28)
- Screen specs live in `design-system/screens/<step>.md` (first: `intake.md`). Tokens only, no raw px in screen specs.
- New tokens: size.{chip, chip-lg, choice-card-min, code-input-max, dropzone-height, progress-height, accent-bar,
  empty-max, modal-sm, modal-md, split-list(-min/-max), step-rail, aside, wizard-max, requester-wide-max, icon-xl,
  list-row-min}, breakpoint.short (480px viewport HEIGHT: sticky bars unstick), type.code-entry, shadow.bar-top.
- New required contrast pairs in build_tokens.py: text.secondary/focus.ring/border.selected on bg.selected;
  action.primary.bg and border.strong on bg.sunken. All pass (77 pairs).
- New components C§19–§32: choice card/chip, code input (single field, never 6 boxes), step indicator + step list,
  sticky action bar (Back leaves the bar under 22em; one primary in DOM), review summary card, upload tile
  (status strip BELOW image, never text on photos), masked block (4 variants), requester status card,
  action/attention cards, request row + markers, view tabs, error summary, disclosure/overflow menu, sheet sizes.
- Requester chip tones: Received = info, Being reviewed = info (not amber: nothing waits on the requester),
  Closed = neutral. Staff chips keep §52 names/tones.
- Large-text contract: requester pages tested at 390 + 200% text and 200% zoom; container queries in em for all grids;
  overflow-wrap:anywhere on emails/addresses; min-height only.
- Split view: 1280–1535 list = split-list-min + one-column detail; >=1536 list = split-list + 2fr/1fr detail.
- Requester field labels type-h3, helpers type-body (never type-small), inputs type-body-lg at control-lg.
- L10 Close request uses the Danger button (only Danger in intake). R9 "Take a photo" is Secondary; Done is primary.
- Icons: app uses hand-drawn Lucide-style symbols in ham/web/static/web/icons.svg; new icons must be added there.

## v1.4 (step 3 approvals, 2026-09-29) — components only, tokens unchanged at 1.3.0
- Spec: `design-system/screens/approvals.md`. Owner box in docs/ux/approvals.md + docs/architecture/approvals.md overrides both bodies (undo 30 min, 14-day window, Q-154 reason labels, "the requester" until reveal, change category Dir/AD only, one "Why approved (leaders only)" note on approval only, take-over = tick + decide in one sheet).
- New components C§26a (requester chips: Approved=success circle-check, Not approved=neutral circle-x, Taking another look=info rotate-ccw, Closed=neutral ban), C§33 Decision card, C§34 Decision pair (Approve/Decline both Secondary, same icons colour; urgent = Primary "Approve as urgent" + Secondary Decline; Decline never Danger), C§35 quote block (figure/figcaption/blockquote, bg.sunken, left accent bar border.strong), C§36 message preview (dashed border.strong, requester type sizes, aria-live off), C§37 pending-decision notice (inline-alert--info + timer, absolute time, no ticking countdown), C§38 Q&A thread, C§39 side sheet (right, modal-sm/md, ≥1024), C§40 urgent banner variants (needs-pastor / approved must-ack / undone).
- "Rejected · Final" = Rejected chip + reason line, never a new chip.
- Undo lives in the Decision card + small confirm sheet, never in a toast (P§4 v1.4).
- Requests split view 1280–1535 uses the sidebar RAIL; detail is a size container, two columns at 42em (main 1fr + size.aside), Decision card sticky only in two-column mode and when viewport height >= breakpoint.short.
- <768: decision buttons rendered in card + sticky bar; under 22em a normal pair leaves the bar (no primary to keep), urgent keeps only the Primary. Sheets: consequence line + Cancel move into flow under 22em.
- Requester R13: Send answer stays inside the card (no mirrored sticky bar for textarea cards). R16: "Not now" in the flow <1024, bar holds only the primary.
- Open visual questions OQ-1..OQ-8 at the end of the spec (requester page during undo window, rail at 1280, etc.).

## Step 3 visual QA (2026-09-29, report docs/ux/reviews/step3-ui-visual-qa.md)
- QA recipe: DB ham_qa3, states made via services under FixedClock (past-window decisions) + run_held_decision_effects; drain outbox with ham.outbox.dispatch._attempt to get urgent banners. ALWAYS QA leadership with a live urgent banner: it caused the worst large-text failures.
- Recurring traps to check first next time: inherited `overflow-wrap:anywhere` (`.request-detail p`) breaks buttons letter-by-letter -> `.btn{overflow-wrap:normal}`; sheet Cancel must carry `.action-bar__back` or it stays in the bar under 22em; short-page bar pinning must cover `.sheet--fullscreen`, not only `.public-card`; viewport-gated sticky (media query) on one-column layouts covers content -> sticky only inside the container-query two-column mode.
- Verdicts: full-screen sheets at every width = acceptable V1 (with request line in header, no sticky banner on sheets); no second decision bar = acceptable if card is first and not sticky; R16 no aside = acceptable.
- Staff chips must come from tokens.json status.project (Rejected neutral circle-x, Approved info badge-check, Recon attention rotate-ccw); never render requester chip labels on staff rows.
