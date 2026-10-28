const CACHE_VERSION = 'treasuryflow-v12';

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => {
      return cache.addAll([
        '/static/img/brand/icon_192.png',
        '/static/img/brand/icon_512.png',
        '/static/img/brand/logo_128.png',
      ]);
    })
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET' || !event.request.url.startsWith(self.location.origin)) {
    return;
  }
  const url = new URL(event.request.url);
  const isStaticAsset = url.pathname.startsWith('/static/') || url.pathname === '/favicon.ico';
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (isStaticAsset && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_VERSION + '-dynamic').then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.filter((name) => name !== CACHE_VERSION && name !== CACHE_VERSION + '-dynamic').map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});
