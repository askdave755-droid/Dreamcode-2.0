const CACHE_NAME = 'dreamdecode-v3';
const urlsToCache = [
  '/',
  '/index.html',
  '/index.css'
];

// Install: cache fresh assets and activate immediately (don't wait for old SW to die)
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(urlsToCache))
  );
});

// Activate: delete ALL old caches (v1/v2) so no stale version survives, then take control
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Never intercept non-GET (API calls pass straight through)
  if (request.method !== 'GET') return;

  // Never cache API responses
  if (request.url.includes('/api/')) return;

  // HTML pages: network-first so new deploys appear immediately, cache as offline fallback
  if (request.mode === 'navigate' || request.destination === 'document') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match('/index.html')))
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request))
  );
});
