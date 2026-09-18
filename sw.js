const CACHE="bux-safari-v4";
const FILES=["./","./index.html","./manifest.json","./icon-192.png","./icon-512.png"];
self.addEventListener("install",e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES)).catch(()=>{}).then(()=>self.skipWaiting()));});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==CACHE).map(x=>caches.delete(x)))).then(()=>self.clients.claim()));});
self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET") return;
  if(e.request.url.indexOf("supabase.co")>-1) return;      // server so'rovlari keshlanmaydi
  e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(e.request,c)).catch(()=>{});return r;})
    .catch(()=>caches.match(e.request).then(r=>r||caches.match("./index.html"))));
});
self.addEventListener("notificationclick",e=>{e.notification.close();
  e.waitUntil(clients.matchAll({type:"window",includeUncontrolled:true}).then(l=>{for(const c of l)if("focus" in c)return c.focus();return clients.openWindow("./");}));});
