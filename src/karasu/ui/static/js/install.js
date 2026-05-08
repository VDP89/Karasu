/* install.js — Karasu PWA install affordance (UI-14 §3-B).
 *
 * Vanilla, dependency-free. Loaded via
 *   <script src="/assets/js/install.js" defer></script>
 * from index.html. Renders the fifth footer slot (after the
 * UI-3 / UI-12a four-slot family — version, last-event, crow,
 * push). Quiet text affordance, NO modal anywhere, NO banner,
 * NO toast — same constraint UI-8 audit pin #5 sealed for the
 * shell.
 *
 * --- State machine (§3-B + §3-F + §11.6.9 SEALED) ------------
 *
 * Five states, mutually exclusive (only ONE renders at a time
 * per §11.6.9 editorial-calm pin). The first four are install
 * states from §3-B; the fifth is the §3-F refresh affordance
 * sharing the same footer slot family.
 *
 *   unsupported : browser does not fire beforeinstallprompt AND
 *                 is not iOS Safari. Read-only. --fg-2.
 *   available   : Chromium / Edge / Android Chrome — captured
 *                 the deferred prompt event. --accent. Click
 *                 invokes the OS install dialog. A dismiss
 *                 button (×) is visible at the right edge and
 *                 persists "Not now" decisions for 30 days.
 *   ready       : iOS Safari — no beforeinstallprompt API but
 *                 the platform supports A2HS. --accent text +
 *                 inline hint "(Share → Add to Home Screen)" in
 *                 --fg-2. NO click handler; the install gesture
 *                 is browser-native and the educational
 *                 walk-through lives in docs/pwa-install.md.
 *   installed   : navigator.standalone === true OR
 *                 matchMedia('(display-mode: standalone)').
 *                 Read-only. --fg-2.
 *   update      : registration.waiting present — a NEW sw.js
 *                 has installed and is waiting for the operator
 *                 to opt in (§3-F SEALED — UI-14 §3-F SW Update
 *                 Lifecycle Lock). Renders "Update available."
 *                 in --accent + a Refresh button. Clicking the
 *                 button posts {type:"SKIP_WAITING"} to the
 *                 waiting SW and the page reloads on
 *                 controllerchange. The "update" state WINS in
 *                 decideState() so the install line yields per
 *                 §11.6.9 mutual exclusion.
 *
 * --- Dismiss persistence (§3-B SEALED) -----------------------
 *
 * The dismiss state lives in localStorage as
 *   karasu.install.dismissed_at  (ISO-8601 string)
 *
 * and ONLY the dismiss state. No session material, no operator
 * state, no event projection ever materialises in localStorage
 * (UI-12b §11.6.16 carry-forward; UI-14 re-binds for install).
 *
 * Re-show triggers:
 *   - 30 days have passed since dismiss.
 *   - The SW posts {type:"install-prompt-reset"} on activate
 *     (signaling the operator the surface evolved). The SW
 *     broadcast itself lands in UI-14 commit 4 (sw.js §3-F
 *     update strategy); this listener is forward-compatible.
 */

(function () {
    'use strict';

    const STORAGE_KEY = 'karasu.install.dismissed_at';
    const RESHOW_AFTER_MS = 30 * 24 * 60 * 60 * 1000;
    const ROOT_ID = 'footer-install';

    /* §3-F SEALED — registration.update() poll cadence. 60 min
     * matches the brief "every 60 minutes (or on navigation
     * event, whichever fires first)". The browser fires its own
     * navigation-time update check; this interval covers the
     * long-running tab case. */
    const UPDATE_POLL_INTERVAL_MS = 60 * 60 * 1000;

    /* deferredPrompt holds the BeforeInstallPromptEvent so the
     * footer click handler can re-fire it. The browser only
     * dispatches the event once; capturing + storing is the
     * documented pattern. */
    let deferredPrompt = null;

    /* installCapable is sticky for the page session — set true
     * the FIRST time the browser dispatches beforeinstallprompt
     * and never cleared. §11.6.14 SEALED — when the page is
     * dismissed within the 30-day window the affordance still
     * renders as "available" (truthful: the platform supports
     * install) and ONLY the click is gated. Without a sticky
     * capability flag, a dismissed slot would fall through to
     * "unsupported" because deferredPrompt has been consumed
     * by prompt.prompt() — that is Codex round-2 P1.
     *
     * Same flag covers the post-decline beat: prompt.prompt()
     * consumes the event so deferredPrompt becomes null, but
     * the platform is still capable and the brief says the
     * slot returns to "available" (best-effort; click stays a
     * no-op until the browser re-fires beforeinstallprompt
     * after fresh engagement signals). */
    let installCapable = false;

    /* updateRegistration holds the live SW registration so the
     * refresh affordance can read .waiting and post SKIP_WAITING
     * to it. Populated by setupUpdateLifecycle() on init. */
    let updateRegistration = null;

    /* ---------------- environment detection ---------------- */

    function isInstalled() {
        if (typeof window.matchMedia === 'function') {
            try {
                if (window.matchMedia('(display-mode: standalone)').matches) {
                    return true;
                }
            } catch (_) {
                /* matchMedia threw on a malformed query — fall
                 * through to the iOS Safari shape below. */
            }
        }
        /* iOS Safari exposes navigator.standalone (boolean) when
         * the page is launched from the home screen. Outside iOS
         * Safari the property is undefined. */
        if (typeof window.navigator.standalone === 'boolean') {
            return window.navigator.standalone === true;
        }
        return false;
    }

    function isIOSSafari() {
        const ua = window.navigator.userAgent || '';
        const isIOS = /iPad|iPhone|iPod/.test(ua);
        if (!isIOS) {
            return false;
        }
        /* Exclude in-app browsers and Chrome/Firefox/Edge on iOS
         * (which all run on top of WebKit but disable A2HS). */
        if (/CriOS|FxiOS|EdgiOS|OPiOS|GSA/.test(ua)) {
            return false;
        }
        return /Safari/.test(ua);
    }

    /* ---------------- dismiss persistence ----------------- */

    function readDismissed() {
        let raw = null;
        try {
            raw = window.localStorage.getItem(STORAGE_KEY);
        } catch (_) {
            /* localStorage may throw in private browsing or when
             * the quota is exhausted. Treat as not-dismissed. */
            return false;
        }
        if (!raw) {
            return false;
        }
        const ts = Date.parse(raw);
        if (Number.isNaN(ts)) {
            /* Corrupt value — treat as not-dismissed and rewrite
             * defensively on the next dismiss. */
            return false;
        }
        return (Date.now() - ts) < RESHOW_AFTER_MS;
    }

    function writeDismissed() {
        try {
            window.localStorage.setItem(STORAGE_KEY, new Date().toISOString());
        } catch (_) {
            /* localStorage may throw — the affordance keeps
             * working in-memory for the rest of the session, the
             * dismiss just won't survive a reload. */
        }
    }

    function clearDismissed() {
        try {
            window.localStorage.removeItem(STORAGE_KEY);
        } catch (_) {
            /* see writeDismissed */
        }
    }

    /* ---------------- update affordance ------------------- */

    function isUpdatePending() {
        return updateRegistration !== null
            && typeof updateRegistration === 'object'
            && updateRegistration.waiting !== null
            && updateRegistration.waiting !== undefined;
    }

    /* ---------------- rendering --------------------------- */

    /* The footer slot has four children: a state span, an
     * inline hint span (iOS "ready" only), a dismiss button
     * ("available" only), and a Refresh button ("update" only).
     * render() flips the state class plus each child's content
     * + visibility from a single source of truth, honouring
     * §11.6.9 mutual exclusion (only ONE of {dismiss, refresh}
     * can be visible at a time, and the label text follows the
     * winning state). */
    function render(state) {
        const root = document.getElementById(ROOT_ID);
        if (!root) {
            return;
        }
        const labelEl = root.querySelector('.footer-install-state');
        const hintEl = root.querySelector('.footer-install-hint');
        const dismissEl = root.querySelector('.footer-install-dismiss');
        const refreshEl = root.querySelector('.footer-install-refresh');

        root.classList.remove(
            'is-unsupported',
            'is-available',
            'is-ready',
            'is-installed',
            'is-update'
        );
        root.classList.add('is-' + state);

        /* §11.6.14 SEALED + Codex round-2 P1 — when the slot is
         * "available" but the dismiss key is inside its 30-day
         * window, signal the muted-but-still-capable beat with a
         * sub-state class. The state class stays is-available
         * (truthful capability); the modifier dims the line and
         * tells CSS to hide the × button (re-clicking dismiss is
         * a no-op). The modifier is removed in every other state
         * (the click gating in onLabelClick is the procedural
         * counterpart). */
        root.classList.remove('is-dismissed');
        if (state === 'available' && readDismissed()) {
            root.classList.add('is-dismissed');
        }

        if (labelEl) {
            /* §3-F SEALED copy. The install states (un / avail
             * / ready / installed) write the bare state word
             * after the static "Install: " prefix in markup;
             * the update state replaces the prefix line with
             * a full sentence per the brief. */
            if (state === 'update') {
                labelEl.textContent = 'Update available.';
            } else {
                labelEl.textContent = state;
            }
        }

        if (hintEl) {
            if (state === 'ready') {
                hintEl.textContent = '(Share → Add to Home Screen)';
                hintEl.hidden = false;
            } else {
                hintEl.textContent = '';
                hintEl.hidden = true;
            }
        }

        if (dismissEl) {
            dismissEl.hidden = state !== 'available';
        }

        if (refreshEl) {
            refreshEl.hidden = state !== 'update';
        }

        /* The state label gets a click handler + keyboard
         * activation ONLY in the actionable "available" sub-
         * state — i.e. state === 'available' AND the dismiss
         * key is OUTSIDE its 30-day window. iOS "ready" is
         * read-only (UI-14 §3-B SEALED — the install gesture is
         * browser-native, the inline hint is the affordance).
         * "update" routes activation through the dedicated
         * Refresh button, not the label.
         *
         * Codex round-2 P2 (2026-05-08): the dismiss-within-
         * window beat keeps state === 'available' (truthful
         * platform capability per §11.6.14) but onLabelClick
         * short-circuits via readDismissed(). Exposing
         * role="button" + tabindex="0" + pointer cursor on a
         * label whose click is no-op misleads keyboard /
         * screen-reader users. Strip the button affordance in
         * the dismissed sub-state — the visual signal lives in
         * the is-dismissed CSS modifier, the procedural signal
         * lives here.
         *
         * A <span> is not focusable by default, so flip
         * role="button" + tabindex dynamically; without these
         * the keydown listener never receives Tab+Enter. */
        if (labelEl) {
            const labelActionable = state === 'available' && !readDismissed();
            if (labelActionable) {
                labelEl.setAttribute('role', 'button');
                labelEl.setAttribute('tabindex', '0');
                labelEl.style.cursor = 'pointer';
            } else {
                labelEl.removeAttribute('role');
                labelEl.removeAttribute('tabindex');
                labelEl.style.cursor = '';
            }
        }
    }

    function decideState() {
        /* §11.6.9 mutual exclusion — refresh affordance wins
         * over the install affordance when both could render.
         * The install line yields. */
        if (isUpdatePending()) {
            return 'update';
        }
        if (isInstalled()) {
            return 'installed';
        }
        /* §11.6.14 SEALED + Codex round-2 P1 — installCapable is
         * sticky once the browser fires beforeinstallprompt.
         * That truthfully reflects "the platform supports
         * install" regardless of whether deferredPrompt has been
         * consumed by a click or whether the dismiss key is
         * inside its 30-day window. The dismiss / declined cases
         * are surfaced visually (is-dismissed modifier in
         * render()) and procedurally (onLabelClick gates the
         * click) without lying about platform capability. */
        if (installCapable) {
            return 'available';
        }
        if (isIOSSafari()) {
            return 'ready';
        }
        return 'unsupported';
    }

    function rerender() {
        render(decideState());
    }

    /* ---------------- wiring ------------------------------ */

    function onLabelClick(event) {
        /* Only react in "available" — the state class on the
         * root is the single source of truth. */
        const root = document.getElementById(ROOT_ID);
        if (!root || !root.classList.contains('is-available')) {
            return;
        }
        /* §11.6.14 SEALED + Codex round-2 P1 — the click is
         * a no-op when:
         *   1. dismiss key is inside the 30-day window (the
         *      slot renders dimmed via is-dismissed but stays
         *      truthfully "available"; the action waits until
         *      the window expires or a SW activate broadcasts
         *      install-prompt-reset);
         *   2. deferredPrompt is null because prompt.prompt()
         *      already consumed the BeforeInstallPromptEvent
         *      (the browser may re-fire on a later engagement
         *      tick; until then the click cannot do anything).
         * Both cases keep the state truthful and the action
         * gated procedurally — that is the §11.6.14 split. */
        if (readDismissed()) {
            return;
        }
        if (!deferredPrompt) {
            return;
        }
        event.preventDefault();
        const prompt = deferredPrompt;
        deferredPrompt = null;
        prompt.prompt();
        prompt.userChoice
            .then(function (choice) {
                if (choice && choice.outcome === 'accepted') {
                    /* The browser will fire 'appinstalled' on
                     * success; the listener below handles the
                     * state transition. Be defensive and force
                     * a render in case the event misses. */
                    render('installed');
                } else {
                    /* User declined the OS dialog — do NOT
                     * auto-dismiss; the slot remains "available"
                     * (installCapable stays sticky) so the next
                     * beforeinstallprompt fire restores the
                     * actionable click. */
                    rerender();
                }
            })
            .catch(function () {
                rerender();
            });
    }

    function onDismissClick(event) {
        event.preventDefault();
        event.stopPropagation();
        writeDismissed();
        rerender();
    }

    function onBeforeInstallPrompt(event) {
        /* Capture the event so the click handler can re-fire it.
         * preventDefault() suppresses the browser's own install
         * promotion surface — UI-8 audit pin #5 sealed against
         * any browser-driven nag for the install gesture.
         *
         * §11.6.14 SEALED — set installCapable sticky on first
         * dispatch so decideState() can return "available"
         * (truthful) regardless of whether deferredPrompt is
         * later consumed or whether the dismiss key is inside
         * its 30-day window. */
        event.preventDefault();
        deferredPrompt = event;
        installCapable = true;
        rerender();
    }

    function onAppInstalled() {
        deferredPrompt = null;
        installCapable = false;
        clearDismissed();
        render('installed');
    }

    function onSWMessage(event) {
        const data = (event && event.data) || {};
        if (data.type === 'install-prompt-reset') {
            clearDismissed();
            rerender();
        }
    }

    function onRefreshClick(event) {
        event.preventDefault();
        if (!isUpdatePending()) {
            return;
        }
        /* §3-F SEALED — post SKIP_WAITING to the waiting SW.
         * sw.js listens for this exact message type and calls
         * self.skipWaiting() with NO other side effect. The
         * controllerchange listener (set in
         * setupUpdateLifecycle below) reloads the page once
         * the new SW takes over. */
        try {
            updateRegistration.waiting.postMessage({ type: 'SKIP_WAITING' });
        } catch (_) {
            /* postMessage to a closing SW may throw — degrade
             * to a manual reload so the user gets feedback. */
            window.location.reload();
        }
    }

    function setupUpdateLifecycle() {
        if (!('serviceWorker' in navigator)) {
            return;
        }

        navigator.serviceWorker.ready
            .then(function (reg) {
                updateRegistration = reg;

                /* If a SW already finished installing in the
                 * background before this script loaded (e.g.
                 * an update landed mid-session), surface the
                 * affordance immediately. */
                if (reg.waiting) {
                    rerender();
                }

                /* Track future updates as the browser fetches
                 * sw.js and the new instance moves through
                 * installing → installed. The "controller
                 * present" guard distinguishes a true update
                 * (active controller exists; new SW will wait)
                 * from a fresh install (no controller; sw.js
                 * skipWaiting fires per §3-F). */
                reg.addEventListener('updatefound', function () {
                    const installing = reg.installing;
                    if (!installing) {
                        return;
                    }
                    installing.addEventListener('statechange', function () {
                        if (installing.state === 'installed'
                            && navigator.serviceWorker.controller) {
                            rerender();
                        }
                    });
                });

                /* §3-F SEALED — registration.update() poll
                 * every 60 minutes for the long-running tab
                 * case. Best-effort; failures are silent so a
                 * transient network error does not surface. */
                setInterval(function () {
                    reg.update().catch(function () {});
                }, UPDATE_POLL_INTERVAL_MS);
            })
            .catch(function () {
                /* SW registration failed — install affordance
                 * still works through beforeinstallprompt /
                 * iOS Safari paths; the update affordance is
                 * gated on a successful SW. */
            });

        /* §3-F SEALED — when the new SW takes over (via the
         * SKIP_WAITING message above OR a fresh install
         * skipWaiting), reload the page so the operator sees
         * the new shell. Registered ONCE at module load. */
        navigator.serviceWorker.addEventListener('controllerchange', function () {
            window.location.reload();
        });
    }

    function init() {
        const root = document.getElementById(ROOT_ID);
        if (!root) {
            return;
        }
        const labelEl = root.querySelector('.footer-install-state');
        const dismissEl = root.querySelector('.footer-install-dismiss');
        const refreshEl = root.querySelector('.footer-install-refresh');
        if (labelEl) {
            labelEl.addEventListener('click', onLabelClick);
            labelEl.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    /* Suppress the space-key scroll always so a
                     * focusable label never causes a page jump,
                     * even in a state where the click handler
                     * returns early. */
                    e.preventDefault();
                    onLabelClick(e);
                }
            });
        }
        if (dismissEl) {
            dismissEl.addEventListener('click', onDismissClick);
        }
        if (refreshEl) {
            refreshEl.addEventListener('click', onRefreshClick);
        }
        window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
        window.addEventListener('appinstalled', onAppInstalled);

        /* SW broadcast listener. The 'install-prompt-reset'
         * message is dispatched by sw.js on activate (§3-F
         * SEALED). Listener is wired up-front; cooperates with
         * the SKIP_WAITING / controllerchange flow registered
         * inside setupUpdateLifecycle. */
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.addEventListener('message', onSWMessage);
        }

        setupUpdateLifecycle();
        rerender();
    }

    /* The script tag is loaded with `defer`, so the document is
     * already parsed by the time this IIFE runs and the footer
     * element is reachable. Wire-up runs immediately. */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
