// Round 47 — Block 3.2: PWA Service Worker.
// Provides an offline shell — the app loads even without network.
// Data fetches fail gracefully with cached data + an "offline" indicator.
// No offline editing (pilot simplicity).

const CACHE_NAME = 'maestro-v1';
const OFFLINE_URLS = [
  '/app.html',
  '/static/css/maestro-bumble.css',
  '/static/css/invisible-maestro.css',
  '/static/js/maestro.js',
  '/static/js/today.js',
  '/static/js/mode-tabs.js',
  '/static/js/swipe-cards.js',
];

// Install — cache the offline shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(OFFLINE_URLS))
  );
  self.skipWaiting();
});

// Activate — clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.filter(name => name !== CACHE_NAME).map(name => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch — cache-first for static assets, network-first for API calls
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API calls — network-first, fall back to nothing (don't cache API responses)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        // Return a generic offline response for API calls
        return new Response(
          JSON.stringify({ error: 'You are offline. Please reconnect.' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
      })
    );
    return;
  }

  // Static assets — cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        // Cache successful responses
        if (response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      });
    })
  );
});
