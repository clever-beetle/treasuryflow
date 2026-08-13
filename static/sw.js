self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open('treasuryflow-v4').then((cache) => {
      return cache.addAll([
        '/',
        '/static/img/logo_v4.png',
      ]);
    })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // Cache the latest version if successful
        if (event.request.method === 'GET' && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open('treasuryflow-v4-dynamic').then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // Fallback to cache if offline
        return caches.match(event.request);
      })
  );
});

self.addEventListener('activate', (event) => {
  // Clear old caches to force updates
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.filter((name) => !name.startsWith('treasuryflow-v4')).map((name) => caches.delete(name))
      );
    })
  );
});
