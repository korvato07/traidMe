const CACHE = 'traidme-v1';
const STATIC = ['/', '/dashboard', '/algo', '/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // API calls — network only
  if (e.request.url.includes('/api/') || e.request.url.includes('/ws')) return;
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
