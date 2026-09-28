/* Service worker for بيت الخبرة: push notifications + open the right screen on tap.
   No caching on purpose — the app always loads fresh from the network. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {}); // installability; network as usual

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { title: "بيت الخبرة", body: e.data && e.data.text() }; }
  const title = d.title || "بيت الخبرة";
  const opts = {
    body: d.body || "",
    icon: "/assets/icon-192.png",
    badge: "/assets/icon-192.png",
    tag: d.tag || ("bk-" + (d.id || Date.now())),
    dir: "rtl", lang: "ar",
    data: { url: d.url || "/tools.html" },
  };
  e.waitUntil((async () => {
    await self.registration.showNotification(title, opts);
    try { if (d.badge != null && self.navigator.setAppBadge) await self.navigator.setAppBadge(d.badge); } catch (_) {}
  })());
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/tools.html";
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) {
      if (c.url.includes("/tools.html")) { await c.focus(); c.postMessage({ type: "open", url }); return; }
    }
    await self.clients.openWindow(url);
  })());
});
