#!/usr/bin/env python3
"""Build HAM design tokens.

Reads  design-system/tokens.json  (source of truth)
Writes design-system/tokens.css   (CSS custom properties, light + dark; OS auto-dark only if ham.autoDark)
       design-system/README.md    (contrast + status tables between their markers)

Exit code 1 if any required contrast pair fails, so this can run in CI
(`python3 design-system/tools/build_tokens.py --check`).
Standard library only.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "tokens.json"
CSS = ROOT / "tokens.css"
README = ROOT / "README.md"
START, END = "<!-- contrast:start -->", "<!-- contrast:end -->"
SSTART, SEND = "<!-- status:start -->", "<!-- status:end -->"

doc = json.loads(TOKENS.read_text(encoding="utf-8"))


def get(path):
    node = doc
    for part in path.split("."):
        node = node[part]
    return node


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


REF = re.compile(r"^\{([^}]+)\}$")


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


def resolve(v, mode):
    """Resolve a value (possibly an alias) to a literal for the given mode."""
    m = REF.match(v) if isinstance(v, str) else None
    if not m:
        return v
    tok = get(m.group(1))
    val = tok.get("$extensions", {}).get("ham.modes", {}).get(mode, tok["$value"]) if mode == "dark" else tok["$value"]
    return resolve(val, mode)


def build_css():
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
    head = ("/* HAM design tokens — GENERATED from tokens.json by tools/build_tokens.py. Do not edit by hand. */\n"
            f"/* Version {doc['$extensions']['ham.version']} */\n\n")
    body = ":root {\n  color-scheme: light;\n" + "\n".join(light) + "\n}\n\n"
    darkblock = "\n".join(dark)
    body += '[data-theme="dark"] {\n  color-scheme: dark;\n' + darkblock + "\n}\n\n"
    if not doc["$extensions"].get("ham.autoDark", False):
        body += ("/* Automatic OS dark mode is OFF (ham.autoDark=false) while Q-016 is open; dark only via data-theme=\"dark\". */\n\n")
    else:
        body += ('@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {\n    color-scheme: dark;\n'
                 + "\n".join("  " + l for l in dark) + "\n  }\n}\n\n")
    body += ("@media (prefers-reduced-motion: reduce) {\n  :root {\n"
             "    --ham-duration-fast: 0ms;\n    --ham-duration-base: 0ms;\n    --ham-duration-slow: 0ms;\n  }\n}\n")
    CSS.write_text(head + body, encoding="utf-8")


# ---------- contrast ----------
def lum(hexv):
    h = hexv.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def S(p):
    return "{semantic.color." + p + "}"


SURFACES = ["bg.canvas", "bg.surface", "bg.surface-raised", "bg.sunken"]
PAIRS = []  # (fg, bg, minimum, note)
for t in ["text.primary", "text.secondary", "text.tertiary", "text.link"]:
    for s in SURFACES:
        PAIRS.append((t, s, 4.5, "text"))
for t, s in [("text.primary", "bg.selected"), ("text.primary", "bg.hover"), ("text.brand", "bg.selected"),
             ("text.on-primary", "action.primary.bg"), ("text.on-primary", "action.primary.bg-hover"),
             ("text.on-primary", "action.primary.bg-pressed"), ("text.on-danger", "action.danger.bg"),
             ("text.on-danger", "action.danger.bg-hover"), ("action.secondary.fg", "action.secondary.bg"),
             ("action.secondary.fg", "action.secondary.bg-hover"), ("text.on-appbar", "bg.appbar"),
             ("text.on-inverse", "bg.inverse"), ("appbar.text-muted", "bg.appbar"),
             ("appbar.text-muted", "appbar.field-bg"), ("text.on-appbar", "appbar.field-bg"),
             ("badge.fg", "badge.bg")]:
    PAIRS.append((t, s, 4.5, "text"))
for t, s in [("action.primary.bg", "bg.canvas"), ("action.primary.bg", "bg.surface"),
             ("action.danger.bg", "bg.surface"), ("action.secondary.border", "bg.surface"),
             ("border.strong", "bg.surface"), ("border.strong", "bg.canvas"), ("border.selected", "bg.surface"),
             ("focus.ring", "bg.canvas"), ("focus.ring", "bg.surface"),
             ("appbar.status-ok", "bg.appbar"), ("appbar.field-border", "bg.appbar")]:
    PAIRS.append((t, s, 3.0, "UI"))
for tone in doc["semantic"]["color"]["tone"]:
    if tone.startswith("$"):
        continue
    PAIRS += [(f"tone.{tone}.fg", f"tone.{tone}.bg", 4.5, "chip text"),
              (f"tone.{tone}.fg", "bg.surface", 4.5, "text on card"),
              (f"tone.{tone}.icon", f"tone.{tone}.bg", 3.0, "chip icon"),
              (f"tone.{tone}.icon", "bg.surface", 3.0, "icon on card")]
INFO = [("accent.leaf-light", "bg.surface", "decorative only"), ("accent.leaf-mid", "bg.surface", "decorative only"),
        ("accent.leaf-dark", "bg.surface", "large display / graphics only"),
        ("text.disabled", "bg.surface", "WCAG-exempt (disabled)")]


def contrast_md():
    rows, fails = [], []
    for fg, bg, mn, note in PAIRS:
        cells = []
        ok = True
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
    return head + "\n".join(rows) + "\n", fails


def status_md():
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


def splice(txt, a, b, body):
    if a in txt and b in txt:
        pre, rest = txt.split(a, 1)
        _, post = rest.split(b, 1)
        return pre + a + "\n" + body + b + post
    return txt


def main():
    build_css()
    md, fails = contrast_md()
    if README.exists():
        txt = README.read_text(encoding="utf-8")
        txt = splice(txt, START, END, md)
        txt = splice(txt, SSTART, SEND, status_md())
        README.write_text(txt, encoding="utf-8")
    else:
        print(md)
    print(f"tokens.css written; {len(PAIRS)} required pairs checked; {len(fails)} failing")
    for f in fails:
        print("  FAIL:", f)
    if fails and "--check" in sys.argv:
        sys.exit(1)


if __name__ == "__main__":
    main()
