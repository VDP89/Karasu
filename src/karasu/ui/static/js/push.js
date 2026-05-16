/* push.js — UI-12b push opt-in surface client logic.
 *
 * Wires the footer affordance click handler, the .modal#push-modal
 * dialog, and the two-phase mutation contract that keeps the
 * browser PushSubscription and the server-side karasu-push.json
 * store in agreement (UI-12b §3-B + pin §11.6.13).
 *
 * Brief invariants enforced here:
 *
 *   §3-A — modal entry from the footer affordance only;
 *          unsupported / denied state has NO click handler.
 *   §11.6.2 — Notification.requestPermission fires ONLY from
 *             the modal's primary "Enable notifications" click.
 *   §11.6.13 — subscribe rollback (subscription.unsubscribe()
 *              on every non-204 server response, no
 *              human_decision on rollback paths); unsubscribe
 *              is server-removal-first (POST → 204 → browser
 *              .unsubscribe()).
 *   §11.6.14 — when /api/push.vapid_public_key is null, modal
 *              opens but the primary is disabled; native prompt
 *              never fires from this state.
 *   §11.6.16 — endpoint sourced from
 *              registration.pushManager.getSubscription() ONLY
 *              for the unsubscribe path; never DOM /
 *              localStorage / cached values.
 *
 * Loaded BEFORE the inline <script> in index.html so the inline
 * init can call wirePushFooter() + wirePushModal(). Top-level
 * function declarations attach to the global object (window), so
 * the existing UI-10 / UI-11b / UI-12a code can reach the push
 * functions without import/export plumbing (UI-0 §4 — no
 * toolchain).
 */

/* Mirror of the closed enum in src/karasu/ui/push_store.py.
 * Kept as a literal so push.js stays standalone; if Karasu
 * ever extends categories the audit demands a fresh brief
 * which would touch both sides. */
const PUSH_CATEGORIES = ['attention', 'errors', 'corrections'];

/* Module-level state mirror — the latest /api/push payload so
 * the modal opens with the operator's current categories
 * pre-selected when re-opened post-subscribe. Refreshed on
 * each loadPushState() tick; the modal reads it on open. */
let latestPushPayload = null;

/* Body conversion helpers — kept tiny so the privacy contract
 * is auditable: only the documented fields cross to the wire. */
function pushSubscribeBody(subscription, categories) {
    /* PushSubscription.toJSON() returns {endpoint, expirationTime,
     * keys: {p256dh, auth}}. We strip expirationTime + extras and
     * only forward the documented brief §3-B fields. */
    const json = subscription.toJSON();
    return JSON.stringify({
        subscription: {
            endpoint: json.endpoint,
            keys: {
                p256dh: json.keys && json.keys.p256dh,
                auth: json.keys && json.keys.auth,
            },
        },
        categories,
    });
}

function pushUnsubscribeBody(subscription) {
    const json = subscription.toJSON();
    return JSON.stringify({ endpoint: json.endpoint });
}

/* base64url → Uint8Array for applicationServerKey (the VAPID
 * public key returned by /api/push). PushManager.subscribe
 * needs raw bytes, not the b64u string. */
function urlBase64ToUint8Array(b64u) {
    const padding = '='.repeat((4 - (b64u.length % 4)) % 4);
    const base64 = (b64u + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
}

/* --- Footer affordance click wiring ------------------------------ */

function wirePushFooter() {
    /* Pin §11.6.11 — unsupported / denied state has NO click
     * handler. The footer span stays passive read-only.
     *
     * Called from loadPushState() AFTER the state class is set,
     * so this function reads the class to decide whether the
     * affordance is interactive. */
    const root = document.getElementById('footer-push');
    if (!root) return;
    const interactive = root.classList.contains('is-on') ||
                        root.classList.contains('is-off');
    if (!interactive) {
        root.removeAttribute('role');
        root.removeAttribute('tabindex');
        root.style.cursor = '';
        root.onclick = null;
        root.onkeydown = null;
        return;
    }
    root.setAttribute('role', 'button');
    root.setAttribute('tabindex', '0');
    root.style.cursor = 'pointer';
    root.onclick = (ev) => {
        ev.preventDefault();
        openPushModal();
    };
    root.onkeydown = (ev) => {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        ev.preventDefault();
        openPushModal();
    };
}

/* --- Modal lifecycle --------------------------------------------- */

function isPushModalOpen() {
    const modal = document.getElementById('push-modal');
    return !!modal && !modal.hasAttribute('hidden');
}

function setPushModalError(text) {
    const err = document.getElementById('push-modal-error');
    if (!err) return;
    if (text) {
        err.textContent = text;
        err.removeAttribute('hidden');
    } else {
        err.textContent = '';
        err.setAttribute('hidden', '');
    }
}

function openPushModal() {
    /* The modal opens with the categories pre-selected from
     * latestPushPayload (post-subscribe layout) or all three
     * pre-checked (pre-subscribe layout per brief §10.1). */
    const modal = document.getElementById('push-modal');
    const backdrop = document.getElementById('modal-backdrop');
    if (!modal || !backdrop) return;

    const subscribed = !!latestPushPayload &&
                       latestPushPayload.subscription_count > 0;
    const vapidProvisioned = !!latestPushPayload &&
                             !!latestPushPayload.vapid_public_key;

    /* Pre-subscribe: all three categories checked per §10.1.
     * Post-subscribe: we only know the COUNT from /api/push
     * (the per-subscription categories never cross the read
     * boundary per pin §11.6.5). The modal therefore opens
     * with all three checked and the operator unchecks any
     * they want to drop; the "Update categories" path will
     * UPDATE the store with the new validated set.
     *
     * Codex audited this: the operator's per-browser
     * categories are not knowable to the surface, but the
     * UPDATE path is idempotent and emits a fresh
     * push_subscribe event, so the operator setting
     * "everything" then unchecking is the operator-feel
     * pin's "deliberate confirm" loop. */
    for (const input of modal.querySelectorAll('input[name="push-category"]')) {
        input.checked = true;
    }

    const stateRow = document.getElementById('push-modal-state');
    const unsubBtn = document.getElementById('push-modal-unsubscribe');
    const confirmBtn = document.getElementById('push-modal-confirm');
    const footCopy = document.getElementById('push-modal-foot-copy');

    if (subscribed) {
        stateRow.textContent =
            'Subscribed: ' + latestPushPayload.subscription_count +
            (latestPushPayload.subscription_count === 1 ? ' subscription' : ' subscriptions');
        stateRow.removeAttribute('hidden');
        unsubBtn.removeAttribute('hidden');
        confirmBtn.textContent = 'Update categories';
    } else {
        stateRow.setAttribute('hidden', '');
        unsubBtn.setAttribute('hidden', '');
        confirmBtn.textContent = 'Enable notifications';
    }

    /* Pin §11.6.14 — when vapid_public_key is null, the modal
     * opens but the primary is DISABLED + the foot copy
     * surfaces the operator-actionable reason. The native
     * permission prompt MUST NOT fire from this state.
     *
     * Brief §3-H amendment 2026-05-16 (closes phase-4-dogfood
     * Finding #3 sub-friction 3): the foot copy surfaces the
     * runnable CLI command (`karasu watch`) inline instead of
     * just pointing at a doc. An operator inside the standalone
     * PWA window does not have a terminal handy and previously
     * had to switch contexts just to learn what to type. */
    if (!vapidProvisioned) {
        confirmBtn.disabled = true;
        confirmBtn.setAttribute('aria-disabled', 'true');
        footCopy.textContent =
            'VAPID keys not provisioned. Run `karasu watch` in a ' +
            'terminal once to bootstrap.';
    } else {
        confirmBtn.disabled = false;
        confirmBtn.removeAttribute('aria-disabled');
        footCopy.textContent =
            'Confirming will ask your browser for notification permission.';
    }

    setPushModalError(null);
    modal.removeAttribute('hidden');
    backdrop.classList.add('modal-open');
    void modal.getBoundingClientRect();
    document.getElementById('push-modal-cancel').focus();
}

function closePushModal() {
    const modal = document.getElementById('push-modal');
    const backdrop = document.getElementById('modal-backdrop');
    if (!modal || !backdrop) return;
    modal.setAttribute('hidden', '');
    /* Only release the backdrop if no other modal is open. The
     * UI-10 + UI-11b modals share the backdrop class. */
    const otherOpen = (
        (document.getElementById('revoke-modal') &&
         !document.getElementById('revoke-modal').hasAttribute('hidden')) ||
        (document.getElementById('trust-modal') &&
         !document.getElementById('trust-modal').hasAttribute('hidden'))
    );
    if (!otherOpen) {
        backdrop.classList.remove('modal-open');
    }
}

/* --- Two-phase subscribe + rollback (pin §11.6.13) ------------- */

function selectedPushCategories() {
    const out = [];
    for (const input of document.querySelectorAll('input[name="push-category"]:checked')) {
        out.push(input.value);
    }
    return out;
}

async function confirmPushSubscribe() {
    const confirmBtn = document.getElementById('push-modal-confirm');
    if (!confirmBtn || confirmBtn.disabled) return;
    confirmBtn.disabled = true;
    setPushModalError(null);

    const categories = selectedPushCategories();
    const vapidPublic = latestPushPayload && latestPushPayload.vapid_public_key;
    if (!vapidPublic) {
        /* Should not be reachable — the disabled gate above
         * covers it — but defensive in case of a race against
         * a fresh /api/push response. */
        setPushModalError('VAPID keys not provisioned.');
        confirmBtn.disabled = false;
        return;
    }

    const subscribed = !!latestPushPayload && latestPushPayload.subscription_count > 0;

    /* Update-categories path (pin §11.6.16): when the operator
     * is already subscribed, we do NOT call PushManager.subscribe
     * again (that would re-prompt the OS). Instead we read the
     * existing PushSubscription from the browser and POST it
     * with the new categories. The endpoint comes from
     * registration.pushManager.getSubscription() — never from
     * the DOM, localStorage, or cached values. */
    if (subscribed) {
        try {
            const reg = await navigator.serviceWorker.ready;
            const existing = await reg.pushManager.getSubscription();
            if (!existing) {
                /* Browser-side state diverged from the store
                 * (operator unsubscribed via OS). The modal
                 * should show no subscribed state next time
                 * loadPushState runs — close + bail. */
                setPushModalError(
                    'Browser is no longer subscribed. Close and re-open the modal.'
                );
                confirmBtn.disabled = false;
                return;
            }
            const r = await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: pushSubscribeBody(existing, categories),
            });
            if (r.status !== 204) {
                setPushModalError('Update failed (' + r.status + '). Try again.');
                confirmBtn.disabled = false;
                return;
            }
            closePushModal();
            /* Refresh footer state. */
            if (typeof loadPushState === 'function') await loadPushState();
            return;
        } catch (err) {
            setPushModalError('Network error. Try again.');
            confirmBtn.disabled = false;
            return;
        }
    }

    /* Pre-subscribe path: native permission prompt → subscribe
     * → POST → on non-204, ROLLBACK via subscription.unsubscribe(). */
    let permission;
    try {
        permission = await Notification.requestPermission();
    } catch {
        setPushModalError('Permission prompt failed.');
        confirmBtn.disabled = false;
        return;
    }
    if (permission !== 'granted') {
        /* Pin §3.5 + audit clarification: native deny path
         * emits NO bus event, calls NO POST, and PushManager
         * .subscribe was NEVER called. Footer flips to denied
         * via the next loadPushState (it reads
         * Notification.permission directly). */
        closePushModal();
        if (typeof loadPushState === 'function') await loadPushState();
        return;
    }

    let subscription;
    try {
        const reg = await navigator.serviceWorker.ready;
        subscription = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidPublic),
        });
    } catch (err) {
        setPushModalError('Push service unreachable. Try again.');
        confirmBtn.disabled = false;
        return;
    }

    /* Server POST. Any non-204 triggers the rollback so the
     * push service never holds a subscription Karasu does not
     * know about. */
    let postOk = false;
    try {
        const r = await fetch('/api/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: pushSubscribeBody(subscription, categories),
        });
        postOk = r.status === 204;
    } catch {
        postOk = false;
    }

    if (!postOk) {
        /* Pin §11.6.13 binding: rollback BEFORE user-visible
         * feedback. Browser unsubscribes; no human_decision
         * lands; the surface refresh shows zero subscriptions. */
        try { await subscription.unsubscribe(); } catch { /* best-effort */ }
        setPushModalError('Server rejected subscription. Try again.');
        confirmBtn.disabled = false;
        return;
    }

    closePushModal();
    if (typeof loadPushState === 'function') await loadPushState();
}

/* --- Two-phase unsubscribe (pin §11.6.13) --------------------- */

async function confirmPushUnsubscribe() {
    const unsubBtn = document.getElementById('push-modal-unsubscribe');
    if (!unsubBtn) return;
    unsubBtn.disabled = true;
    setPushModalError(null);

    let subscription;
    try {
        const reg = await navigator.serviceWorker.ready;
        subscription = await reg.pushManager.getSubscription();
    } catch {
        subscription = null;
    }

    if (!subscription) {
        /* Browser-side already gone (orphaned store entry, or
         * OS-level revocation). UI-12b leaves orphans for
         * UI-12c 410 prune; close the modal so the operator
         * does not see a hung state. */
        closePushModal();
        if (typeof loadPushState === 'function') await loadPushState();
        return;
    }

    /* Server-removal-first per pin §11.6.13. POST 204 → browser
     * unsubscribe. POST 404 (orphaned store) → treat as success +
     * still call browser unsubscribe; the bus carries ZERO new
     * events on the 404 path (server silence = audit truth). */
    let serverStatus = 0;
    try {
        const r = await fetch('/api/push/unsubscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: pushUnsubscribeBody(subscription),
        });
        serverStatus = r.status;
    } catch {
        serverStatus = 0;
    }

    if (serverStatus !== 204 && serverStatus !== 404) {
        setPushModalError(
            'Server-side removal failed (' + serverStatus + '). Try again.'
        );
        unsubBtn.disabled = false;
        return;
    }

    /* Browser unsubscribe AFTER server confirms. If this
     * rejects, the store is empty but the browser still holds
     * the subscription; the retry path will see POST 404 (audit
     * silence) + a fresh getSubscription() that resolves
     * successfully on the second attempt. */
    try {
        await subscription.unsubscribe();
    } catch {
        setPushModalError(
            'Server-side removed but browser unsubscribe failed. Retry.'
        );
        unsubBtn.disabled = false;
        return;
    }

    closePushModal();
    if (typeof loadPushState === 'function') await loadPushState();
}

/* --- Modal wire-up ----------------------------------------------- */

function wirePushModal() {
    const cancelBtn = document.getElementById('push-modal-cancel');
    const confirmBtn = document.getElementById('push-modal-confirm');
    const unsubBtn = document.getElementById('push-modal-unsubscribe');
    if (!cancelBtn || !confirmBtn || !unsubBtn) return;

    cancelBtn.addEventListener('click', closePushModal);
    confirmBtn.addEventListener('click', confirmPushSubscribe);
    unsubBtn.addEventListener('click', confirmPushUnsubscribe);

    /* First Esc closes the push modal (pin parity with UI-10 /
     * UI-11b modal Esc behaviour). The drawer-level Esc handler
     * in index.html skips when ANY modal is open; the modal-
     * level Esc handler in wireModal() also handles the push
     * modal because closeModal() in index.html closes both
     * revoke + trust modals — push is a third sibling. To keep
     * push self-contained, we add a dedicated Esc handler that
     * runs only when the push modal is open. */
    document.addEventListener('keydown', (ev) => {
        if (ev.key !== 'Escape') return;
        if (!isPushModalOpen()) return;
        ev.stopPropagation();
        closePushModal();
    });

    /* Backdrop click closes the modal (pin parity with UI-10). */
    const backdrop = document.getElementById('modal-backdrop');
    if (backdrop) {
        backdrop.addEventListener('click', () => {
            if (isPushModalOpen()) closePushModal();
        });
    }
}

/* --- Read-side hook: the inline loadPushState calls into us ---- */

function recordPushPayload(payload) {
    /* Inline loadPushState in index.html calls this with the
     * /api/push response so the modal-open path can pre-fill
     * the Subscribed: N line + the disabled-primary branch on
     * VAPID-null. */
    latestPushPayload = payload;
}
