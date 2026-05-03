// ═══════════════════════════════════════════════════════════
// SARATHI-AI — Service Worker (PWA)
// Strategy: Network-first for pages/API, Cache-first for assets
// Auto-updates: SW checks for new version on every page load
// ═══════════════════════════════════════════════════════════

const CACHE_VERSION = 'sarathi-v27';
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `dynamic-${CACHE_VERSION}`;

// Static assets to pre-cache on install
const PRE_CACHE = [
  '/',
  '/static/dark-mode.css?v=4',
  '/static/dark-mode.js?v=3',
  '/static/icon-192x192.png',
  '/static/icon-512x512.png',
  '/static/favicon.ico',
  '/static/logo.png'
];

// ── Install: pre-cache shell ─────────────────────────────
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(PRE_CACHE))
      .then(() => self.skipWaiting()) // activate immediately
  );
});

// ── Activate: clean old caches ───────────────────────────
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== STATIC_CACHE && k !== DYNAMIC_CACHE)
            .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim()) // take control of all tabs
  );
});

// ── Fetch: network-first for HTML/API, cache-first for assets ──
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // Skip non-GET requests
  if (e.request.method !== 'GET') return;

  // Skip external requests (fonts, CDN, Razorpay, etc.)
  if (url.origin !== self.location.origin) return;

  // API & HTML pages → Network-first (always fresh)
  if (e.request.mode === 'navigate' ||
      url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/health') ||
      url.pathname.startsWith('/login') ||
      url.pathname.startsWith('/webhook')) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          // Cache a copy for offline fallback
          if (res.ok && e.request.mode === 'navigate') {
            const clone = res.clone();
            caches.open(DYNAMIC_CACHE).then(c => c.put(e.request, clone));
          }
          return res;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Static assets → Cache-first with network fallback
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then(cached => {
        if (cached) return cached;
        return fetch(e.request).then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(STATIC_CACHE).then(c => c.put(e.request, clone));
          }
          return res;
        });
      })
    );
    return;
  }

  // Everything else → Network-first
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(DYNAMIC_CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

// ── Message: force update ────────────────────────────────
self.addEventListener('message', (e) => {
  if (e.data === 'skipWaiting') {
    self.skipWaiting();
  }
});
