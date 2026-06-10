// Nidaan Partner Service Worker
// v2 — network-first for HTML (so price/copy changes propagate immediately),
//      cache-first for /static/* assets (images, fonts, manifest).
// Cache version is bumped on every product-content change.

const CACHE_NAME = 'nidaan-v2';

// Only pre-cache truly-immutable assets — NOT HTML.
const STATIC_ASSETS = [
  '/static/nidaan_logo.png',
  '/static/nidaan.webmanifest',
];

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return Promise.allSettled(STATIC_ASSETS.map(url => cache.add(url).catch(() => {})));
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      // Purge ALL old cache versions on activate.
      return Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)));
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', function(event) {
  const url = new URL(event.request.url);

  // Only handle same-origin GETs
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  // API / internal / auth → network only, never cache
  if (url.pathname.startsWith('/nidaan/api/') ||
      url.pathname.startsWith('/internal/') ||
      ['/nidaan/login', '/nidaan/logout', '/nidaan/signup', '/nidaan/start'].includes(url.pathname)) {
    return;
  }

  // Navigation / HTML pages → NETWORK FIRST (so copy/price changes show immediately).
  // Fallback to cached copy only if offline.
  const isNavigation = event.request.mode === 'navigate' ||
                       (event.request.headers.get('accept') || '').includes('text/html');
  if (isNavigation) {
    event.respondWith(
      fetch(event.request).then(function(response) {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
        }
        return response;
      }).catch(function() {
        return caches.match(event.request)
          || caches.match('/nidaan/dashboard')
          || caches.match('/static/nidaan_dashboard.html');
      })
    );
    return;
  }

  // Static assets (images, fonts, manifest, css, js) → CACHE FIRST, network fallback.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(function(cached) {
        if (cached) return cached;
        return fetch(event.request).then(function(response) {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
          }
          return response;
        });
      })
    );
  }
});
