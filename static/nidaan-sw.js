// Nidaan Partner Service Worker
// Caches static UI assets for fast loads and basic offline support.

const CACHE_NAME = 'nidaan-v1';
const STATIC_ASSETS = [
  '/nidaan/dashboard',
  '/static/nidaan_dashboard.html',
  '/static/nidaan_start.html',
  '/static/nidaan_index.html',
  '/static/nidaan_logo.png',
  '/static/nidaan.webmanifest',
];

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      // Cache what we can — ignoring individual failures so install always succeeds
      return Promise.allSettled(
        STATIC_ASSETS.map(url => cache.add(url).catch(() => {}))
      );
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', function(event) {
  const url = new URL(event.request.url);

  // Only handle GET requests on same origin
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  // API requests — network only, never cache
  if (url.pathname.startsWith('/nidaan/api/') || url.pathname.startsWith('/internal/')) return;

  // Auth routes — network only (contain redirects)
  if (['/nidaan/login', '/nidaan/logout', '/nidaan/signup'].includes(url.pathname)) return;

  // For navigation and static assets: cache-first, fallback to network
  event.respondWith(
    caches.match(event.request).then(function(cached) {
      if (cached) return cached;
      return fetch(event.request).then(function(response) {
        // Cache fresh copies of static assets
        if (response.ok && (
          url.pathname.startsWith('/static/') ||
          url.pathname === '/nidaan/dashboard' ||
          url.pathname === '/nidaan/start'
        )) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
        }
        return response;
      }).catch(function() {
        // Offline fallback — show dashboard shell if navigating
        if (event.request.mode === 'navigate') {
          return caches.match('/nidaan/dashboard') || caches.match('/static/nidaan_dashboard.html');
        }
      });
    })
  );
});
