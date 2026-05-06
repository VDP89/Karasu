"""Category classifier — pure mapping from bus events to push categories.

Brief §3-B + pin §11.6.10 + pin §11.6.9.

The classifier is pure: input ``Event`` → ``str | None``. It
never reads the store, never opens a socket, never holds state.
Each call is independent.

The closed enum (pin §11.6.10):

  * ``attention``   — the operator should look. Either an
    agent_response asked a human (``response.requires_human``
    True), or the controller's chain cap has been hit on a
    file_change so a /scar loop is being throttled.
  * ``errors``      — an adapter failed (``dispatch.status``
    "failed").
  * ``corrections`` — a scar / correction was recorded
    out-of-band (a ``human_decision`` with ``source != "ui"``;
    Telegram, GitHub webhook, future inbound surfaces).

Pin §11.6.9 binding: a ``human_decision`` with ``source == "ui"``
(scar_revoke, trust_adjust, push_subscribe, push_unsubscribe)
NEVER classifies into ``corrections``. The filter is applied
INSIDE :func:`classify` so UI-write events surface as ``None``
and the dispatcher never even reaches the rate-limit gate for
them.

Layer-1 of :mod:`._rate_limit` ALSO suppresses ``source == "ui"``
events globally. The two filters together mean a hypothetical
future event type that emerges with ``source == "ui"`` cannot
slip through one filter and hit the other (defence in depth).

Events outside the three categories return ``None``. The caller
(:mod:`._emitter`) skips them entirely — no rate-limit slot is
consumed, no log line beyond DEBUG fires.
"""

from __future__ import annotations

from typing import Final

from karasu.eventbus import Event


# UI-12 brief §3-G + pin §11.6.10 — the closed enum. Mirrored in
# :data:`karasu.ui.push_store.PUSH_CATEGORIES` (the read surface
# from UI-12a) so a stale client cannot pass a category the
# server doesn't know.
ATTENTION: Final = "attention"
ERRORS: Final = "errors"
CORRECTIONS: Final = "corrections"

#: All push categories in canonical (sorted) order. Matches the
#: tuple in :mod:`karasu.ui.push_store`.
PUSH_CATEGORIES: Final = (ATTENTION, ERRORS, CORRECTIONS)


# Issue #47 + brief §3-B carry-forward — when a file_change has
# its ``controller_chain_depth`` at the controller's cap, the
# resubmit was just throttled and the operator should look. The
# constant is mirrored from :data:`LoopController.CHAIN_CAP` to
# avoid a circular import; the binding test in
# ``tests/test_push_emit_classifier.py`` asserts the two stay
# in sync (caught by the import statement, not a hardcoded
# duplicate).
def _chain_cap() -> int:
    # Lazy lookup so a future change to ``CHAIN_CAP`` does not
    # require re-deploying the push_emit module wholesale.
    from karasu.controller.loop import LoopController

    return LoopController.CHAIN_CAP


# UI-write source sentinel (pin §11.6.9 binding). The UI server's
# POST handlers stamp ``source="ui"`` on every human_decision they
# emit; the classifier filters that exact string.
_UI_SOURCE = "ui"


def classify(event: Event) -> str | None:
    """Map ``event`` to a push category, or ``None``.

    Pin §11.6.9 binding: ``source == "ui"`` events NEVER
    classify into ``corrections`` (the only category they could
    plausibly land in). They are filtered to ``None`` here so
    the dispatcher does not even reach the rate-limit Layer 1
    UI-write check for them.

    The function is intentionally exhaustive on the three
    canonical event types (``agent_response``, ``file_change``,
    ``human_decision``). Future event types default to ``None``;
    new categories earn their own brief.
    """
    if event.type == "agent_response":
        return _classify_agent_response(event)
    if event.type == "file_change":
        return _classify_file_change(event)
    if event.type == "human_decision":
        return _classify_human_decision(event)
    return None


def _classify_agent_response(event: Event) -> str | None:
    # ``errors`` precedes ``attention``: a failed dispatch is
    # the most urgent surface even if the response payload also
    # carries ``requires_human=True`` (e.g. an adapter that
    # paused mid-call). The two are usually mutually exclusive
    # but the order pins the resolution if both are present.
    status = event.dispatch.get("status")
    if status == "failed":
        return ERRORS
    requires_human = event.response.get("requires_human")
    if requires_human is True:
        return ATTENTION
    return None


def _classify_file_change(event: Event) -> str | None:
    depth = event.data.get("controller_chain_depth")
    if isinstance(depth, int) and depth >= _chain_cap():
        return ATTENTION
    return None


def _classify_human_decision(event: Event) -> str | None:
    # Pin §11.6.9: source="ui" never reaches corrections.
    if event.source == _UI_SOURCE:
        return None
    return CORRECTIONS
