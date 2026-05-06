"""Server-side Web Push emit (UI-12c).

Bus subscriber that classifies events into push categories
(:mod:`._classifier`), serialises them through a three-layer
rate limit (:mod:`._rate_limit`), VAPID-signs (:mod:`._signing`)
and aes128gcm-encrypts (:mod:`._encryption`) per delivery, and
fans out one outbound HTTP POST per active subscription
(:mod:`._dispatch`).

This package introduces the ``cryptography`` runtime dependency
as the named, scoped exception per UI-12 §11.6.13. The import
is CONFINED to :mod:`._signing`, :mod:`._keys`, and
:mod:`._encryption`. Every other module under ``karasu/`` is
forbidden from importing ``cryptography``; the binding is
pinned by ``tests/test_push_emit_import_scope.py``.

The :class:`PushEmit` class (added in the final commit of this
chunk) is a :class:`TriggerSource` that the
:class:`LoopController` registers when ``karasu watch`` starts.
Lifecycle:

  * ``start()``  — bootstrap VAPID if missing (writes the store
    once via :mod:`karasu.ui.push_store`), open a JsonlTailReader
    on the bus, spawn the subscriber thread.
  * ``stop()``   — signal the thread, flush in-flight debounced
    deliveries, drop in-memory rate-limit state.

UI-12c is the ONLY proactive outbound HTTP surface in Karasu.
The ``push_emit`` module reaches OUT to FCM / APNs / Mozilla
autopush; every other surface is request/response.
"""

from __future__ import annotations

# The public ``PushEmit`` / ``PushEmitConfig`` re-exports are
# attached after the leaf modules land. Keeping the import here
# would break ``from karasu.push_emit._classifier import ...``
# during incremental commits.

__all__: list[str] = []
