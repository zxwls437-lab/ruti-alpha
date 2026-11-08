// RUTI 서비스 워커: 화면 파일만 저장해 빠르게 열고, 인터넷이 끊기면 안내 화면을 보여준다.
// 회원 정보·상담·분석 같은 API 응답은 절대 저장하지 않는다 (개인정보 보호).
const CACHE = 'ruti-v9';
const SHELL = ['/static/common.css', '/static/common.js', '/static/explain.js', '/static/offline.html',
  '/static/icons/icon-192.png', '/static/icons/icon-512.png'];
const PAGES = ['/scan', '/chat', '/community', '/mypage'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  // 화면 이동: 항상 최신을 먼저 받고, 실패하면 저장본 → 오프라인 안내
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then(res => {
      if (PAGES.includes(url.pathname) && res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(url.pathname, copy)); }
      return res;
    }).catch(async () => (await caches.match(url.pathname)) || caches.match('/static/offline.html')));
    return;
  }
  // 정적 파일: 저장본을 바로 쓰고 뒤에서 새로 받아 둠
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(caches.open(CACHE).then(async c => {
      const hit = await c.match(req);
      const fresh = fetch(req).then(res => { if (res.ok) c.put(req, res.clone()); return res; }).catch(() => hit);
      return hit || fresh;
    }));
  }
  // 그 밖의 요청(API)은 손대지 않음
});
