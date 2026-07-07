/* 서비스워커 — 네트워크 우선(network-first) 전략.
 *
 * 원칙: "조용히 오래된 데이터"를 보여주지 않는다.
 *  - 온라인이면 항상 네트워크 응답을 쓰고, 성공한 응답만 캐시에 갱신한다.
 *  - 오프라인일 때만 캐시로 폴백한다(화면의 '업데이트: N시간 전' 표기가
 *    데이터가 오래됐음을 그대로 드러낸다).
 */
const CACHE = "disparity-v1";
const SHELL = [
  "./",
  "index.html",
  "app.js",
  "styles.css",
  "manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  // 외부 CDN(chart.js)은 브라우저 기본 캐시에 맡긴다.
  if (!req.url.startsWith(self.location.origin)) return;

  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(req, clone));
        }
        return res;
      })
      .catch(() =>
        caches.match(req, { ignoreSearch: true }).then((hit) => {
          if (hit) return hit;
          throw new Error("offline & not cached");
        })
      )
  );
});
