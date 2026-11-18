// Serves the app shell from cache so the app opens offline, refreshing the cache in the background when online.
// API calls are never cached: offline data lives in IndexedDB (see js/db.js). Bump VERSION to drop old caches.
const VERSION = "v16";
const CACHE = `srs-shell-${VERSION}`;
const SHELL = [
  "/",
  "/manifest.webmanifest",
  "/static/app.css",
  "/static/js/app.js",
  "/static/js/api.js",
  "/static/js/db.js",
  "/static/js/dom.js",
  "/static/js/fsrs.js",
  "/static/js/queue.js",
  "/static/js/render.js",
  "/static/js/sync.js",
  "/static/js/offline.js",
  "/static/js/views/home.js",
  "/static/js/views/study.js",
  "/static/js/views/items.js",
  "/static/js/views/item_editor.js",
  "/static/js/views/settings.js",
  "/static/js/views/templates.js",
  "/static/js/views/library.js",
  "/static/js/views/reader.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL.map((url) => new Request(url, { credentials: "include" }))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("srs-shell-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Only cache real responses: when the openhost session has expired, requests get redirected to the login page,
// and caching that would break the app until the next update.
function cacheable(response) {
  return response.ok && !response.redirected && response.type === "basic";
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/service/")) return;
  const key = event.request.mode === "navigate" ? "/" : url.pathname;
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(key);
      const network = fetch(event.request)
        .then((response) => {
          if (cacheable(response)) cache.put(key, response.clone());
          return response;
        })
        .catch(() => undefined);
      if (cached) {
        event.waitUntil(network);
        return cached;
      }
      return (await network) ?? new Response("offline", { status: 503 });
    }),
  );
});
