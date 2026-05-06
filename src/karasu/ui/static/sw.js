/* sw.js — Karasu UI service worker (UI-8 + UI-12b).
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
 * The ordering is the contract. tests/test_ui_sw.py pins it
 * structurally (UI-12b pin §11.6.4).
 *
 * --- Push handlers (UI-12b additive) -------------------------
 *
 * UI-12b adds two SW event listeners independent of the fetch
 * handler: ``push`` (renders an OS-level notification when
 * UI-12c emits) and ``notificationclick`` (focuses an existing
 * surface tab or opens a new one). Both register without
 * touching the fetch handler ordering — the additive-only
 * claim is proved by tests/test_ui_sw.py.
 *
 * UI-12b ships with no server-side emit; the push listener is
 * registered for forward-compat. UI-12c earns the VAPID JWT
 * dispatch path that actually delivers messages here.
 */

const CACHE_NAME = 'karasu-ui-v12b';

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
    /* UI-12b — push.js carries the modal flow + two-phase
     * mutation rollback paths. Precached so the offline shell
     * and the live page share the same byte-identical script
     * (pin §11.6.4 — fetch ordering keeps /api/* network-only;
     * /assets/* including push.js is cache-first). */
    '/assets/js/push.js',
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

/* --- UI-12b push handlers (additive) -------------------------
 *
 * The push listener fires when the operating system delivers a
 * Web Push message to this worker. UI-12b ships only the
 * receiver — UI-12c earns the server-side dispatch path that
 * actually sends messages here, gated by the cryptography dep
 * named under UI-12 §11.6.13. Until UI-12c lands, no message
 * ever reaches this listener; registering it is forward-compat.
 *
 * Payload shape (the one UI-12c will produce):
 *
 *   { "title":    "<editorial single sentence>",
 *     "category": "attention" | "errors" | "corrections",
 *     "url":      "/",
 *     "event_id": "<bus event id>" }
 *
 * Per UI-12 §3-H the body is intentionally empty so the
 * notification reads as one editorial line; the title carries
 * the meaning. A payload-less wakeup ping (push service kept-
 * alive, etc.) falls back to a generic "Karasu" title rather
 * than rendering a blank notification.
 *
 * tag = "karasu" (singular) so a fresh push REPLACES any
 * pending notification rather than stacking — the operator
 * gets the latest pulse, not a queue.
 */
self.addEventListener('push', (event) => {
    let payload = {};
    if (event.data) {
        try {
            payload = event.data.json();
        } catch {
            payload = {};
        }
    }
    const title = (typeof payload.title === 'string' && payload.title)
        ? payload.title
        : 'Karasu';
    const data = {
        url: typeof payload.url === 'string' ? payload.url : '/',
        category: typeof payload.category === 'string' ? payload.category : null,
        event_id: typeof payload.event_id === 'string' ? payload.event_id : null,
    };
    const options = {
        body: '',
        icon: '/assets/icons/karasu-192.png',
        badge: '/assets/icons/karasu-192.png',
        tag: 'karasu',
        data,
        silent: false,
        requireInteraction: false,
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

/* The notificationclick listener routes the click to an
 * existing surface tab when one is open (focus it), or opens a
 * new one at the configured url. The Web Notifications spec
 * requires the click handler to call event.notification.close()
 * explicitly — without it the OS can leave the notification
 * lingering after the user dismissed it.
 */
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const data = event.notification.data || {};
    const url = typeof data.url === 'string' ? data.url : '/';
    event.waitUntil(
        self.clients
            .matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                for (const client of clientList) {
                    /* Match on pathname, not full URL — a surface
                     * tab on http://localhost:8000/ should focus
                     * for a notification whose data.url is "/". */
                    try {
                        const clientPath = new URL(client.url).pathname;
                        if (clientPath === url && 'focus' in client) {
                            return client.focus();
                        }
                    } catch {
                        /* malformed client.url — try next client */
                    }
                }
                if (self.clients.openWindow) {
                    return self.clients.openWindow(url);
                }
                return undefined;
            })
    );
});
