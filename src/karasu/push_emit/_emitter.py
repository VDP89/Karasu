"""PushEmit — bus subscriber + multi-device fan-out.

Brief §3-A. The :class:`TriggerSource` that
:class:`LoopController` registers when ``karasu watch`` starts
(brief §11.6.16: lifecycle bound to the controller).

Wires:

  ``classifier``   — pure category mapping (:mod:`._classifier`).
  ``rate_limit``   — three-layer rate limiter (:mod:`._rate_limit`).
  ``dispatcher``   — HTTP delivery + 410/404 prune + transport
                     privacy (:mod:`._dispatch`).

Lifecycle:

  ``start()``:
    1. Bootstrap VAPID via :func:`bootstrap_if_missing` —
       fresh keypair on first start, idempotent thereafter.
    2. Load the VAPID private key + public b64u from the
       store.
    3. Build :class:`PushDispatcher` (HTTP layer) +
       :class:`RateLimit` (in-memory throttling).
    4. Open a :class:`JsonlTailReader` at the bus path.
    5. Spawn the subscriber thread that polls + classifies +
       fans out per (subscription, category).

  ``stop()``:
    1. Signal the subscriber thread.
    2. Join with timeout.
    3. ``rate_limit.stop()`` — cancel pending debounce timers
       + drop in-memory dedupe ring.

Multi-device fan-out (pin §11.6.14): each call to
:meth:`_on_bus_event` walks every active subscription whose
configured categories include the classified category. One
:meth:`RateLimit.on_event` call per (subscription, category)
tuple. The dispatcher then handles the per-call HTTP POST.

Brief §3-A binding: lives inside ``karasu watch`` (NOT
``karasu ui``). The cross-process file lock from UI-12c §3-G
serialises the prune writes against UI-12b's POST handlers.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from karasu.eventbus import Event, JsonlTailReader
from karasu.push_emit._classifier import classify
from karasu.push_emit._dispatch import (
    DEFAULT_TTL_SECONDS,
    DispatcherConfig,
    PushDispatcher,
)
from karasu.push_emit._keys import bootstrap_if_missing
from karasu.push_emit._rate_limit import (
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_DEDUP_RING_SIZE,
    RateLimit,
)
from karasu.push_emit._signing import load_private_key
from karasu.ui.push_store import _read_or_empty_store

_log = logging.getLogger(__name__)


# Brief §10.4 default — operator should configure
# karasu.yaml `push.contact_email` for production. localhost
# dogfood survives with the placeholder.
DEFAULT_CONTACT_EMAIL = "operator@localhost.invalid"


@dataclass
class PushEmitConfig:
    """Persistent config for one ``karasu watch`` push surface.

    Fields:
      ``store_path``         path to ``karasu-push.json``.
      ``bus_path``           path to ``events.jsonl``.
      ``contact_email``      VAPID ``sub`` claim. Defaults to
                             :data:`DEFAULT_CONTACT_EMAIL`.
      ``debounce_seconds``   Layer-2 trailing debounce window.
      ``dedup_ring_size``    Layer-3 ring per endpoint.
      ``ttl_seconds``        Web Push TTL header.
      ``poll_interval``      Subscriber thread sleep between
                             tail reads.
    """

    store_path: Path
    bus_path: Path
    contact_email: str = DEFAULT_CONTACT_EMAIL
    debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS
    dedup_ring_size: int = DEFAULT_DEDUP_RING_SIZE
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    poll_interval: float = 0.5


class PushEmit:
    """Long-running subscriber that classifies bus events
    and pushes notifications to opted-in browsers.

    Implements the :class:`TriggerSource` protocol via
    :meth:`start` + :meth:`stop`; the
    :class:`LoopController` calls them as part of its own
    lifecycle.
    """

    def __init__(self, config: PushEmitConfig) -> None:
        self._config = config
        self._reader: JsonlTailReader | None = None
        self._thread: threading.Thread | None = None
        self._stopping: threading.Event | None = None
        self._rate_limit: RateLimit | None = None
        self._dispatcher: PushDispatcher | None = None

    # ------------------------------------------------------------------
    # TriggerSource protocol
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Bootstrap VAPID + spawn the subscriber thread."""
        # Restart guard — symmetric with LoopController.start()
        # (PR #36, chunk 3a). A previous start() that left a
        # live thread (because stop() timed out) cannot be
        # silently overwritten; the operator must resolve the
        # hung thread first.
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError(
                "push_emit: previous subscriber thread still alive; "
                "cannot restart until it exits"
            )

        # Brief §3-F binding — auto-bootstrap on first start.
        # Idempotent on subsequent starts.
        bootstrap_if_missing(self._config.store_path)

        store = _read_or_empty_store(self._config.store_path)
        vapid = store.get("vapid")
        if not isinstance(vapid, dict):
            raise RuntimeError(
                "push_emit: VAPID bootstrap should have populated "
                "the store; got malformed vapid section"
            )
        public_b64 = vapid.get("public")
        private_b64 = vapid.get("private")
        if not isinstance(public_b64, str) or not isinstance(private_b64, str):
            raise RuntimeError(
                "push_emit: VAPID keys missing or malformed after "
                "bootstrap"
            )

        # Build the inner pipeline from the inside out:
        # dispatcher → rate_limit → reader.
        dispatcher_config = DispatcherConfig(
            store_path=self._config.store_path,
            private_key=load_private_key(private_b64),
            public_key_b64u=public_b64,
            subject=f"mailto:{self._config.contact_email}",
            ttl_seconds=self._config.ttl_seconds,
        )
        self._dispatcher = PushDispatcher(dispatcher_config)
        self._rate_limit = RateLimit(
            dispatcher=self._dispatcher.dispatch,
            debounce_seconds=self._config.debounce_seconds,
            dedup_ring_size=self._config.dedup_ring_size,
        )

        # Tail the bus from the END so a watcher restart doesn't
        # replay every historical event as a push (pin §11.6.5
        # restart-cleared dedupe would catch most replays, but
        # starting at end is the cheaper invariant).
        self._reader = JsonlTailReader(
            self._config.bus_path, start_at_end=True
        )
        self._stopping = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="karasu-push-emit",
        )
        self._thread.start()
        _log.info(
            "push_emit: started; bus=%s store=%s",
            self._config.bus_path,
            self._config.store_path,
        )

    def stop(self) -> None:
        """Signal the subscriber thread + flush rate-limit
        state.

        Called by :meth:`LoopController.stop` BEFORE the worker
        thread is joined. In-flight HTTP deliveries continue
        until they complete (or hit their request timeout) —
        the dispatcher does not abort mid-flight.

        If the subscriber thread does not exit within 5 s, the
        thread + ``_stopping`` event + reader handles are left
        populated so a future :meth:`start` raises rather than
        silently leaking a second subscriber on top of the
        abandoned one (mirror of :meth:`LoopController.stop`
        in PR #36).
        """
        if self._stopping is not None:
            self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                _log.warning(
                    "push_emit: subscriber thread did not exit "
                    "within 5s; abandoning. start() will refuse "
                    "a restart until it exits."
                )
                # Leave _thread + _stopping + _reader populated
                # so start() refuses. rate_limit.stop() still
                # fires below — pending timers cancel either way.
                if self._rate_limit is not None:
                    self._rate_limit.stop()
                return
            self._thread = None
            self._stopping = None
            self._reader = None
        if self._rate_limit is not None:
            self._rate_limit.stop()
            self._rate_limit = None
        self._dispatcher = None
        _log.info("push_emit: stopped")

    # ------------------------------------------------------------------
    # Subscriber loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        assert self._reader is not None
        assert self._stopping is not None
        while not self._stopping.is_set():
            try:
                events = self._reader.read_new()
            except Exception:
                _log.exception("push_emit: bus reader failed")
                events = []
            for event in events:
                try:
                    self._on_bus_event(event)
                except Exception:
                    _log.exception(
                        "push_emit: on_bus_event failed for %s",
                        event.id,
                    )
            self._stopping.wait(timeout=self._config.poll_interval)

    def _on_bus_event(self, event: Event) -> None:
        """Classify + fan out to every matching subscription."""
        category = classify(event)
        if category is None:
            return
        assert self._rate_limit is not None

        # Multi-device fan-out: walk every subscription whose
        # categories include this category. Each call to
        # ``rate_limit.on_event`` is independent — debounce +
        # dedupe state is per (endpoint_hash, category).
        try:
            store = _read_or_empty_store(self._config.store_path)
        except Exception:
            _log.exception(
                "push_emit: store read failed during fan-out"
            )
            return
        subs = store.get("subscriptions")
        if not isinstance(subs, list):
            return
        for entry in subs:
            if not isinstance(entry, dict):
                continue
            categories = entry.get("categories")
            if not isinstance(categories, list):
                continue
            if category not in categories:
                continue
            endpoint_hash = entry.get("endpoint_hash")
            if not isinstance(endpoint_hash, str) or not endpoint_hash:
                continue
            self._rate_limit.on_event(event, endpoint_hash, category)
