/* Barterly console service worker: lets the arrivals screen open without signal.
 *
 * - The arrivals page (/console/arrivals) is network-first: the cached copy is used
 *   only when the network fails.
 * - Next's hashed build files (/_next/static/) are cache-first: their names change
 *   when their content does.
 * - Nothing else is touched: API calls, sign-in and other pages go to the network as
 *   usual. The arrivals data and queued check-ins live in IndexedDB, not here.
 */
const VERSION = "v1";
const PAGES = `barterly-pages-${VERSION}`;
const ASSETS = `barterly-assets-${VERSION}`;
const OFFLINE_PAGES = ["/console/arrivals"];

// The page is cached when it's visited signed in (never at install, which could store
// the sign-in redirect instead).
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("barterly-") && k !== PAGES && k !== ASSETS)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.open(ASSETS).then(async (cache) => {
        const hit = await cache.match(request);
        if (hit) return hit;
        const response = await fetch(request);
        if (response.ok) cache.put(request, response.clone());
        return response;
      }),
    );
    return;
  }

  if (request.mode === "navigate" && OFFLINE_PAGES.includes(url.pathname)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Only a real page: never a redirect to sign-in.
          if (response.ok && !response.redirected) {
            const copy = response.clone();
            caches.open(PAGES).then((cache) => cache.put(url.pathname, copy));
          }
          return response;
        })
        .catch(async () => (await caches.match(url.pathname)) || Response.error()),
    );
  }
});
