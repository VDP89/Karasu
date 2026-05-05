/* sw.js — Karasu UI service worker (UI-8).
 *
 * Vanilla, dependency-free. Registered from index.html with a
 * feature-detection guard. Scoped to root via the
 * Service-Worker-Allowed: / header that src/karasu/ui/server.py
 * emits when serving this file.
 *
 * --- Cache version discipline ---------------------------------
 *
 * CACHE_NAME embeds the chunk version. The bump rule (Codex P1
 * binding from the UI-8 design review):
 *
 *   Bump CACHE_NAME whenever sw.js, offline.html, manifest.json,
 *   the static CSS files, fonts, or the crow assets change.
 *
 * The activate handler deletes any cache whose name does not
 * match CACHE_NAME, so a bumped value cleans up the old shell
 * on first navigation under the new SW.
 *
 * --- Fetch handler ordering (Codex P1, P0-on-regression) -----
 *
 *   1. /api/* → network-only. Live state must NEVER be served
 *      from cache; a cached /api/events is exactly the
 *      "looks live but isn't" failure UI is designed to avoid.
 *   2. Navigation requests → try network, fall back to
 *      /offline.html on failure. The cached offline shell
 *      reads the last-known bus_path from localStorage and
 *      paints the perched crow in the .offline pose.
 *   3. Static assets → cache-first. Only after the /api/ +
 *      navigate branches have already returned. Any refactor
 *      that lets /api/* fall through to caches.match() is a
 *      P0 regression.
 *
 * The ordering is the contract.
 */

const CACHE_NAME = 'karasu-ui-v8';

/* Static manifest precached on install. The list is the minimum
 * set the offline page + the application shell need to render
 * editorially when the network is unreachable. /api/* is NOT in
 * the manifest by design. */
const PRECACHE_URLS = [
    '/',
    '/offline.html',
    '/assets/manifest.json',
    '/assets/css/tokens.css',
    '/assets/css/reset.css',
    '/assets/css/base.css',
    '/assets/css/timeline.css',
    '/assets/css/crow.css',
    '/assets/css/map.css',
    '/assets/css/drawer.css',
    '/assets/crow/crow.svg',
    '/assets/crow/crow-flight.svg',
    '/assets/icons/karasu-192.png',
    '/assets/icons/karasu-512.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
    );
    /* Skip the wait so a freshly installed SW activates on the
     * next page load without requiring a manual refresh. The
     * cleanup in activate handles any older caches. */
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) =>
            Promise.all(
                names
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            )
        )
    );
    /* Take control of any clients that were already loaded under
     * the previous SW so the fetch handler ordering applies
     * immediately. */
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    /* 1. /api/* — network-only, always. */
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(fetch(event.request));
        return;
    }

    /* 2. Navigation — try network, fall back to offline.html on
     *    failure. The cached offline.html is the editorial
     *    fallback; the live shell is preferred when the network
     *    is reachable. */
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(() => caches.match('/offline.html'))
        );
        return;
    }

    /* 3. Static assets — cache-first. Reaches here ONLY after
     *    the /api/ + navigate branches have already returned;
     *    /api/* requests cannot fall through to this match by
     *    construction. */
    event.respondWith(
        caches.match(event.request).then((hit) => hit || fetch(event.request))
    );
});
