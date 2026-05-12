// Service Worker 3MV — v1.3
// Garante que o app mobile funcione offline e receba atualizações

const CACHE = '3mv-v1.3';
const PRECACHE = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
];

// Instala e pré-cacheia arquivos estáticos
self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE).catch(() => {}))
  );
});

// Ativa e limpa caches antigos
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Estratégia: network-first para HTML/JSON, cache-first para assets estáticos
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  
  // Não intercepta requisições externas (API Suas Vendas, Resend, etc.)
  if (url.origin !== self.location.origin) return;

  // HTML e JSON: sempre tenta rede primeiro (dados frescos)
  if (e.request.headers.get('accept')?.includes('text/html') ||
      url.pathname.endsWith('.json')) {
    e.respondWith(
      fetch(e.request)
        .then(r => {
          const clone = r.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return r;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Assets estáticos: cache-first
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(r => {
        if (r.ok) {
          const clone = r.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return r;
      });
    })
  );
});

// Push notifications (alertas automáticos)
self.addEventListener('push', e => {
  const data = e.data?.json() || {};
  const title = data.title || '🚨 Alerta 3MV';
  const options = {
    body: data.body || 'Há pendências no painel.',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: '3mv-alerta',
    renotify: true,
    data: { url: data.url || '/' },
  };
  e.waitUntil(self.registration.showNotification(title, options));
});

// Abre o painel ao clicar na notificação
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = e.notification.data?.url || '/';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(ws => {
      const win = ws.find(w => w.url.includes(self.location.origin));
      if (win) { win.focus(); win.navigate(url); }
      else clients.openWindow(url);
    })
  );
});
