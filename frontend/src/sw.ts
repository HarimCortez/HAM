/**
 * HAM's service worker (foundation.md S5: "PWA manifest + service worker (shell precache,
 * offline page)"). Scope is `/` (served at `/sw.js` with `Service-Worker-Allowed: /`, see
 * `ham/web/views.py`).
 *
 * Step 1 scope only (foundation.md §10 "Out of scope for step 1"):
 *   - Precache the app shell (offline page + a couple of static assets) so a navigation that
 *     fails offline can still show something useful.
 *   - On a failed navigation request, serve the cached offline page.
 *   - NO offline data queue yet. That is designed with the attendance step (Q-006 seam only).
 *
 * Self-contained, no bundler runtime dependency beyond esbuild's IIFE wrapper (CLAUDE.md
 * "Avoid heavy libraries for simple needs").
 */

/// <reference lib="webworker" />
export {};

declare const self: ServiceWorkerGlobalScope;

// Bumped whenever the precache list changes so old caches are cleaned up on activate.
// esbuild replaces this at build time (see scripts/build.mjs `define`).
declare const __HAM_SW_CACHE_VERSION__: string;

const CACHE_NAME = `ham-shell-${__HAM_SW_CACHE_VERSION__}`;

// Kept intentionally small: the offline page plus the bare minimum to render it. Real pages
// are network-first and are not precached (step 1 is read-only shell, not a full app cache).
const PRECACHE_URLS = ["/offline", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      // Best-effort: a missing asset must never block installation (PRD §70.3 "HAM must keep
      // working if any integration is down" applies to the shell too).
      await Promise.all(
        PRECACHE_URLS.map((url) => cache.add(url).catch(() => undefined)),
      );
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only handle page navigations. Everything else (static files, API calls) goes straight to
  // the network: HAM is server-rendered, so there is no offline data to serve from cache yet.
  if (request.mode !== "navigate") {
    return;
  }

  event.respondWith(
    (async () => {
      try {
        return await fetch(request);
      } catch {
        const cache = await caches.open(CACHE_NAME);
        const offline = await cache.match("/offline");
        return offline ?? Response.error();
      }
    })(),
  );
});
