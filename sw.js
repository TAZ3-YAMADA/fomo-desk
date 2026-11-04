/* Desk shell. Do not log request URLs: data paths are secret. */
var CACHE = "desk-v1";
var SHELL = [
  "./",
  "./index.html",
  "./app.css",
  "./app.js",
  "./chart.js",
  "./manifest.json",
  "./icons/icon.svg",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(SHELL);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (key) {
        return key !== CACHE;
      }).map(function (key) {
        return caches.delete(key);
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

function fromCache(request) {
  return caches.match(request).then(function (hit) {
    if (hit) return hit;
    return caches.match("./index.html");
  });
}

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") return;

  var url;
  try { url = new URL(request.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;

  if (url.pathname.indexOf("/d/") !== -1) {
    event.respondWith(
      fetch(request, { redirect: "manual", cache: "no-store" }).then(function (response) {
        if (response.type === "opaqueredirect" || !response.ok) {
          return response.type === "opaqueredirect" ? Promise.reject() : response;
        }
        var copy = response.clone();
        caches.open(CACHE).then(function (cache) {
          return cache.put(request, copy);
        }).catch(function () {});
        return response;
      }).catch(function () {
        return caches.match(request).then(function (hit) {
          if (!hit) return Promise.reject();
          return hit.blob().then(function (body) {
            var headers = new Headers(hit.headers);
            headers.set("X-Desk-From-Cache", "1");
            return new Response(body, { status: hit.status, headers: headers });
          });
        });
      }).catch(function () {
        return new Response("", { status: 504, statusText: "Offline" });
      })
    );
    return;
  }

  event.respondWith(
    fetch(request).then(function (response) {
      if (response && response.ok) {
        var copy = response.clone();
        caches.open(CACHE).then(function (cache) {
          return cache.put(request, copy);
        }).catch(function () {});
      }
      return response;
    }).catch(function () {
      return fromCache(request);
    })
  );
});
