#!/usr/bin/env node
/**
 * HAM frontend build (docs/adr/0001-stack.md: "one small TypeScript bundle via esbuild").
 *
 * 1. Bundles `src/sw.ts` -> `dist/sw.js` (the service worker; Django serves it from `/sw.js`
 *    with `Service-Worker-Allowed: /`, see `ham/web/views.py`).
 * 2. Self-hosts the active brand's fonts (design-system/README.md "How to use" step 1: "the
 *    frontend should self-host the brand's fonts... don't fetch from Google at runtime").
 *    Reads `design-system/brands/<HAM_BRAND>/brand.json` for the font names, copies the
 *    matching `@fontsource-variable/*` package's variable woff2 file, and writes
 *    `dist/fonts.css` with `@font-face` rules. If a named font has no installed/approved
 *    fontsource package, it is skipped: the token stack's system-font fallback still applies
 *    (`--ham-font-display` / `--ham-font-ui` already list system fallbacks), so this never
 *    blocks the build (S5 step 5: "otherwise system font stack via tokens").
 */
import { build } from "esbuild";
import {
  readFileSync,
  mkdirSync,
  copyFileSync,
  writeFileSync,
  existsSync,
  readdirSync,
} from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const repoRoot = path.resolve(root, "..");
const distDir = path.join(root, "dist");

mkdirSync(distDir, { recursive: true });

// --- 1. Service worker bundle -----------------------------------------------------------
const cacheVersion = process.env.HAM_SW_CACHE_VERSION ?? String(Date.now());

await build({
  entryPoints: [path.join(root, "src/sw.ts")],
  bundle: true,
  outfile: path.join(distDir, "sw.js"),
  format: "iife",
  target: "es2022",
  sourcemap: true,
  minify: true,
  define: {
    __HAM_SW_CACHE_VERSION__: JSON.stringify(cacheVersion),
  },
});
console.log("Built dist/sw.js");

// --- 1b. Upload module (R9 "Add photos and videos", S2.7) --------------------------------
await build({
  entryPoints: [path.join(root, "src/upload.ts")],
  bundle: true,
  outfile: path.join(distDir, "upload.js"),
  format: "iife",
  target: "es2022",
  sourcemap: true,
  minify: true,
});
console.log("Built dist/upload.js");

// --- 2. Self-hosted brand fonts ----------------------------------------------------------

// Package folder name for each approved font (design-system/brands/README.md "Approved
// fonts"), and which file inside it is the single self-hostable "variable" woff2.
const FONTSOURCE_PACKAGES = {
  Oswald: "@fontsource-variable/oswald",
  "Roboto Condensed": "@fontsource-variable/roboto-condensed",
  Montserrat: "@fontsource-variable/montserrat",
  Inter: "@fontsource-variable/inter",
  "Source Sans 3": "@fontsource-variable/source-sans-3",
  "Noto Sans": "@fontsource-variable/noto-sans",
  "Public Sans": "@fontsource-variable/public-sans",
};

const brandId = process.env.HAM_BRAND ?? "miami-temple";
const brandJsonPath = path.join(repoRoot, "design-system", "brands", brandId, "brand.json");

let fontFaces = [];
if (existsSync(brandJsonPath)) {
  const brand = JSON.parse(readFileSync(brandJsonPath, "utf-8"));
  const wanted = new Set([brand.fonts?.display, brand.fonts?.ui].filter(Boolean));
  const fontsDir = path.join(distDir, "fonts");
  mkdirSync(fontsDir, { recursive: true });

  for (const fontName of wanted) {
    const pkgName = FONTSOURCE_PACKAGES[fontName];
    if (!pkgName) {
      console.warn(
        `frontend build: "${fontName}" has no fontsource package mapping; falling back to ` +
          "the system font stack for it (design-system tokens already list one).",
      );
      continue;
    }
    // Fontsource packages install under frontend/node_modules (frontend/package.json), not
    // the repo root's.
    const pkgDir = path.join(root, "node_modules", pkgName);
    const wght = path.join(pkgDir, "wght.css");
    if (!existsSync(wght)) {
      console.warn(
        `frontend build: ${pkgName} is not installed (run "npm ci" in frontend/); skipping ` +
          `self-hosting for "${fontName}" this build. The system font stack still applies.`,
      );
      continue;
    }
    // The fontsource "variable" package ships one @font-face per Unicode range (latin,
    // latin-ext, cyrillic...) in `wght.css`, each pointing at `./files/<name>.woff2`. Copy the
    // whole `files/` folder for this package and rewrite the CSS to (a) point at our own
    // static path instead of a relative node_modules path, and (b) use the plain font name
    // ("Oswald") the design tokens reference, instead of fontsource's "Oswald Variable".
    const pkgSlug = pkgName.split("/")[1];
    const destFilesDir = path.join(fontsDir, pkgSlug);
    mkdirSync(destFilesDir, { recursive: true });
    for (const file of readdirSync(path.join(pkgDir, "files"))) {
      if (file.endsWith(".woff2")) {
        copyFileSync(path.join(pkgDir, "files", file), path.join(destFilesDir, file));
      }
    }
    const css = readFileSync(wght, "utf-8")
      .replaceAll("./files/", `/static/fonts/${pkgSlug}/`)
      .replaceAll(`${fontName} Variable`, fontName);
    fontFaces.push(`/* ${pkgName} (self-hosted, design-system/brands/README.md) */\n${css}`);
  }
}

const fontsCssPath = path.join(distDir, "fonts.css");
writeFileSync(
  fontsCssPath,
  fontFaces.length
    ? fontFaces.join("\n\n") + "\n"
    : "/* No self-hosted brand fonts for this build; system font stack applies. */\n",
);
console.log(
  fontFaces.length
    ? `Built dist/fonts.css with ${fontFaces.length} self-hosted font face(s).`
    : "Built dist/fonts.css (empty: no fonts self-hosted, system stack applies).",
);
