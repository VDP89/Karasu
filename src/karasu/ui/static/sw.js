/* sw.js — Karasu UI service worker (UI-8 + UI-12b + UI-13 + UI-14).
 *
 * Vanilla, dependency-free. Registered from index.html with a
 * feature-detection guard. Scoped to root via the
 * Service-Worker-Allowed: / header that src/karasu/ui/server.py
 * emits when serving this file.
 *
 * --- UI-14 §3-F SW Update Lifecycle Lock ---------------------
 *
 * This is the ONLY explicit deviation from a prior shape-lock
 * UI-14 earns. UI-8 sealed self.skipWaiting() on install +
 * self.clients.claim() on activate. UI-14 §3-F supersedes that
 * lifecycle for UPDATE events while preserving the FIRST-LOAD
 * shape:
 *
 *   FIRST-LOAD   (no existing controller): skipWaiting + claim
 *                — same as UI-8.
 *   UPDATE       (existing controller present): NEITHER
 *                skipWaiting NOR claim. The new SW installs as
 *                "waiting" until the page posts a
 *                {type:"SKIP_WAITING"} message in response to
 *                the user clicking the footer Refresh affordance
 *                (§3-B / §11.6.9). Then the page reloads.
 *
 * Detecting first-load vs update from inside the SW: at install
 * time the existing self.registration.active is null on first
 * load (no SW was previously controlling) and non-null on
 * update. Same shape works for activate.
 *
 * The fetch handler ordering + cache routing + pre-auth/post-auth
 * cache split (UI-13 §3-H) are UNCHANGED — UI-14 §3-F bounded the
 * deviation to install + activate + message handlers only.
 * tests/test_ui_sw.py keeps pinning the fetch handler shape.
 *
 * --- Cache split discipline (UI-13 §3-H binding) -------------
 *
 * UI-13 splits the cache into two named buckets:
 *
 *   PRE_AUTH_CACHE_NAME  = 'karasu-ui-login-v13'
 *   POST_AUTH_CACHE_NAME = 'karasu-ui-v13'
 *
 * The pre-auth cache is populated at install time with the
 * EXACT §3-H set (login surface + tokens / reset / base CSS +
 * crow.svg + 192 icon + manifest + fonts + sw.js itself).
 * The PWA app shell (bus-capable JS, modals, push.js, the rest
 * of the design-system CSS) is NOT pre-auth-cached — a logged-
 * out browser must NEVER serve those bytes from the SW.
 *
 * The post-auth cache fills lazily after the first
 * {type:"auth:granted"} postMessage from the page (sent on
 * successful login). It mirrors the UI-8 PWA shell shape.
 *
 * On {type:"auth:revoked"} the post-auth cache is dropped so
 * an expired-session browser falls back to the pre-auth cache
 * (which renders login when GET / hits the network and is
 * redirected, or paints offline.html when the network is
 * unreachable).
 *
 * Bump rule: bump the version suffix on EITHER cache name
 * whenever any of the assets in that cache change. The
 * activate handler deletes any cache whose name does not
 * match either canonical name, so a bumped value cleans up
 * the old shell on first navigation under the new SW.
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
 *      UI-13 §3-H pin §11.6.12: navigation IS network-first
 *      so an expired-session GET / lands at the server's
 *      redirect-to-login rather than being masked by the
 *      cached app shell.
 *   3. Static assets → cache-first against BOTH caches
 *      (pre-auth checked first, post-auth as fallback).
 *
 * The ordering is the contract. tests/test_ui_sw.py pins it
 * structurally (UI-12b pin §11.6.4 + UI-13 §3-H additions).
 *
 * --- Push handlers (UI-12b additive, unchanged) --------------
 */

/* UI-14 cache bump: v13 → v14. Pre-auth manifest body changed
 * (§3-A icons + colors); post-auth shell gained install.js +
 * the maskable PNG pair. Per the bump rule above, EITHER cache
 * change forces both names to advance. The activate handler
 * deletes any cache name not in the canonical set, so the v13
 * caches are dropped on the first activation under v14. */
const PRE_AUTH_CACHE_NAME = 'karasu-ui-login-v14';
const POST_AUTH_CACHE_NAME = 'karasu-ui-v14';

/* §3-H pre-auth EXACT set. The login surface must render
 * cleanly offline + a logged-out browser must NEVER see the
 * PWA shell. */
const PRE_AUTH_PRECACHE_URLS = [
    '/',
    '/assets/css/login.css',
    '/assets/css/tokens.css',
    '/assets/css/reset.css',
    '/assets/css/base.css',
    '/assets/crow/crow.svg',
    '/assets/icons/karasu-192.png',
    '/assets/manifest.json',
    /* Entire fonts dir — login surface uses the same Inter
     * Display + JetBrains Mono faces as the rest of the app. */
    '/assets/fonts/inter-display-400.woff2',
    '/assets/fonts/inter-display-500.woff2',
    '/assets/fonts/inter-display-700.woff2',
    '/assets/fonts/jetbrains-mono-400.woff2',
    '/assets/fonts/jetbrains-mono-500.woff2',
    '/assets/fonts/jetbrains-mono-700.woff2',
];

/* §3-H post-auth set. Mirror of the UI-8 PWA shell pre-cache,
 * minus the login-only items already in the pre-auth cache.
 * Filled lazily on {type:"auth:granted"}. UI-14 additions:
 * the maskable icon pair (§3-A manifest entries) + install.js
 * (§3-B install affordance loaded by the authenticated shell). */
const POST_AUTH_PRECACHE_URLS = [
    '/offline.html',
    '/assets/css/timeline.css',
    '/assets/css/crow.css',
    '/assets/css/map.css',
    '/assets/css/drawer.css',
    '/assets/crow/crow-flight.svg',
    '/assets/icons/karasu-512.png',
    '/assets/icons/karasu-maskable-192.png',   // UI-14 §3-A
    '/assets/icons/karasu-maskable-512.png',   // UI-14 §3-A
    '/assets/js/push.js',
    '/assets/js/install.js',                   // UI-14 §3-B
];

/* UI-14 §3-F SW Update Lifecycle Lock — distinguish first-load
 * from update. Inside install/activate, ``self.registration.active``
 * is null on first-load (no SW was previously controlling) and
 * non-null on update. The lifecycle helpers below honour the
 * UI-14 lock without leaking to fetch handler / cache routing. */
function isFirstLoad() {
    return self.registration && !self.registration.active;
}

self.addEventListener('install', (event) => {
    /* Codex round 3 P1 audit binding 2026-05-08: a SW
     * version bump while the operator already has a valid
     * session would cache the authenticated PWA shell HTML
     * under the pre-auth ``/`` key (the install fetch
     * carries cookies by default, so the server returns
     * index.html instead of login.html). Force the
     * navigation precache to fetch with credentials omitted
     * so the response is always the login render. The other
     * pre-auth assets (CSS / fonts / icons) are static —
     * cookies do not affect their bodies — so they keep the
     * default cache.addAll path. */
    const navRequest = new Request('/', { credentials: 'omit' });
    const otherUrls = PRE_AUTH_PRECACHE_URLS.filter((u) => u !== '/');
    event.waitUntil(
        caches.open(PRE_AUTH_CACHE_NAME).then((cache) =>
            Promise.all([cache.add(navRequest), cache.addAll(otherUrls)])
        )
    );
    /* UI-14 §3-F SEALED — skipWaiting ONLY on first-load. On an
     * UPDATE event, the new SW installs as "waiting" and stays
     * there until the page posts {type:"SKIP_WAITING"} in
     * response to the user clicking the footer Refresh
     * affordance (§3-B / §11.6.9 mutual exclusion with the
     * install slot). UI-8's eager swap is preserved for the
     * fresh-install case so a brand-new operator does not face
     * a pointless "Update available" beat on first paint. */
    if (isFirstLoad()) {
        self.skipWaiting();
    }
});

self.addEventListener('activate', (event) => {
    const canonical = new Set([PRE_AUTH_CACHE_NAME, POST_AUTH_CACHE_NAME]);
    event.waitUntil(
        caches.keys().then((names) =>
            Promise.all(
                names
                    .filter((name) => !canonical.has(name))
                    .map((name) => caches.delete(name))
            )
        )
    );
    /* UI-14 §3-F SEALED — clients.claim ONLY on first-load.
     * On an UPDATE event the new SW does NOT take over open
     * tabs; the user explicitly opts in via the footer
     * Refresh affordance which posts SKIP_WAITING and reloads.
     * Aggressive claim on a deployed PWA mid-read disrupts UX. */
    if (isFirstLoad()) {
        self.clients.claim();
    }
    /* UI-14 §3-B / §11.6.9 — broadcast install-prompt-reset to
     * any open page so install.js clears its 30-day dismiss
     * key. The install affordance "may have evolved" with the
     * new SW (manifest, icons, prompt copy) and the user
     * deserves a fresh chance. matchAll with
     * includeUncontrolled:true catches tabs that still answer
     * to the old SW so we don't depend on clients.claim. */
    event.waitUntil(
        self.clients
            .matchAll({ type: 'window', includeUncontrolled: true })
            .then((clients) => {
                for (const client of clients) {
                    try {
                        client.postMessage({ type: 'install-prompt-reset' });
                    } catch (_) {
                        /* postMessage to a closing client may
                         * throw — the broadcast is best-effort. */
                    }
                }
            })
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    /* 1. /api/* — network-only, always. */
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(fetch(event.request));
        return;
    }

    /* 2. Navigation — try network, fall back to offline.html on
     *    failure. UI-13 §3-H pin §11.6.12: this is the network-
     *    first behaviour the brief binds for navigation. */
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(() => caches.match('/offline.html'))
        );
        return;
    }

    /* 3. Static assets — cache-first. ``caches.match()``
     *    without a ``cacheName`` option queries every named
     *    cache in turn, so a single key (e.g. /assets/css/
     *    tokens.css) lands the pre-auth bucket before the
     *    post-auth bucket. The pre-auth set is byte-identical
     *    to its post-auth counterpart for shared keys, so the
     *    bucket precedence is informational. */
    event.respondWith(
        caches.match(event.request).then((hit) => hit || fetch(event.request))
    );
});

/* --- UI-13 §3-H message handler ------------------------------
 *
 * The page sends {type:"auth:granted"} on successful login and
 * {type:"auth:revoked"} on logout / 401 / redirect-to-/auth
 * from /api/*. The SW reflects the cache state accordingly.
 */
self.addEventListener('message', (event) => {
    const data = event.data || {};
    if (data.type === 'auth:granted') {
        event.waitUntil(
            caches
                .open(POST_AUTH_CACHE_NAME)
                .then((cache) => cache.addAll(POST_AUTH_PRECACHE_URLS))
                .catch(() => {
                    /* Best-effort precache — if a single asset is
                     * 404 (e.g. the operator hasn't generated the
                     * 512 icon yet) we still want the swap to
                     * complete so subsequent fetches land. */
                })
        );
        return;
    }
    if (data.type === 'auth:revoked') {
        event.waitUntil(caches.delete(POST_AUTH_CACHE_NAME));
        return;
    }
    /* UI-14 §3-F SEALED — the page posts SKIP_WAITING in
     * response to the user clicking the footer Refresh
     * affordance. The waiting SW takes over; the page then
     * reloads on controllerchange. NO other side effect. */
    if (data.type === 'SKIP_WAITING') {
        self.skipWaiting();
        return;
    }
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
