// Nome do cache
const CACHE_NAME = 'cashbaze-v1';

// Arquivos para salvar no celular do usuário
const urlsToCache = [
  '/',
  '/index.html',
  '/login.html',
  '/app.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];

// Instalando o Service Worker
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

// Interceptando as requisições para rodar offline
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        return response || fetch(event.request);
      })
  );
});