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
 * --- State machine (§3-B SEALED) -----------------------------
 *
 * Four states, written verbatim into the footer line:
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

    /* deferredPrompt holds the BeforeInstallPromptEvent so the
     * footer click handler can re-fire it. The browser only
     * dispatches the event once; capturing + storing is the
     * documented pattern. */
    let deferredPrompt = null;

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

    /* ---------------- rendering --------------------------- */

    /* The footer slot has three children: a state span, an
     * inline hint span (only used in iOS "ready"), and a dismiss
     * button (only used in "available"). render() flips the
     * state class, the visible label, and the hint / dismiss
     * visibility from a single source of truth. */
    function render(state) {
        const root = document.getElementById(ROOT_ID);
        if (!root) {
            return;
        }
        const labelEl = root.querySelector('.footer-install-state');
        const hintEl = root.querySelector('.footer-install-hint');
        const dismissEl = root.querySelector('.footer-install-dismiss');

        root.classList.remove(
            'is-unsupported',
            'is-available',
            'is-ready',
            'is-installed'
        );
        root.classList.add('is-' + state);

        if (labelEl) {
            labelEl.textContent = state;
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

        /* The state label gets a click handler + keyboard
         * activation ONLY in "available". iOS "ready" is read-
         * only — UI-14 §3-B SEALED: the install gesture is
         * browser-native, the inline hint is the affordance.
         * A <span> is not focusable by default, so flip
         * role="button" + tabindex dynamically; without these
         * the keydown listener never receives Tab+Enter. */
        if (labelEl) {
            if (state === 'available') {
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
        if (isInstalled()) {
            return 'installed';
        }
        if (deferredPrompt) {
            return readDismissed() ? 'unsupported' : 'available';
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
                     * until the explicit × dismiss. */
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
         * any browser-driven nag for the install gesture. */
        event.preventDefault();
        deferredPrompt = event;
        rerender();
    }

    function onAppInstalled() {
        deferredPrompt = null;
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

    function init() {
        const root = document.getElementById(ROOT_ID);
        if (!root) {
            return;
        }
        const labelEl = root.querySelector('.footer-install-state');
        const dismissEl = root.querySelector('.footer-install-dismiss');
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
        window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
        window.addEventListener('appinstalled', onAppInstalled);

        /* SW broadcast listener. The 'install-prompt-reset'
         * message is dispatched by sw.js on activate (UI-14
         * commit 4 §3-F deliverable). The listener is wired
         * up-front so the contract holds regardless of
         * commit ordering. */
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.addEventListener('message', onSWMessage);
        }

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
