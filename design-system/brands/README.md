# Church brands: how to add a new church

HAM is built for one church per deployment (PRD header "Single church", §74, §75; Q-026). Another church that adopts HAM runs its **own** copy, with its own data, and swaps in its own look by adding a folder here. No code changes and no multi-church data model.

Each church's look is a thin **brand layer** on top of HAM's fixed core system (`../tokens.json`):

```
design-system/
  tokens.json                  HAM core: identical for every church
  brands/
    miami-temple/              one folder per church
      brand.json               name, mission line, colors, fonts, logos
      logo-white-on-dark.png
      logo-dark-on-light.png
      logo-dark-on-light@small.png
      logo-mark.png
  tools/build_tokens.py        combines the two: --brand <folder name>
  tokens.css                   the result the app loads
```

## What a church can and cannot customize

| Can customize (brand layer) | Cannot customize (HAM core, same for every church) |
|---|---|
| Church name, short name, mission line | Status colors, icons and labels (projects, tasks, invitations, credentials…) |
| One primary brand color (the "seed") and up to two accent colors | Semantic colors: danger red, attention amber, success teal, info blue, AI violet |
| Display font and UI font, each from the approved list below | Neutrals (grays, text colors, page backgrounds, the dark app bar) |
| Logos (three versions, below) | Type scale and sizes, spacing, corner radius, shadows, motion, breakpoints |
| | Minimum touch-target size, focus ring, contrast rules |

**Why so strict?** Safety and status meaning must be identical everywhere. "Red = blocked or unsafe", "teal with a check = done" and "amber = waiting on a person" mean the same thing for every volunteer at every church. Those colors are chosen together to be readable by older requesters in sunlight and by people with color blindness. A church changes how HAM *feels*, never what its signals *mean*.

### Where the brand color shows up
- Primary buttons, links, the selected item in navigation, focus rings, outline buttons.
- The thin decorative stripe under the app bar and on hero number tiles (primary + accent colors).
- **Not** in status chips. The "active / on track" status keeps HAM's own green for every church.

### Approved fonts
Listed in `tokens.json` under `$extensions["ham.brandPolicy"].fonts`, with the offline (self-hosted) package for each. All are free to use and self-hostable, readable at 16px, and support Latin Extended.

| Display (screen titles, big numbers) | UI (everything else) |
|---|---|
| Oswald (Miami Temple) | Inter (Miami Temple, HAM default) |
| Roboto Condensed | Source Sans 3 |
| Montserrat | Noto Sans |
| Inter (no separate display face) | Public Sans |

To propose another font, ask the HAM design owner (ham-ui-designer). It must be free to self-host, have tabular figures, and stay readable at 16px.

## Logos: the three versions HAM needs

| `brand.json` key | What it is | Background | Used on |
|---|---|---|---|
| `onDark` | Light / white logo | **Dark only** (HAM's app bar is near-black `#111814` in every theme) | App bar, dark photos, splash |
| `onLight` (+ optional `small`) | Dark logo, with the wordmark in near-black **`#111814`** | White or light surfaces | Sign-in card, requester pages, emails, PDF reports, public scoreboard embed |
| `mark` | The symbol alone, no words | Must work on both light and dark | Favicon / app icon, compact mobile app bar |

Requirements:
- PNG with a transparent background (or SVG). Full lockups at least 2000px wide; mark at least 400px on its short side.
- The dark-on-light version keeps the church's own symbol colors; only the words turn to `#111814` (decided with the product owner for Miami Temple and used for every church, so logos sit on the same ink as HAM's text).
- No padding baked into the files beyond the logo's own clear space. No drop shadows or outlines.
- Get the church communications team's written OK to use the logo, and ask for their brand guide.

## Colors: what the build does with your seed

1. You give **one primary color** (usually the strongest color in the logo). The build makes an 11-step scale from it, 50 (lightest) to 950 (darkest), with your color at step 500. The steps are computed in a perceptual color space so every church's scale has similar lightness steps.
2. It then **picks the button color automatically**: the step closest to your color on which white text reaches **4.7:1** (WCAG AA asks for 4.5:1; the extra margin covers screen glare). It may go at most two steps darker than your color, so the button still looks like your brand.
3. It **picks the link color**: at least one step deeper than the button (thin text needs more contrast than a filled button), reaching 4.7:1 on every page background, including gray panels and the selected-row tint.
4. It writes the picks and the reasons into `../README.md` ("Active brand" section) and prints them.
5. It runs HAM's full contrast check (all required pairs, both themes).

**The build stops, with a plain-language message and no files written, when:**
- your color is too light for white button text even two steps darker (typical for yellows, oranges and pastels). The message suggests the nearest darker shade that would work; ask the church whether its brand guide has a deeper "web" or "text" version;
- your color is too close to HAM's **danger red**. Red must only mean "stop / unsafe" in HAM. Use another logo color as the primary; the red can still be an accent;
- a field is missing, a font isn't approved, or a logo file isn't in the folder.

Accent colors are decorative only (never text, never meaning), so they have no contrast requirement.

## Checklist: adding a church

1. [ ] Church communications has approved HAM's use of the logo; you have their brand guide if one exists.
2. [ ] Create `design-system/brands/<short-id>/` (lowercase, hyphens, e.g. `grace-chapel`).
3. [ ] Add the three logo versions (`onDark`, `onLight` with `#111814` wordmark, `mark`); check each on its intended background.
4. [ ] Copy `miami-temple/brand.json`, then set `id`, church `name`, `shortName`, `missionLine`, `colors.primary`, up to two `colors.accents`, `fonts.display`, `fonts.ui`, logo `alt` text, and each logo's `file` and `size`.
5. [ ] Run `python3 design-system/tools/build_tokens.py --brand <short-id> --check`. Fix anything it reports.
6. [ ] Read the "Active brand" section in `design-system/README.md`: does the picked button color still look like the church? If not, try a different seed from the logo.
7. [ ] Open the mockups in `docs/ux/screens/` with the new `tokens.css` and look at: the app bar logo, a primary button, a link, a selected nav item, and a status chip next to a button (they must not look alike).
8. [ ] Deploy that church's HAM with `tokens.css` built for its brand, and point the app's brand setting at the same folder.

Contact details (ministry phone and email, Q-007) are not part of the brand layer; administrators set them in the app.
