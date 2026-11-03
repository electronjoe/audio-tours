// Offline support for every tour under this directory.
// Audio files have content-hashed names, so they are cache-first. So is player code the
// pages load with ?v=<hash> (publish.player_version): an old page from the cache then runs
// its own old code, never today's, whose markup it lacks ("Couldn't load the tour"). Everything
// else (pages, tour.json) is network-first with a short timeout, falling back to the cache,
// so updates arrive when online and the tour still opens offline.
const CACHE = "audio-tours";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  if (req.headers.has("range")) return; // media range requests go to the network untouched
  const url = new URL(req.url);
  if (/\.mp3$/.test(url.pathname)) e.respondWith(cacheFirst(req));
  else if (url.searchParams.has("v")) e.respondWith(cacheFirst(req, url));
  else e.respondWith(networkFirst(req));
});

/** `versioned`: also drop the file's other ?v= copies once this one is cached. */
async function cacheFirst(req, versioned) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) {
    await cache.put(req, res.clone());
    if (versioned) {
      for (const old of await cache.keys(req, { ignoreSearch: true }))
        if (old.url !== req.url) await cache.delete(old);
    }
  }
  return res;
}

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await Promise.race([
      fetch(req),
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 4000)),
    ]);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req, { ignoreSearch: true });
    if (hit) return hit;
    throw err;
  }
}
