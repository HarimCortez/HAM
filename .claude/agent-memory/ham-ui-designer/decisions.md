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
