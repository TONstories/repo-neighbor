// Only immutable public build files and the public shell may be cached.
const cacheName = "rn-shell-v1";
self.addEventListener("install", (event) =>
  event.waitUntil(
    (async () => {
      const cache = await caches.open(cacheName);
      const shell = await fetch("/", { cache: "reload" });
      if (!shell.ok) throw Error("Shell unavailable");
      const html = await shell.clone().text();
      await cache.addAll([
        ...new Set(html.match(/\/assets\/[\w.-]+\.(?:js|css)/g) || []),
      ]);
      await cache.put("/", shell);
      await self.skipWaiting();
    })(),
  ),
);
self.addEventListener("activate", (event) =>
  event.waitUntil(self.clients.claim()),
);
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname === "/" && !url.search) {
    event.respondWith(fetch(event.request).catch(() => caches.match("/")));
  } else if (/^\/assets\/[\w.-]+\.(js|css)$/.test(url.pathname)) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(cacheName);
        const hit = await cache.match(event.request);
        if (hit) return hit;
        const response = await fetch(event.request);
        if (response.ok) await cache.put(event.request, response.clone());
        return response;
      })(),
    );
  }
});
