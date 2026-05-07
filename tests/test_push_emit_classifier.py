"""Pure unit tests for the push_emit category classifier.

Brief §3-I + pin §11.6.10 + pin §11.6.9.
"""

from __future__ import annotations

import pytest

from karasu.eventbus import Event
from karasu.push_emit._classifier import (
    ATTENTION,
    CORRECTIONS,
    ERRORS,
    PUSH_CATEGORIES,
    _chain_cap,
    classify,
)


# ---------------------------------------------------------------------------
# attention
# ---------------------------------------------------------------------------


def test_attention_agent_response_requires_human() -> None:
    event = Event(
        type="agent_response",
        source="adapter",
        response={"requires_human": True},
    )
    assert classify(event) == ATTENTION


def test_attention_file_change_at_chain_cap() -> None:
    cap = _chain_cap()
    event = Event(
        type="file_change",
        source="controller",
        data={"controller_chain_depth": cap},
    )
    assert classify(event) == ATTENTION


def test_attention_file_change_above_chain_cap() -> None:
    # Depth above the cap also classifies — the controller's cap
    # blocks at == cap so anything > cap is a forged event we
    # still surface as attention rather than dropping silently.
    cap = _chain_cap()
    event = Event(
        type="file_change",
        source="controller",
        data={"controller_chain_depth": cap + 5},
    )
    assert classify(event) == ATTENTION


def test_attention_file_change_below_chain_cap_is_none() -> None:
    cap = _chain_cap()
    event = Event(
        type="file_change",
        source="controller",
        data={"controller_chain_depth": cap - 1},
    )
    assert classify(event) is None


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------


def test_errors_agent_response_failed() -> None:
    event = Event(
        type="agent_response",
        source="adapter",
        dispatch={"status": "failed"},
    )
    assert classify(event) == ERRORS


def test_errors_takes_precedence_over_attention() -> None:
    # Adapter failed AND the response carries requires_human —
    # errors wins (most urgent surface).
    event = Event(
        type="agent_response",
        source="adapter",
        dispatch={"status": "failed"},
        response={"requires_human": True},
    )
    assert classify(event) == ERRORS


# ---------------------------------------------------------------------------
# corrections
# ---------------------------------------------------------------------------


def test_corrections_human_decision_telegram() -> None:
    event = Event(
        type="human_decision",
        source="telegram",
        data={"text": "/scar reason=foo"},
    )
    assert classify(event) == CORRECTIONS


def test_corrections_human_decision_github_webhook() -> None:
    event = Event(
        type="human_decision",
        source="github_webhook",
        data={"text": "review feedback"},
    )
    assert classify(event) == CORRECTIONS


# ---------------------------------------------------------------------------
# pin §11.6.9 — UI-write events never classify into corrections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action",
    ["scar_revoke", "trust_adjust", "push_subscribe", "push_unsubscribe"],
)
def test_ui_write_human_decision_never_classifies(action: str) -> None:
    event = Event(
        type="human_decision",
        source="ui",
        data={"action": action},
    )
    assert classify(event) is None


# ---------------------------------------------------------------------------
# None branches — events outside the closed enum
# ---------------------------------------------------------------------------


def test_none_agent_response_completed_no_human() -> None:
    event = Event(
        type="agent_response",
        source="adapter",
        dispatch={"status": "completed"},
        response={"requires_human": False},
    )
    assert classify(event) is None


def test_none_agent_response_completed_no_response_field() -> None:
    event = Event(
        type="agent_response",
        source="adapter",
        dispatch={"status": "completed"},
    )
    assert classify(event) is None


def test_none_file_change_no_chain_depth() -> None:
    event = Event(
        type="file_change",
        source="watcher",
        data={"path": "src/foo.py"},
    )
    assert classify(event) is None


def test_none_file_change_chain_depth_wrong_type() -> None:
    # Untrusted forged depth: not an int → ignored.
    event = Event(
        type="file_change",
        source="controller",
        data={"controller_chain_depth": "high"},
    )
    assert classify(event) is None


def test_none_git_event() -> None:
    event = Event(
        type="git_event",
        source="git_hook",
        data={"hook": "post-commit"},
    )
    assert classify(event) is None


def test_none_unknown_future_type() -> None:
    event = Event(
        type="some_future_type",
        source="future",
        data={},
    )
    assert classify(event) is None


# ---------------------------------------------------------------------------
# closed enum + chain-cap stay in sync with their authorities
# ---------------------------------------------------------------------------


def test_push_categories_match_store_constant() -> None:
    # The classifier's enum and the read-surface enum must agree.
    # Drift between them would let a stale modal pass a category
    # the server doesn't know how to push (or vice versa).
    from karasu.ui.push_store import PUSH_CATEGORIES as STORE_CATS

    assert PUSH_CATEGORIES == STORE_CATS


def test_chain_cap_matches_controller() -> None:
    from karasu.controller.loop import LoopController

    assert _chain_cap() == LoopController.CHAIN_CAP
