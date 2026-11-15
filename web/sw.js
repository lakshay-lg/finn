/* FINN service worker. Network first for everything, so a redeploy is picked up on the next open;
   the cached app shell is only a fallback when there is no connection. API data is never cached
   here: the page says plainly when it cannot reach the server. */
const SHELL = "finn-shell-v1";
const FILES = ["/", "/app.css", "/app.js", "/manifest.json", "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== SHELL).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  e.respondWith(
    fetch(e.request).then(r => {
      if (r.ok && FILES.includes(url.pathname)) { const copy = r.clone(); caches.open(SHELL).then(c => c.put(url.pathname, copy)); }
      return r;
    }).catch(() => caches.match(e.request.mode === "navigate" ? "/" : url.pathname).then(m => m || Response.error()))
  );
});
