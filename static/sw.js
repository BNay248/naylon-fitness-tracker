const CACHE_NAME = 'tracker-shell-v4';
const CORE_ASSETS = [
  '/',
  '/foods',
  '/history',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return; // never intercept POST/PATCH/DELETE — let the app's own queue handle those
  const url = new URL(request.url);
  if (url.pathname.startsWith('/api/')) return; // always hit the network; app JS handles offline fallback itself

  // App shell / pages: network-first so you get the latest version when online,
  // falling back to cache so the page still opens with no connection at all.
  if (request.mode === 'navigate' || CORE_ASSETS.includes(url.pathname)) {
    event.respondWith(
      fetch(request)
        .then(res => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          return res;
        })
        .catch(() => caches.match(request).then(cached => cached || caches.match('/')))
    );
    return;
  }

  // Static assets (css/js/icons under /static/): cache-first, network as fallback/refresh
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(cached => {
        const fetchPromise = fetch(request).then(res => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          return res;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    );
  }
});
