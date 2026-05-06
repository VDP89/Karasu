"""PushEmit lifecycle + multi-device fan-out tests.

The bus is a real :class:`JsonlEventBus` writing to a tmp
file; the dispatcher is mocked so the tests don't actually
POST anything. Multi-device fan-out is verified by writing
two subscriptions to the store and counting that
``rate_limit.on_event`` is called once per (subscription,
category) tuple.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from karasu.eventbus import Event, JsonlEventBus
from karasu.push_emit import (
    DEFAULT_CONTACT_EMAIL,
    PushEmit,
    PushEmitConfig,
)
from karasu.push_emit._dispatch import HttpResponse, PushDispatcher
from karasu.ui.push_store import (
    append_subscription,
    compute_endpoint_hash,
    seed_vapid,
)


@pytest.fixture
def setup_paths(tmp_path: Path) -> tuple[Path, Path]:
    bus_path = tmp_path / "events.jsonl"
    store_path = tmp_path / "karasu-push.json"
    return bus_path, store_path


def _make_subscription(endpoint: str) -> dict[str, Any]:
    """Generate a minimal subscription dict with a fresh
    UA keypair (so the encryption module is happy if it
    runs)."""
    from base64 import urlsafe_b64encode
    import os

    from cryptography.hazmat.primitives.asymmetric import ec

    pk = ec.generate_private_key(ec.SECP256R1())
    nums = pk.public_key().public_numbers()
    raw = (
        b"\x04"
        + nums.x.to_bytes(32, "big")
        + nums.y.to_bytes(32, "big")
    )
    p256dh = urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    auth = (
        urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode("ascii")
    )
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}


# ---------------------------------------------------------------------------
# Default contact email (brief §10.4)
# ---------------------------------------------------------------------------


def test_default_contact_email() -> None:
    assert DEFAULT_CONTACT_EMAIL == "operator@localhost.invalid"


def test_config_defaults() -> None:
    config = PushEmitConfig(
        store_path=Path("x.json"), bus_path=Path("y.jsonl")
    )
    assert config.contact_email == DEFAULT_CONTACT_EMAIL
    assert config.debounce_seconds == 5.0
    assert config.dedup_ring_size == 64
    assert config.ttl_seconds == 60


# ---------------------------------------------------------------------------
# start() bootstraps VAPID
# ---------------------------------------------------------------------------


def test_start_bootstraps_vapid_on_empty_store(
    setup_paths: tuple[Path, Path],
) -> None:
    bus_path, store_path = setup_paths
    JsonlEventBus(bus_path)  # ensure parent dir exists

    config = PushEmitConfig(
        store_path=store_path,
        bus_path=bus_path,
        poll_interval=0.05,
    )
    emitter = PushEmit(config)
    try:
        emitter.start()
        # Store now has VAPID section.
        from karasu.ui.push_store import _read_or_empty_store

        raw = _read_or_empty_store(store_path)
        assert "vapid" in raw
        assert raw["vapid"]["public"]
        assert raw["vapid"]["private"]
    finally:
        emitter.stop()


def test_start_idempotent_on_pre_seeded_store(
    setup_paths: tuple[Path, Path],
) -> None:
    """If the store already has VAPID keys, start() reuses
    them — does NOT regenerate."""
    bus_path, store_path = setup_paths
    JsonlEventBus(bus_path)

    # Seed manually first.
    seed_vapid(
        store_path,
        public="A" * 87,
        private="B" * 43,
    )

    config = PushEmitConfig(
        store_path=store_path,
        bus_path=bus_path,
        poll_interval=0.05,
    )
    emitter = PushEmit(config)
    try:
        emitter.start()
        from karasu.ui.push_store import _read_or_empty_store

        raw = _read_or_empty_store(store_path)
        assert raw["vapid"] == {"public": "A" * 87, "private": "B" * 43}
    finally:
        emitter.stop()


# ---------------------------------------------------------------------------
# Restart guard
# ---------------------------------------------------------------------------


def test_double_start_raises(setup_paths: tuple[Path, Path]) -> None:
    bus_path, store_path = setup_paths
    JsonlEventBus(bus_path)

    config = PushEmitConfig(
        store_path=store_path,
        bus_path=bus_path,
        poll_interval=0.05,
    )
    emitter = PushEmit(config)
    try:
        emitter.start()
        with pytest.raises(RuntimeError, match="still alive"):
            emitter.start()
    finally:
        emitter.stop()


# ---------------------------------------------------------------------------
# Bus events flow through to the dispatcher
# ---------------------------------------------------------------------------


def test_attention_event_dispatches_to_subscribed_browser(
    setup_paths: tuple[Path, Path],
) -> None:
    bus_path, store_path = setup_paths
    bus = JsonlEventBus(bus_path)

    endpoint = "https://fcm.googleapis.com/fcm/send/AAA"
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint),
        categories=["attention"],
    )

    config = PushEmitConfig(
        store_path=store_path,
        bus_path=bus_path,
        debounce_seconds=0.05,
        poll_interval=0.02,
    )
    emitter = PushEmit(config)

    posts: list[tuple[str, dict[str, str]]] = []

    def stub_post(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> HttpResponse:
        posts.append((url, dict(headers)))
        return HttpResponse(status=201)

    try:
        emitter.start()
        # The bootstrap created VAPID; we now patch the
        # dispatcher's HTTP client (post-start since
        # _dispatcher exists only after start).
        assert emitter._dispatcher is not None
        emitter._dispatcher._http_post = stub_post

        # Append an attention-class event.
        bus.append(
            Event(
                type="agent_response",
                source="adapter",
                response={"requires_human": True},
            )
        )

        # Wait for the subscriber thread to pick it up + the
        # debounce timer to fire.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not posts:
            time.sleep(0.05)
    finally:
        emitter.stop()

    assert len(posts) == 1
    assert posts[0][0] == endpoint
    assert posts[0][1]["Topic"] == "attention"


# ---------------------------------------------------------------------------
# Multi-device fan-out (pin §11.6.14)
# ---------------------------------------------------------------------------


def test_multi_device_fan_out(setup_paths: tuple[Path, Path]) -> None:
    bus_path, store_path = setup_paths
    bus = JsonlEventBus(bus_path)

    endpoint_a = "https://fcm.googleapis.com/fcm/send/AAA"
    endpoint_b = "https://updates.push.services.mozilla.com/wpush/v1/BBB"
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint_a),
        categories=["attention", "errors"],
    )
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint_b),
        categories=["attention"],
    )

    config = PushEmitConfig(
        store_path=store_path,
        bus_path=bus_path,
        debounce_seconds=0.05,
        poll_interval=0.02,
    )
    emitter = PushEmit(config)

    posts: list[str] = []

    def stub_post(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> HttpResponse:
        posts.append(url)
        return HttpResponse(status=201)

    try:
        emitter.start()
        assert emitter._dispatcher is not None
        emitter._dispatcher._http_post = stub_post

        # ONE attention event → TWO POSTS (one per browser).
        bus.append(
            Event(
                type="agent_response",
                source="adapter",
                response={"requires_human": True},
            )
        )

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and len(posts) < 2:
            time.sleep(0.05)
    finally:
        emitter.stop()

    assert sorted(posts) == sorted([endpoint_a, endpoint_b])


def test_subscriber_with_only_errors_category_skips_attention(
    setup_paths: tuple[Path, Path],
) -> None:
    """A subscriber opted into ONLY "errors" must NOT receive
    an attention-class push."""
    bus_path, store_path = setup_paths
    bus = JsonlEventBus(bus_path)

    endpoint = "https://fcm.googleapis.com/fcm/send/ERR"
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint),
        categories=["errors"],  # NOT attention
    )

    config = PushEmitConfig(
        store_path=store_path,
        bus_path=bus_path,
        debounce_seconds=0.05,
        poll_interval=0.02,
    )
    emitter = PushEmit(config)

    posts: list[str] = []

    def stub_post(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> HttpResponse:
        posts.append(url)
        return HttpResponse(status=201)

    try:
        emitter.start()
        assert emitter._dispatcher is not None
        emitter._dispatcher._http_post = stub_post

        # An attention event — should NOT push to this
        # subscriber.
        bus.append(
            Event(
                type="agent_response",
                source="adapter",
                response={"requires_human": True},
            )
        )

        # Wait long enough for any push to arrive.
        time.sleep(0.5)
    finally:
        emitter.stop()

    assert posts == []


# ---------------------------------------------------------------------------
# UI-write events do not push (pin §11.6.9 + Layer 1 of rate_limit)
# ---------------------------------------------------------------------------


def test_ui_write_event_does_not_push(
    setup_paths: tuple[Path, Path],
) -> None:
    bus_path, store_path = setup_paths
    bus = JsonlEventBus(bus_path)

    endpoint = "https://fcm.googleapis.com/fcm/send/UI"
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint),
        categories=["corrections"],
    )

    config = PushEmitConfig(
        store_path=store_path,
        bus_path=bus_path,
        debounce_seconds=0.05,
        poll_interval=0.02,
    )
    emitter = PushEmit(config)

    posts: list[str] = []

    def stub_post(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> HttpResponse:
        posts.append(url)
        return HttpResponse(status=201)

    try:
        emitter.start()
        assert emitter._dispatcher is not None
        emitter._dispatcher._http_post = stub_post

        # source="ui" event — classifier returns None
        # (pin §11.6.9), so nothing reaches the dispatcher.
        bus.append(
            Event(
                type="human_decision",
                source="ui",
                data={"action": "scar_revoke"},
            )
        )

        # Wait long enough for any push to arrive.
        time.sleep(0.5)
    finally:
        emitter.stop()

    assert posts == []


# ---------------------------------------------------------------------------
# stop() lifecycle
# ---------------------------------------------------------------------------


def test_stop_idempotent_on_unstarted_emitter(
    setup_paths: tuple[Path, Path],
) -> None:
    """stop() on an emitter that was never started must NOT
    raise — defensive against fault paths in cmd_watch."""
    bus_path, store_path = setup_paths
    config = PushEmitConfig(store_path=store_path, bus_path=bus_path)
    emitter = PushEmit(config)
    emitter.stop()  # should be no-op


def test_start_after_clean_stop_succeeds(
    setup_paths: tuple[Path, Path],
) -> None:
    """The lifecycle pattern is start/stop/start — a clean
    stop must allow a subsequent start. The restart guard
    blocks ONLY when the previous thread is still alive."""
    bus_path, store_path = setup_paths
    JsonlEventBus(bus_path)

    config = PushEmitConfig(
        store_path=store_path,
        bus_path=bus_path,
        poll_interval=0.05,
    )
    emitter = PushEmit(config)
    emitter.start()
    emitter.stop()
    emitter.start()  # should not raise
    emitter.stop()
