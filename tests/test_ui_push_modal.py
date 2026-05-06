"""Playwright regression for the UI-12b push opt-in modal.

Pin §11.6.13 binding (Codex round 2 audit): the four browser
flows below are mandatory before merge. The HTTP shape locks
in tests/test_ui_server_http.py already pin the wire contracts
on the server side; this module covers the BROWSER side of the
two-phase mutation contract — the contract that keeps the
browser PushSubscription and the server-side
karasu-push.json store in agreement.

The four flows:

  test_subscribe_post_failure_rolls_back_browser
    Server POST returns 503. Browser subscription.unsubscribe()
    fires; bus has zero push_subscribe events; modal foot
    surfaces an editorial error.

  test_unsubscribe_browser_call_is_made_after_204
    Server POST returns 204. Browser subscription.unsubscribe()
    fires AFTER the 204 lands. Bus carries exactly one
    push_unsubscribe.

  test_unsubscribe_404_converges_with_no_bus_event
    Store empty (parallel pruner case). Server POST returns
    404. Browser unsubscribe still fires; bus has ZERO new
    push_unsubscribe events; both sides converge to
    unsubscribed.

  test_unsubscribe_browser_failure_after_204_can_retry_via_404
    First attempt: POST 204 (server emits one); browser
    unsubscribe rejects; modal foot shows error. Retry: POST
    404 (server already empty); browser unsubscribe succeeds.
    Total bus push_unsubscribe count = exactly 1 across both
    attempts.

Skipped silently when Playwright is not installed so the rest
of the suite stays green for contributors who skip the optional
browser dependency. The mocks for navigator.serviceWorker /
PushManager are injected via page.add_init_script so the page
sees the documented Web Push API surface against in-memory
deterministic stand-ins (headless Chromium has no real push
service).
"""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from karasu.ui import server as ui_server

playwright = pytest.importorskip("playwright.sync_api")


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def push_http(tmp_path: Path) -> Iterator[tuple[str, int, Path, Path]]:
    """Stand up the UI server with a per-test event log + push
    store. Returns (host, port, bus, push_store)."""
    original_event_log = ui_server.EVENT_LOG
    original_scars_path = ui_server.SCARS_PATH
    original_config_path = ui_server.CONFIG_PATH
    original_push_store = ui_server.PUSH_STORE_PATH
    bus = tmp_path / "events.jsonl"
    push_store = tmp_path / "karasu-push.json"
    ui_server.configure(
        event_log=bus,
        scars_path=tmp_path / "scars",
        config_path=tmp_path / "karasu.yaml",
        push_store_path=push_store,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.UIHandler)
    thread = threading.Thread(
        target=server.serve_forever, name="karasu-ui-push-test", daemon=True
    )
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield host, port, bus, push_store
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        ui_server.configure(
            event_log=original_event_log,
            scars_path=original_scars_path,
            config_path=original_config_path,
            push_store_path=original_push_store,
        )


def _seed_vapid(push_store: Path) -> None:
    """Seed VAPID public + private so the server-side 503 gate
    does not fire AND the client's urlBase64ToUint8Array
    decoder accepts the public key.

    The public key is a valid 65-byte b64u-encoded P-256
    uncompressed point placeholder (0x04 prefix + 64 zero
    bytes). 86 b64u chars, zero padding — the format
    PushManager.subscribe expects for applicationServerKey.
    Real keys are non-zero; this fixture only needs to be
    syntactically valid to flow through the client-side
    decode without throwing."""
    push_store.write_text(
        json.dumps({
            "vapid": {
                "public": (
                    "BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
                    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
                ),
                "private": "PRIVKEY-DO-NOT-LEAK",
            },
            "subscriptions": [],
        }),
        encoding="utf-8",
    )


def _seed_subscription(push_store: Path, endpoint: str) -> None:
    """Seed the store with one subscription so the unsubscribe
    flow has something to remove."""
    raw = json.loads(push_store.read_text(encoding="utf-8"))
    raw.setdefault("subscriptions", []).append({
        "endpoint": endpoint,
        "endpoint_hash": "x" * 64,
        "keys": {"p256dh": "p", "auth": "a"},
        "categories": ["attention"],
        "created_at": "2026-05-06T00:00:00Z",
        "updated_at": "2026-05-06T00:00:00Z",
    })
    push_store.write_text(json.dumps(raw), encoding="utf-8")


def _bus_events(bus: Path) -> list[dict]:
    if not bus.exists():
        return []
    return [
        json.loads(line)
        for line in bus.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _push_decisions(bus: Path, action: str) -> list[dict]:
    return [
        e for e in _bus_events(bus)
        if e.get("type") == "human_decision"
        and e.get("data", {}).get("action") == action
    ]


# ---------------------------------------------------------------------------
# Mock Web Push API — injected into every page before page scripts run.
# Headless Chromium has no real push service, so pushManager.subscribe()
# and getSubscription() are stubbed to return a deterministic in-memory
# subscription object whose toJSON() carries a known endpoint + keys. The
# stub also tracks unsubscribe() calls + lets a test force the next
# unsubscribe() to reject (for the retry flow).
# ---------------------------------------------------------------------------


_PUSH_MOCK_INIT = r"""
(() => {
    const TEST_ENDPOINT =
        'https://fcm.googleapis.com/playwright-test-endpoint';

    let subscribed = window.__karasuPushTest && window.__karasuPushTest.preSubscribed;
    let nextUnsubscribeShouldFail = false;
    let unsubscribeCalls = 0;
    let subscribeCalls = 0;

    const fakeSubscription = {
        endpoint: TEST_ENDPOINT,
        toJSON() {
            return {
                endpoint: TEST_ENDPOINT,
                keys: { p256dh: 'mockP256dh', auth: 'mockAuth' },
            };
        },
        async unsubscribe() {
            unsubscribeCalls += 1;
            if (nextUnsubscribeShouldFail) {
                nextUnsubscribeShouldFail = false;
                throw new Error('synthetic browser unsubscribe failure');
            }
            subscribed = false;
            return true;
        },
    };

    /* Replace ServiceWorkerContainer.ready with a resolved
     * promise that exposes pushManager. We don't actually need
     * a SW to test the modal flow — push.js calls
     * navigator.serviceWorker.ready then reg.pushManager.*
     * which the stub satisfies. */
    Object.defineProperty(navigator, 'serviceWorker', {
        configurable: true,
        value: {
            ready: Promise.resolve({
                pushManager: {
                    async subscribe(opts) {
                        subscribeCalls += 1;
                        subscribed = true;
                        return fakeSubscription;
                    },
                    async getSubscription() {
                        return subscribed ? fakeSubscription : null;
                    },
                },
            }),
            register: () => Promise.resolve({}),
            addEventListener: () => {},
        },
    });

    /* The page also feature-detects PushManager / Notification
     * on `window`. Provide stubs so browserPushSupport()
     * returns 'supported'. */
    if (!('PushManager' in window)) {
        window.PushManager = function () {};
    }
    if (!('Notification' in window)) {
        window.Notification = {
            permission: 'default',
            requestPermission: async () => 'granted',
        };
    } else {
        const original = window.Notification.requestPermission;
        window.Notification.requestPermission = async () =>
            (window.__karasuPushTest && window.__karasuPushTest.permission) || 'granted';
        Object.defineProperty(window.Notification, 'permission', {
            configurable: true,
            get: () =>
                (window.__karasuPushTest && window.__karasuPushTest.notifPermission) ||
                'default',
        });
    }

    /* Expose the mock counters so tests can assert on them. */
    window.__karasuPushMockState = () => ({
        subscribed,
        unsubscribeCalls,
        subscribeCalls,
    });
    window.__karasuPushSetUnsubscribeFail = (fail) => {
        nextUnsubscribeShouldFail = fail;
    };
})();
"""


def _open_page(p, host: str, port: int, *, pre_subscribed: bool = False,
               permission: str = 'granted', notif_permission: str = 'default'):
    """Launch a Chromium page with the push mock injected. Returns
    (browser, context, page)."""
    browser = p.chromium.launch()
    context = browser.new_context()
    # Pre-permission grant lets the requestPermission() bypass
    # the OS-level prompt; we still mock at the JS level so the
    # test can flip permission state per-flow.
    context.grant_permissions(['notifications'], origin=f'http://{host}:{port}')
    page = context.new_page()

    # Seed test-control flags BEFORE any page script runs.
    page.add_init_script(
        f"window.__karasuPushTest = {{"
        f"  preSubscribed: {str(pre_subscribed).lower()},"
        f"  permission: {json.dumps(permission)},"
        f"  notifPermission: {json.dumps(notif_permission)},"
        f"}};"
    )
    page.add_init_script(_PUSH_MOCK_INIT)
    page.goto(f"http://{host}:{port}/")
    page.wait_for_load_state("networkidle")
    return browser, context, page


# ---------------------------------------------------------------------------
# Test 1 — Subscribe POST failure → browser rollback
# ---------------------------------------------------------------------------


def test_subscribe_post_failure_rolls_back_browser(
    push_http: tuple[str, int, Path, Path],
) -> None:
    """Pin §11.6.13 binding: any non-204 server response triggers
    subscription.unsubscribe() rollback BEFORE user-visible
    feedback; no human_decision emits on rollback paths."""
    host, port, bus, push_store = push_http
    _seed_vapid(push_store)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, context, page = _open_page(
            p, host, port,
            pre_subscribed=False,
            permission='granted',
            notif_permission='default',
        )
        try:
            # Mock the server-side subscribe POST to 503.
            page.route(
                "**/api/push/subscribe",
                lambda route: route.fulfill(status=503, body='{"error":"forced"}'),
            )

            # Footer must be in the "off" state (no subscription
            # in store; VAPID seeded) so the click handler attaches.
            page.wait_for_selector("#footer-push.is-off", timeout=5000)
            page.locator("#footer-push").click()
            page.locator("#push-modal").wait_for(state="visible", timeout=2000)

            # Confirm — push.js will call requestPermission +
            # subscribe() + POST → 503 → rollback.
            page.locator("#push-modal-confirm").click()

            # Modal should stay open with the editorial error.
            page.locator("#push-modal-error").wait_for(
                state="visible", timeout=3000
            )
            err_text = page.locator("#push-modal-error").inner_text()
            assert "Server rejected" in err_text or "rejected" in err_text.lower()

            # The mock counters: subscribe was called exactly
            # once, unsubscribe was called exactly once
            # (rollback).
            mock_state = page.evaluate("__karasuPushMockState()")
            assert mock_state["subscribeCalls"] == 1
            assert mock_state["unsubscribeCalls"] == 1
            assert mock_state["subscribed"] is False
        finally:
            browser.close()

    # No human_decision events on the bus.
    assert _push_decisions(bus, "push_subscribe") == []
    # Store still empty.
    raw = json.loads(push_store.read_text(encoding="utf-8"))
    assert raw["subscriptions"] == []


# ---------------------------------------------------------------------------
# Test 2 — Unsubscribe POST 204 → browser unsubscribe AFTER
# ---------------------------------------------------------------------------


def test_unsubscribe_browser_call_is_made_after_204(
    push_http: tuple[str, int, Path, Path],
) -> None:
    """Pin §11.6.13 binding: server-removal-first; on 204 the
    browser unsubscribe fires; bus carries exactly one
    push_unsubscribe."""
    host, port, bus, push_store = push_http
    _seed_vapid(push_store)
    _seed_subscription(
        push_store, "https://fcm.googleapis.com/playwright-test-endpoint"
    )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, context, page = _open_page(
            p, host, port,
            pre_subscribed=True,
            permission='granted',
            notif_permission='granted',
        )
        try:
            # Footer in the "on" state (one subscription in store).
            page.wait_for_selector("#footer-push.is-on", timeout=5000)
            page.locator("#footer-push").click()
            page.locator("#push-modal").wait_for(state="visible", timeout=2000)

            # Click Unsubscribe.
            page.locator("#push-modal-unsubscribe").click()

            # Modal should close on success.
            page.locator("#push-modal").wait_for(state="hidden", timeout=3000)

            mock_state = page.evaluate("__karasuPushMockState()")
            # Browser unsubscribe was called.
            assert mock_state["unsubscribeCalls"] == 1
            # No subscribe call was made.
            assert mock_state["subscribeCalls"] == 0
        finally:
            browser.close()

    # Exactly one push_unsubscribe on the bus.
    unsubs = _push_decisions(bus, "push_unsubscribe")
    assert len(unsubs) == 1
    # Store empty.
    raw = json.loads(push_store.read_text(encoding="utf-8"))
    assert raw["subscriptions"] == []


# ---------------------------------------------------------------------------
# Test 3 — Unsubscribe POST 404 (orphan) → browser still cleans up,
#          bus emits zero new events
# ---------------------------------------------------------------------------


def test_unsubscribe_404_converges_with_no_bus_event(
    push_http: tuple[str, int, Path, Path],
) -> None:
    """Pin §11.6.13 binding: 404 path = browser-cleanup
    success (subscription.unsubscribe still fires) AND bus
    emits ZERO new events (server silence = audit truth).

    Setup: store HAS a subscription (so the modal renders the
    unsubscribe verb in its post-subscribe layout) but the
    POST /api/push/unsubscribe is mocked to 404 — simulating a
    parallel pruner that emptied the store between the modal
    open and the POST."""
    host, port, bus, push_store = push_http
    _seed_vapid(push_store)
    _seed_subscription(
        push_store, "https://fcm.googleapis.com/playwright-test-endpoint"
    )
    initial_bus_count = len(_bus_events(bus))

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, context, page = _open_page(
            p, host, port,
            pre_subscribed=True,
            permission='granted',
            notif_permission='granted',
        )
        try:
            # Force POST /api/push/unsubscribe → 404
            page.route(
                "**/api/push/unsubscribe",
                lambda route: route.fulfill(
                    status=404,
                    body='{"error":"subscription not found"}',
                ),
            )

            page.wait_for_selector("#footer-push.is-on", timeout=5000)
            page.locator("#footer-push").click()
            page.locator("#push-modal").wait_for(state="visible", timeout=2000)
            page.locator("#push-modal-unsubscribe").click()

            # Modal closes (404 is treated as success on the
            # client per pin §11.6.13).
            page.locator("#push-modal").wait_for(state="hidden", timeout=3000)

            mock_state = page.evaluate("__karasuPushMockState()")
            # Browser unsubscribe DID fire on the 404 path
            # (browser-cleanup success).
            assert mock_state["unsubscribeCalls"] == 1
        finally:
            browser.close()

    # ZERO new push_unsubscribe events on the bus (server
    # silence = audit truth — pin §11.6.13).
    assert _push_decisions(bus, "push_unsubscribe") == []
    # Bus length unchanged from before this flow (no new
    # human_decision events of any kind on the 404 path).
    assert len(_bus_events(bus)) == initial_bus_count


# ---------------------------------------------------------------------------
# Test 4 — Browser unsubscribe rejection after server 204 → retry via 404
# ---------------------------------------------------------------------------


def test_unsubscribe_browser_failure_after_204_can_retry_via_404(
    push_http: tuple[str, int, Path, Path],
) -> None:
    """Pin §11.6.13 binding: full two-attempt flow.

    First attempt: POST 204 mutates the store + emits one
    push_unsubscribe. subscription.unsubscribe() rejects (one-
    shot via __karasuPushSetUnsubscribeFail(true)); the modal
    foot surfaces an editorial error and re-enables the
    Unsubscribe button.

    Retry: operator clicks Unsubscribe again WHILE THE MODAL
    IS STILL OPEN. push.js calls getSubscription() (returns
    the still-subscribed fake), POSTs /api/push/unsubscribe
    (server returns 404 because the first 204 already emptied
    the store), audit_emitted=false branch fires (no bus
    event), then subscription.unsubscribe() succeeds (the
    one-shot fail flag has reset), modal closes, footer flips
    to "off".

    Pin §11.6.13 binding: the bus push_unsubscribe count
    across BOTH attempts is exactly 1 (from the first 204);
    the 404 retry path emits zero events per the
    audit-event-correspondence invariant.
    """
    host, port, bus, push_store = push_http
    _seed_vapid(push_store)
    _seed_subscription(
        push_store, "https://fcm.googleapis.com/playwright-test-endpoint"
    )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, context, page = _open_page(
            p, host, port,
            pre_subscribed=True,
            permission='granted',
            notif_permission='granted',
        )
        try:
            page.wait_for_selector("#footer-push.is-on", timeout=5000)

            # First attempt — force the browser unsubscribe to
            # reject on the next call.
            page.evaluate("__karasuPushSetUnsubscribeFail(true)")
            page.locator("#footer-push").click()
            page.locator("#push-modal").wait_for(state="visible", timeout=2000)
            page.locator("#push-modal-unsubscribe").click()

            # Error surface (server-side removed via real 204
            # but browser unsubscribe rejected).
            page.locator("#push-modal-error").wait_for(
                state="visible", timeout=3000
            )

            mock_state = page.evaluate("__karasuPushMockState()")
            # Browser unsubscribe was attempted once + threw.
            assert mock_state["unsubscribeCalls"] == 1
            # Browser mock still claims subscribed=true because
            # the rejected unsubscribe didn't flip the flag.
            assert mock_state["subscribed"] is True
            # First 204 emitted exactly one push_unsubscribe.
            assert len(_push_decisions(bus, "push_unsubscribe")) == 1
            # Store IS empty (the 204 mutated it before the
            # browser unsubscribe rejected).
            raw = json.loads(push_store.read_text(encoding="utf-8"))
            assert raw["subscriptions"] == []

            # Retry — modal is still open, button re-enabled.
            # confirmPushUnsubscribe will:
            #   1. getSubscription() → still-subscribed fake.
            #   2. POST /api/push/unsubscribe → real server
            #      returns 404 (store already empty).
            #   3. audit_emitted=false branch → no bus event.
            #   4. subscription.unsubscribe() → succeeds (the
            #      one-shot fail flag has reset to false).
            #   5. modal closes; footer flips to "off".
            page.locator("#push-modal-unsubscribe").click()

            # Modal should close on success.
            page.locator("#push-modal").wait_for(
                state="hidden", timeout=5000
            )

            mock_state = page.evaluate("__karasuPushMockState()")
            # Browser unsubscribe was attempted TWICE total
            # across the two clicks; second call resolved.
            assert mock_state["unsubscribeCalls"] == 2
            # Mock now reports unsubscribed.
            assert mock_state["subscribed"] is False
        finally:
            browser.close()

    # Pin §11.6.13 binding: total bus count of push_unsubscribe
    # events is exactly 1 (from the first POST 204), regardless
    # of the rejected browser unsubscribe + the retry. The 204
    # IS the audit truth; the 404 retry path emits zero events
    # per the audit-event-correspondence invariant.
    assert len(_push_decisions(bus, "push_unsubscribe")) == 1
    # Store remains empty (no further mutation on the 404
    # retry path).
    raw = json.loads(push_store.read_text(encoding="utf-8"))
    assert raw["subscriptions"] == []
