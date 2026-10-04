const CACHE_VERSION = 'treasuryflow-v11';

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => {
      return cache.addAll([
        '/',
        '/static/img/brand/icon_192.png',
        '/static/img/brand/icon_512.png',
        '/static/img/brand/logo_128.png',
      ]);
    })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (event.request.method === 'GET' && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_VERSION + '-dynamic').then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request).then((response) => {
          return response || caches.match('/');
        });
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
