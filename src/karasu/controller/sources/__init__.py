"""Trigger sources — producers that fan events into the LoopController.

Phase 3 chunk 3c. The controller is the single dispatch coordinator;
trigger sources are the producers that hand it events. The
:class:`FilesystemWatcher` was the only source through Phase 3 chunks
3a + 3b; this package opens the seam for additional ones (git hooks,
GitHub webhooks, A2A peers — issue #5 archive).

A trigger source is anything that:
- starts a long-running observation (``start``)
- writes events to the bus and submits them to the controller
- stops cleanly on demand (``stop``)

One-shot producers (e.g. the ``karasu hook`` CLI) do NOT need to
implement this protocol — they call ``controller.submit`` directly
and exit.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TriggerSource(Protocol):
    """Long-running producer that fans events into a LoopController.

    Sources own their own lifecycle (typically a daemon thread or
    an inotify-style observer) and write events to the JSONL bus
    themselves. They submit each event to the controller via the
    callable they were given at construction time.

    The controller calls :meth:`start` after its own worker (and
    bus subscription, if configured) is up; it calls :meth:`stop`
    before shutting the worker down. Sources should be safe to
    construct and discard without ``start`` being called.
    """

    def start(self) -> None:  # pragma: no cover - protocol
        ...

    def stop(self) -> None:  # pragma: no cover - protocol
        ...


__all__ = ["TriggerSource"]
