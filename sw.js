/* =========================================================================
   3MV Painel Mobile - Service Worker
   Estrategia:
     - HTML / logo / manifest: cache-first com refresh em background
     - dados.json do Painel: NETWORK-FIRST (sempre tenta rede; cai pra cache se offline)
     - tudo o mais: pass-through (sem cache)
   ========================================================================= */

const VERSAO = 'pm-v1';
const CACHE  = '3mv-painel-mobile-' + VERSAO;

const ATIVOS = [
  './',
  'painel-mobile.html',
  'manifest.json',
  'logo_3mv_branca.png',
  'logo_3mv_quadrado.png',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ATIVOS).catch(() => {})).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // dados.json: network-first (sempre tenta puxar atualizado)
  if (url.pathname.endsWith('/dados.json')) {
    e.respondWith(
      fetch(e.request).then(resp => {
        const copy = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
        return resp;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  // Worker API (escrita): nunca cacheia
  if (url.pathname.startsWith('/api/field/')) {
    return; // segue rede normal
  }

  // Assets estaticos do app: cache-first com refresh em background
  if (e.request.method === 'GET' && (
        url.pathname.endsWith('.html') ||
        url.pathname.endsWith('.png')  ||
        url.pathname.endsWith('.json') ||
        url.pathname.endsWith('.js'))) {
    e.respondWith(
      caches.match(e.request).then(cached => {
        const rede = fetch(e.request).then(resp => {
          if (resp && resp.ok) {
            const copy = resp.clone();
            caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
          }
          return resp;
        }).catch(() => cached);
        return cached || rede;
      })
    );
  }
});

self.addEventListener('message', e => {
  if (e.data === 'limpar-cache') {
    caches.delete(CACHE);
  }
});
