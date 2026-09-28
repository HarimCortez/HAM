#!/usr/bin/env python3
"""Build HAM design tokens for one church brand.

Two layers:
  design-system/tokens.json                 HAM core system (neutrals, semantic, status tones,
                                            type scale, spacing, motion). Identical for every church.
  design-system/brands/<brand>/brand.json   Thin church brand layer (name, mission line, logos,
                                            brand color seeds, display/UI font from an approved list).

Usage:
  python3 design-system/tools/build_tokens.py [--brand miami-temple] [--check]

Writes design-system/tokens.css (CSS custom properties, light + dark) and refreshes the generated
tables in design-system/README.md (brand picks, status catalog, contrast).

From the brand's primary seed color the build derives an 11-step scale (50-950, 500 = the seed) and
picks, automatically, which step fills primary buttons and which step is used for links, so both
pass WCAG 2.2 AA. The reasoning is printed and written into the README.

Exit code 1 if the brand is invalid or cannot reach AA (always), or if any required contrast pair
fails (with --check). Standard library only.
"""
import copy
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "tokens.json"
BRANDS = ROOT / "brands"
CSS = ROOT / "tokens.css"
README = ROOT / "README.md"
START, END = "<!-- contrast:start -->", "<!-- contrast:end -->"
SSTART, SEND = "<!-- status:start -->", "<!-- status:end -->"
BSTART, BEND = "<!-- brand:start -->", "<!-- brand:end -->"
DEFAULT_BRAND = "miami-temple"

STEPS = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"]
# Scale recipe (fixed, HAM core). Lightness and chroma in OKLCH, so every brand's steps sit at a
# similar *perceived* lightness and the contrast picks land in predictable places.
#   Tints: move lightness this fraction of the way from the seed to white; keep this share of chroma.
TINTS = {"50": (0.914, 0.109), "100": (0.813, 0.256), "200": (0.634, 0.497),
         "300": (0.413, 0.749), "400": (0.200, 0.952)}
#   Shades: reduce the seed's lightness by this fraction; keep this share of chroma.
SHADES = {"600": (0.105, 0.891), "700": (0.2075, 0.781), "800": (0.319, 0.656),
          "900": (0.429, 0.534), "950": (0.534, 0.317)}
# Brand hues too close to HAM's danger red would make the main button look like "danger".
DANGER_HUE_WINDOW = 25      # degrees of OKLCH hue
ATTENTION_HUE_WINDOW = 20
MIN_CHROMA_FOR_HUE = 0.07   # grays / near-neutrals have no meaningful hue

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
REF = re.compile(r"^\{([^}]+)\}$")


class BrandError(Exception):
    """A plain-language problem with the brand that stops the build."""


# ---------------------------------------------------------------- color math
def _s2l(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _l2s(c):
    c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return c * 255


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _hex(rgb):
    return "#" + "".join("%02X" % max(0, min(255, round(x))) for x in rgb)


def to_oklch(h):
    r, g, b = (_s2l(x) for x in _rgb(h))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(x) ** (1 / 3), x) for x in (l, m, s))
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def _oklch_lin(L, C, H):
    a, b = C * math.cos(math.radians(H)), C * math.sin(math.radians(H))
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s]


def from_oklch(L, C, H):
    """OKLCH -> sRGB hex, reducing chroma (keeping lightness and hue) until it fits the sRGB gamut."""
    inside = lambda c: all(-1e-6 <= x <= 1 + 1e-6 for x in _oklch_lin(L, c, H))
    if not inside(C):
        lo, hi = 0.0, C
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if inside(mid) else (lo, mid)
        C = lo
    return _hex([_l2s(min(1, max(0, x))) for x in _oklch_lin(L, C, H)])


def lum(hexv):
    r, g, b = (_s2l(x) for x in _rgb(hexv))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def hue_distance(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


# ---------------------------------------------------------------- token doc helpers
def is_token(n):
    return isinstance(n, dict) and "$value" in n


def walk(node, path=()):
    for k, v in node.items():
        if k.startswith("$"):
            continue
        if is_token(v):
            yield path + (k,), v
        elif isinstance(v, dict):
            yield from walk(v, path + (k,))


def get(doc, path):
    node = doc
    for part in path.split("."):
        node = node[part]
    return node


def css_name(path):
    p = list(path)
    top = p.pop(0)
    if top == "primitive":
        grp = p.pop(0)
        if grp == "color":
            return "--ham-color-" + "-".join(p)
        if grp == "font":
            sub = p.pop(0)
            return ("--ham-font-" if sub == "family" else "--ham-font-weight-") + "-".join(p)
        if grp == "typography":
            return "--ham-type-" + "-".join(p)
        return f"--ham-{grp}-" + "-".join(p)
    if top == "semantic":
        grp = p.pop(0)
        if grp == "color":
            return "--ham-" + "-".join(p)
        return f"--ham-{grp}-" + "-".join(p)
    if top == "status":
        return "--ham-status-" + "-".join(p)
    raise ValueError(path)


def css_value(v):
    if isinstance(v, str):
        m = REF.match(v)
        if m:
            return f"var({css_name(tuple(m.group(1).split('.')))})"
        return v
    if isinstance(v, list):
        if all(isinstance(x, (int, float)) for x in v):
            return "cubic-bezier(" + ", ".join(str(x) for x in v) + ")"
        return ", ".join(f'"{x}"' if " " in x else x for x in v)
    return str(v)


def resolver(doc):
    def resolve(v, mode):
        m = REF.match(v) if isinstance(v, str) else None
        if not m:
            return v
        tok = get(doc, m.group(1))
        val = tok.get("$extensions", {}).get("ham.modes", {}).get(mode, tok["$value"]) if mode == "dark" else tok["$value"]
        return resolve(val, mode)
    return resolve


def S(p):
    return "{semantic.color." + p + "}"


# ---------------------------------------------------------------- brand layer
def load_brand(name):
    folder = BRANDS / name
    f = folder / "brand.json"
    if not f.exists():
        known = sorted(p.name for p in BRANDS.iterdir() if (p / "brand.json").exists()) if BRANDS.exists() else []
        raise BrandError(f"There is no brand called '{name}'. Expected the file {f.relative_to(ROOT.parent)}. "
                         f"Brands available: {', '.join(known) or 'none'}.")
    try:
        brand = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BrandError(f"{f.name} is not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}. "
                         "Check for a missing comma or quote.")
    return folder, brand


def validate_brand(folder, brand, policy):
    problems = []
    church = brand.get("church", {})
    for key, label in (("name", "church name"), ("shortName", "short name"), ("missionLine", "mission line")):
        if not str(church.get(key, "")).strip():
            problems.append(f"The {label} is missing (church.{key}).")
    colors = brand.get("colors", {})
    seeds = [colors.get("primary")] + list(colors.get("accents", []))
    if not colors.get("primary"):
        problems.append("The primary brand color is missing (colors.primary), e.g. \"#0B9444\".")
    for c in seeds:
        if c and not HEX.match(c):
            problems.append(f"'{c}' is not a color HAM understands. Write colors as # plus six hex digits, e.g. \"#0B9444\".")
    if len(colors.get("accents", [])) > 2:
        problems.append("Give at most two accent colors (colors.accents); HAM's decorative stripe has three bands including the primary color.")
    fonts = brand.get("fonts", {})
    for role in ("display", "ui"):
        allowed = policy["fonts"][role]
        choice = fonts.get(role)
        if choice not in allowed:
            problems.append(f"The {role} font '{choice}' is not on HAM's approved list. Choose one of: "
                            f"{', '.join(allowed)}. (Fonts are limited so every church's HAM stays readable "
                            "for older requesters and works offline.)")
    logos = brand.get("logos", {})
    if not str(logos.get("alt", "")).strip():
        problems.append("The logo's alt text is missing (logos.alt). Screen readers read it aloud.")
    need = {"onDark": "a light (white) logo for dark backgrounds",
            "onLight": "a dark logo for white and light backgrounds",
            "mark": "the symbol on its own (no words) for app icons and small spaces"}
    for key, what in need.items():
        entry = logos.get(key)
        if not entry or not entry.get("file"):
            problems.append(f"Logo '{key}' is missing: HAM needs {what}.")
            continue
        for fkey in ("file", "small"):
            if entry.get(fkey) and not (folder / entry[fkey]).exists():
                problems.append(f"Logo file '{entry[fkey]}' ({key}) is listed but not in {folder.name}/.")
        expected_bg = {"onDark": "dark", "onLight": "light", "mark": "any"}[key]
        if entry.get("background") != expected_bg:
            problems.append(f"Logo '{key}' must say \"background\": \"{expected_bg}\".")
    if problems:
        raise BrandError("The brand file has problems:\n  - " + "\n  - ".join(problems))


def derive_scale(seed):
    L, C, H = to_oklch(seed)
    scale = {}
    for step in STEPS:
        if step == "500":
            scale[step] = seed.upper()
        elif step in TINTS:
            t, f = TINTS[step]
            scale[step] = from_oklch(L + (1 - L) * t, C * f, H)
        else:
            d, f = SHADES[step]
            scale[step] = from_oklch(L * (1 - d), C * f, H)
    return scale


def darker(step, n=1):
    return STEPS[STEPS.index(step) + n]


def lighter(step, n=1):
    return STEPS[STEPS.index(step) - n]


def pick_roles(scale, core, resolve, policy, seed):
    """Choose button and link steps for each theme. Returns (roles, reasons)."""
    target = policy["textContrastTarget"]
    roles, reasons = {}, []

    def surfaces(mode):
        return {s: resolve(S(s), mode) for s in ("bg.canvas", "bg.surface", "bg.surface-raised", "bg.sunken", "bg.hover")}

    # ----- light theme
    white = resolve(S("text.on-primary"), "light")
    surf = surfaces("light")
    tried = []
    button = None
    for step in policy["buttonSteps"]:
        r = ratio(scale[step], white)
        ui = min(ratio(scale[step], surf["bg.canvas"]), ratio(scale[step], surf["bg.surface"]))
        tried.append(f"{step} {scale[step]} gives {r:.2f}:1")
        if r >= target and ui >= 3.0:
            button = step
            break
    if not button:
        # Find how dark the seed would need to be, to give a useful suggestion.
        L, C, H = to_oklch(seed)
        suggestion = None
        for i in range(1, 60):
            cand = from_oklch(L * (1 - i * 0.01), C, H)
            if ratio(cand, white) >= target:
                suggestion = cand
                break
        raise BrandError(
            f"The brand color {seed} is too light for HAM's buttons.\n"
            f"  HAM puts white text on the main button, and people must be able to read it (WCAG AA asks for 4.5:1; "
            f"HAM aims for {target}:1 to leave room for screen glare).\n"
            f"  HAM tried your color and up to two shades darker: {'; '.join(tried)}. None is dark enough.\n"
            f"  Going darker than that would no longer look like your brand color, so the build stops here.\n"
            f"  What to do: use a deeper version of the color as the seed"
            + (f" (the nearest shade that works is about {suggestion})" if suggestion else "")
            + ", or ask the church whether its brand guide has a darker 'text' or 'web' version.")
    roles["light"] = {"selected-bg": "50", "action": button, "action-hover": darker(button),
                      "action-pressed": darker(button, 2)}
    reasons.append(f"Button (light): step {button} {scale[button]}. White text on it is "
                   f"{ratio(scale[button], white):.2f}:1. It is the step closest to the seed that reaches "
                   f"{target}:1 (checked: {'; '.join(tried)}). Hover = {darker(button)}, pressed = {darker(button, 2)}.")

    link_bgs = dict(surf, **{"bg.selected": scale["50"]})
    link = None
    for step in STEPS[STEPS.index(button) + 1: STEPS.index("900") + 1]:
        worst_bg, worst = min(((k, ratio(scale[step], v)) for k, v in link_bgs.items()), key=lambda x: x[1])
        if worst >= target:
            link = step
            break
    if not link:
        raise BrandError(f"No shade of {seed} is dark enough for link text on HAM's page backgrounds "
                         f"(needs {target}:1). Use a deeper seed color.")
    roles["light"].update({"link": link, "link-hover": darker(link)})
    reasons.append(f"Links, brand text, outline-button text and focus ring (light): step {link} {scale[link]}. "
                   f"It is at least one step deeper than the button fill (text strokes are thinner than a filled "
                   f"button, so they get extra margin) and its weakest pair is {worst:.2f}:1 on `{worst_bg}`. "
                   f"Hover = {darker(link)}.")

    # ----- dark theme (kept for later; V1 ships light only, Q-016)
    ink = resolve(S("text.on-primary"), "dark")
    dsurf = surfaces("dark")
    dbutton = None
    for step in policy["darkButtonSteps"]:
        r = ratio(scale[step], ink)
        ui = min(ratio(scale[step], dsurf["bg.canvas"]), ratio(scale[step], dsurf["bg.surface"]))
        if r >= target and ui >= 3.0:
            dbutton = step
            break
    if not dbutton:
        raise BrandError(f"The brand color {seed} has no shade light enough for a dark-theme button with dark "
                         f"text at {target}:1. Use a less dark seed color.")
    roles["dark"] = {"selected-bg": "950", "action": dbutton, "action-hover": lighter(dbutton),
                     "action-pressed": lighter(dbutton, 2)}
    dlink_bgs = dict(dsurf, **{"bg.selected": scale["950"]})
    dlink = None
    for step in reversed(STEPS[STEPS.index("100"): STEPS.index(dbutton)]):
        worst_bg, worst = min(((k, ratio(scale[step], v)) for k, v in dlink_bgs.items()), key=lambda x: x[1])
        if worst >= target:
            dlink = step
            break
    if not dlink:
        raise BrandError(f"No shade of {seed} is light enough for dark-theme link text (needs {target}:1).")
    roles["dark"].update({"link": dlink, "link-hover": lighter(dlink)})
    reasons.append(f"Dark theme (kept for later, Q-016): button step {dbutton} {scale[dbutton]} with ink text "
                   f"{ratio(scale[dbutton], ink):.2f}:1; links step {dlink} {scale[dlink]} (weakest {worst:.2f}:1 on `{worst_bg}`).")
    return roles, reasons


def hue_checks(seed, core_resolve):
    """Stop if the brand color would read as HAM's danger red. Warn if it is close to attention amber."""
    L, C, H = to_oklch(seed)
    warnings = []
    if C < MIN_CHROMA_FOR_HUE:
        return warnings
    danger = core_resolve(S("action.danger.bg"), "light")
    dH = to_oklch(danger)[2]
    if hue_distance(H, dH) <= DANGER_HUE_WINDOW:
        raise BrandError(
            f"The brand color {seed} is too close to HAM's danger red ({danger}).\n"
            "  In HAM, red means 'stop / unsafe / blocked' (safety holds, blocked tasks, expired credentials, "
            "Delete buttons). If the main button were red too, volunteers could not tell 'go ahead' from 'danger', "
            "and that meaning must be the same for every church.\n"
            "  What to do: use another of the church's colors as the primary seed (for example a navy, green or "
            "deep blue from the logo). The red can still appear as a decorative accent (colors.accents).")
    amber = core_resolve(S("tone.attention.icon"), "light")
    if hue_distance(H, to_oklch(amber)[2]) <= ATTENTION_HUE_WINDOW:
        warnings.append(f"Note: {seed} is close to HAM's 'needs attention' amber ({amber}). This is allowed because "
                        "every status also has an icon and a label, but check the screens for confusion.")
    return warnings


def apply_brand(core, folder, brand):
    doc = copy.deepcopy(core)
    policy = doc["$extensions"]["ham.brandPolicy"]
    validate_brand(folder, brand, policy)
    seed = brand["colors"]["primary"].upper()
    core_resolve = resolver(doc)
    warnings = hue_checks(seed, core_resolve)

    scale = derive_scale(seed)
    grp = doc["primitive"]["color"]["brand"]
    for step in STEPS:
        grp[step] = {"$type": "color", "$value": scale[step]}
    grp["500"]["$description"] = f"Seed: {brand['church']['shortName']} primary brand color."

    # Accents: primary + up to two accents, filled from the scale if fewer, sorted lightest -> darkest.
    acc = [seed] + [c.upper() for c in brand["colors"].get("accents", [])]
    for fill in ("300", "200"):
        if len(acc) < 3:
            acc.append(scale[fill])
    acc.sort(key=lambda h: to_oklch(h)[0], reverse=True)
    accents = dict(zip(("light", "mid", "dark"), acc))

    policy_fonts = policy["fonts"]
    fonts = {"display": policy_fonts["display"][brand["fonts"]["display"]]["stack"],
             "ui": policy_fonts["ui"][brand["fonts"]["ui"]]["stack"]}
    for path, tok in walk(doc):
        src = tok.get("$extensions", {}).get("ham.fromBrand")
        if src:
            kind, key = src.split(".")
            tok["$value"] = accents[key] if kind == "accent" else fonts[key]
            del tok["$extensions"]["ham.fromBrand"]
            if not tok["$extensions"]:
                del tok["$extensions"]

    resolve = resolver(doc)
    roles, reasons = pick_roles(scale, core, resolve, policy, seed)

    brand_ref = re.compile(r"^\{brand\.([a-z-]+)\}$")
    for path, tok in walk(doc["semantic"]):
        m = brand_ref.match(tok["$value"]) if isinstance(tok["$value"], str) else None
        if m:
            tok["$value"] = "{primitive.color.brand.%s}" % roles["light"][m.group(1)]
        modes = tok.get("$extensions", {}).get("ham.modes", {})
        m = brand_ref.match(modes.get("dark", "")) if isinstance(modes.get("dark"), str) else None
        if m:
            modes["dark"] = "{primitive.color.brand.%s}" % roles["dark"][m.group(1)]
    leftovers = [".".join(p) for p, t in walk(doc) if t["$value"] is None or "{brand." in json.dumps(t)]
    if leftovers:
        raise BrandError("Internal: brand placeholders left unfilled: " + ", ".join(leftovers))
    info = {"seed": seed, "scale": scale, "roles": roles, "reasons": reasons, "accents": accents,
            "warnings": warnings}
    return doc, info


# ---------------------------------------------------------------- outputs
def build_css(doc, brand):
    light, dark = [], []
    for path, tok in walk(doc):
        name = css_name(path)
        v = tok["$value"]
        if tok.get("$type") == "typography":
            fam = css_value(v["fontFamily"])
            light += [f"  {name}-family: {fam};", f"  {name}-weight: {v['fontWeight']};",
                      f"  {name}-size: {v['fontSize']};", f"  {name}-line-height: {v['lineHeight']};",
                      f"  {name}-tracking: {v['letterSpacing']};"]
            continue
        light.append(f"  {name}: {css_value(v)};")
        d = tok.get("$extensions", {}).get("ham.modes", {}).get("dark")
        if d is not None:
            dark.append(f"  {name}: {css_value(d)};")
    head = ("/* HAM design tokens — GENERATED from tokens.json + brands/"
            f"{brand['id']}/brand.json by tools/build_tokens.py. Do not edit by hand. */\n"
            f"/* Version {doc['$extensions']['ham.version']} · Brand: {brand['church']['name']} */\n\n")
    body = ":root {\n  color-scheme: light;\n" + "\n".join(light) + "\n}\n\n"
    body += '[data-theme="dark"] {\n  color-scheme: dark;\n' + "\n".join(dark) + "\n}\n\n"
    if not doc["$extensions"].get("ham.autoDark", False):
        body += ("/* Automatic OS dark mode is OFF (ham.autoDark=false): V1 is light only (Q-016). "
                 "Dark values are kept for later and apply only via data-theme=\"dark\". */\n\n")
    else:
        body += ('@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {\n    color-scheme: dark;\n'
                 + "\n".join("  " + l for l in dark) + "\n  }\n}\n\n")
    body += ("@media (prefers-reduced-motion: reduce) {\n  :root {\n"
             "    --ham-duration-fast: 0ms;\n    --ham-duration-base: 0ms;\n    --ham-duration-slow: 0ms;\n  }\n}\n")
    CSS.write_text(head + body, encoding="utf-8")


SURFACES = ["bg.canvas", "bg.surface", "bg.surface-raised", "bg.sunken"]


def required_pairs(doc):
    pairs = []  # (fg, bg, minimum, note)
    for t in ["text.primary", "text.secondary", "text.tertiary", "text.link"]:
        for s in SURFACES:
            pairs.append((t, s, 4.5, "text"))
    for t, s in [("text.primary", "bg.selected"), ("text.primary", "bg.hover"), ("text.brand", "bg.selected"),
                 ("text.link", "bg.hover"),
                 ("text.on-primary", "action.primary.bg"), ("text.on-primary", "action.primary.bg-hover"),
                 ("text.on-primary", "action.primary.bg-pressed"), ("text.on-danger", "action.danger.bg"),
                 ("text.on-danger", "action.danger.bg-hover"), ("action.secondary.fg", "action.secondary.bg"),
                 ("action.secondary.fg", "action.secondary.bg-hover"), ("text.on-appbar", "bg.appbar"),
                 ("text.on-inverse", "bg.inverse"), ("appbar.text-muted", "bg.appbar"),
                 ("appbar.text-muted", "appbar.field-bg"), ("text.on-appbar", "appbar.field-bg"),
                 ("badge.fg", "badge.bg"),
                 # v1.3 (intake): hint text inside a selected choice card
                 ("text.secondary", "bg.selected")]:
        pairs.append((t, s, 4.5, "text"))
    for t, s in [("action.primary.bg", "bg.canvas"), ("action.primary.bg", "bg.surface"),
                 ("action.danger.bg", "bg.surface"), ("action.secondary.border", "bg.surface"),
                 ("border.strong", "bg.surface"), ("border.strong", "bg.canvas"), ("border.selected", "bg.surface"),
                 ("focus.ring", "bg.canvas"), ("focus.ring", "bg.surface"),
                 ("appbar.status-ok", "bg.appbar"), ("appbar.field-border", "bg.appbar"),
                 # v1.3 (intake): selected choice card edge + focus ring on it; progress fill on its track;
                 # input/drop-zone border on a sunken panel
                 ("border.selected", "bg.selected"), ("focus.ring", "bg.selected"),
                 ("action.primary.bg", "bg.sunken"), ("border.strong", "bg.sunken")]:
        pairs.append((t, s, 3.0, "UI"))
    for tone in doc["semantic"]["color"]["tone"]:
        if tone.startswith("$"):
            continue
        pairs += [(f"tone.{tone}.fg", f"tone.{tone}.bg", 4.5, "chip text"),
                  (f"tone.{tone}.fg", "bg.surface", 4.5, "text on card"),
                  (f"tone.{tone}.icon", f"tone.{tone}.bg", 3.0, "chip icon"),
                  (f"tone.{tone}.icon", "bg.surface", 3.0, "icon on card")]
    return pairs


INFO = [("accent.brand-light", "bg.surface", "decorative only"), ("accent.brand-mid", "bg.surface", "decorative only"),
        ("accent.brand-dark", "bg.surface", "decorative / large display only"),
        ("text.disabled", "bg.surface", "WCAG-exempt (disabled)")]


def contrast_md(doc):
    resolve = resolver(doc)
    pairs = required_pairs(doc)
    rows, fails = [], []
    for fg, bg, mn, note in pairs:
        cells, ok = [], True
        for mode in ("light", "dark"):
            r = ratio(resolve(S(fg), mode), resolve(S(bg), mode))
            ok &= r >= mn
            cells.append(f"{r:.2f}")
        if not ok:
            fails.append(f"{fg} on {bg}")
        rows.append(f"| `{fg}` on `{bg}` | {note} | {mn}:1 | {cells[0]} | {cells[1]} | {'Pass' if ok else '**FAIL**'} |")
    for fg, bg, note in INFO:
        cells = [f"{ratio(resolve(S(fg), m), resolve(S(bg), m)):.2f}" for m in ("light", "dark")]
        rows.append(f"| `{fg}` on `{bg}` | {note} | n/a | {cells[0]} | {cells[1]} | Info |")
    head = ("| Pair (foreground on background) | Use | Min | Light | Dark | Result |\n"
            "|---|---|---|---|---|---|\n")
    return head + "\n".join(rows) + "\n", fails, len(pairs)


def status_md(doc):
    rows = ["| Group (PRD) | Status label | Tone | Icon | CSS prefix |", "|---|---|---|---|---|"]
    for grp, items in doc["status"].items():
        sec = items.get("$description", "")
        first = True
        for slug, tok in items.items():
            if slug.startswith("$"):
                continue
            m = tok["$extensions"]["ham.status"]
            g = f"**{grp}** · {sec}" if first else ""
            first = False
            rows.append(f"| {g} | {m['label']} | {m['tone']} | `{m['icon']}` | `--ham-status-{grp}-{slug}-*` |")
    return "\n".join(rows) + "\n"


def brand_md(brand, info):
    s, r = info["scale"], info["roles"]
    lines = [f"Built for **{brand['church']['name']}** (`brands/{brand['id']}/`). Seed `{info['seed']}`; "
             f"display font {brand['fonts']['display']}, UI font {brand['fonts']['ui']}.", "",
             "| Step | " + " | ".join(STEPS) + " |", "|---|" + "---|" * len(STEPS),
             "| Hex | " + " | ".join(f"`{s[k]}`" for k in STEPS) + " |",
             "| Light role | " + " | ".join(", ".join(x for x, v in r["light"].items() if v == k) or "" for k in STEPS) + " |",
             "| Dark role | " + " | ".join(", ".join(x for x, v in r["dark"].items() if v == k) or "" for k in STEPS) + " |",
             "", "Why these steps (written by the build):", ""]
    lines += [f"- {x}" for x in info["reasons"]]
    lines += [f"- Accent stripe (decorative only): light `{info['accents']['light']}`, mid `{info['accents']['mid']}`, "
              f"dark `{info['accents']['dark']}`."]
    lines += [f"- {w}" for w in info["warnings"]]
    return "\n".join(lines) + "\n"


def splice(txt, a, b, body):
    if a in txt and b in txt:
        pre, rest = txt.split(a, 1)
        _, post = rest.split(b, 1)
        return pre + a + "\n" + body + b + post
    return txt


def parse_args(argv):
    brand, check = DEFAULT_BRAND, False
    it = iter(argv[1:])
    for a in it:
        if a == "--check":
            check = True
        elif a == "--brand":
            brand = next(it, None)
            if not brand:
                sys.exit("--brand needs a name, e.g. --brand miami-temple")
        elif a.startswith("--brand="):
            brand = a.split("=", 1)[1]
        else:
            sys.exit(f"Unknown option {a}. Usage: build_tokens.py [--brand NAME] [--check]")
    return brand, check


def main():
    brand_name, check = parse_args(sys.argv)
    core = json.loads(TOKENS.read_text(encoding="utf-8"))
    try:
        folder, brand = load_brand(brand_name)
        doc, info = apply_brand(core, folder, brand)
    except BrandError as e:
        print(f"BUILD STOPPED (brand '{brand_name}'): {e}\nNothing was written.", file=sys.stderr)
        sys.exit(1)
    build_css(doc, brand)
    md, fails, n = contrast_md(doc)
    if README.exists():
        txt = README.read_text(encoding="utf-8")
        txt = splice(txt, BSTART, BEND, brand_md(brand, info))
        txt = splice(txt, START, END, md)
        txt = splice(txt, SSTART, SEND, status_md(doc))
        README.write_text(txt, encoding="utf-8")
    print(f"Brand: {brand['church']['name']} (seed {info['seed']})")
    for x in info["reasons"] + info["warnings"]:
        print("  " + x)
    print(f"tokens.css written; {n} required pairs checked; {len(fails)} failing")
    for f in fails:
        print("  FAIL:", f)
    if fails and check:
        sys.exit(1)


if __name__ == "__main__":
    main()
