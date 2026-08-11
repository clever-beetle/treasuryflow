self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open('treasuryflow-v1').then((cache) => {
      return cache.addAll([
        '/',
        '/static/img/logo.png',
      ]);
    })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
