// Maestro Service Worker v2
// Stale-while-revalidate for API, cache-first for static, offline fallback.
const CACHE_NAME = 'maestro-v2';
const API_CACHE = 'maestro-api-v2';
const STATIC_ASSETS = [
  '/',
  '/app.html',
  '/static/css/tokens.css',
  '/static/css/design-system.css',
  '/static/css/maestro-bumble.css',
  '/static/js/utils.js',
  '/static/js/state.js',
  '/static/js/components/card.js',
  '/static/js/components/focus-trap.js',
  '/static/js/perf-monitor.js',
  '/static/js/bundle.min.js',
  '/static/js/sw-register.js',
  '/static/js/vendor/lucide.min.js',
  '/static/manifest.json',
  '/static/favicon.ico',
];

// Install — cache the app shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate — clean up old caches, claim clients
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== API_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch — stale-while-revalidate for API, cache-first for static
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET requests (mutations, POSTs)
  if (event.request.method !== 'GET') return;

  // API calls — stale-while-revalidate
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      caches.open(API_CACHE).then(async (cache) => {
        const cached = await cache.match(event.request);
        const fetchPromise = fetch(event.request)
          .then((response) => {
            if (response.ok) {
              cache.put(event.request, response.clone());
            }
            return response;
          })
          .catch(() => {
            // If network fails and we have cache, return cached
            if (cached) return cached;
            // Otherwise return offline response
            return new Response(
              JSON.stringify({ error: 'You are offline. Showing last cached data.', offline: true }),
              { status: 503, headers: { 'Content-Type': 'application/json' } }
            );
          });
        // Return cached immediately if available, otherwise wait for network
        return cached || fetchPromise;
      })
    );
    return;
  }

  // Static assets — cache-first (immutable with content hash)
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clone);
          });
        }
        return response;
      }).catch(() => {
        // Offline fallback for navigation requests
        if (event.request.mode === 'navigate') {
          return caches.match('/app.html');
        }
      });
    })
  );
});
