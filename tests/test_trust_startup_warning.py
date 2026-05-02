"""Tests for the trust_level >= 2 startup warning.

NICE-TO-HAVE #3 from the Phase 3 audit (PR #46), promoted to a
hard chunk-4c pre-req in the Phase 3+ pre-mortem audit (PR #48).

Two layers:

1. ``AgentAdapter.__init__`` emits a structured ``logging.WARNING``
   on the ``karasu.adapters.base`` logger.
2. ``cmd_watch`` / ``cmd_serve`` print a loud stderr banner once
   per startup so operators running interactively see it.

Both layers are tested here so the contract is observable end-to-end.
"""

from __future__ import annotations

import logging

import pytest

from karasu.adapters import AgentRequest, AgentResponse
from karasu.adapters.base import AUTONOMOUS_TRUST_LEVEL, AgentAdapter
from karasu.__main__ import _announce_autonomous_adapters


class _FakeAdapter(AgentAdapter):
    """Concrete adapter for trust-warning tests; dispatch never runs."""

    def dispatch(self, request: AgentRequest) -> AgentResponse:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Layer 1 — AgentAdapter emits a structured warning at construction
# ---------------------------------------------------------------------------


def test_adapter_at_trust_level_2_emits_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="karasu.adapters.base"):
        _FakeAdapter(name="claude_code", trust_level=2)
    assert any(
        "trust_level=2" in r.message and "claude_code" in r.message
        for r in caplog.records
    )


def test_adapter_at_trust_level_3_emits_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="karasu.adapters.base"):
        _FakeAdapter(name="silent_codex", trust_level=3)
    assert any(
        "trust_level=3" in r.message and "silent_codex" in r.message
        for r in caplog.records
    )


def test_adapter_at_trust_level_1_stays_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """trust_level <= 1 is the operator-in-the-loop tier; no warning
    needed because every action is gated on a human notification."""
    with caplog.at_level(logging.WARNING, logger="karasu.adapters.base"):
        _FakeAdapter(name="careful", trust_level=1)
    assert not any(
        "trust_level" in r.message for r in caplog.records
    )


def test_adapter_at_trust_level_0_stays_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="karasu.adapters.base"):
        _FakeAdapter(name="confirm-only", trust_level=0)
    assert not any(
        "trust_level" in r.message for r in caplog.records
    )


def test_adapter_warning_references_the_runbook_section(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Operators triaging this warning need a pointer to the
    documentation. The runbook section is the canonical source on
    what trust_level=2 means in production."""
    with caplog.at_level(logging.WARNING, logger="karasu.adapters.base"):
        _FakeAdapter(name="x", trust_level=2)
    msg = caplog.records[-1].message
    assert "local-dogfood.md" in msg
    assert "Trust gradient" in msg


def test_autonomous_trust_level_constant_is_2() -> None:
    """Pin the threshold so a future contributor moving the bar
    surfaces the change as a visible diff in this test."""
    assert AUTONOMOUS_TRUST_LEVEL == 2


# ---------------------------------------------------------------------------
# Layer 2 — cmd_watch / cmd_serve banner on stderr
# ---------------------------------------------------------------------------


def test_announce_silent_when_no_autonomous_adapters(capsys) -> None:
    adapter = _FakeAdapter(name="careful", trust_level=1)
    _announce_autonomous_adapters([adapter])
    captured = capsys.readouterr()
    assert captured.err == ""


def test_announce_loud_when_one_adapter_is_autonomous(capsys) -> None:
    adapters = [
        _FakeAdapter(name="careful", trust_level=1),
        _FakeAdapter(name="claude_code", trust_level=2),
    ]
    _announce_autonomous_adapters(adapters)
    captured = capsys.readouterr()
    assert "trust gradient" in captured.err
    assert "claude_code(trust=2)" in captured.err
    # The careful adapter is below the bar — should NOT appear in
    # the banner.
    assert "careful" not in captured.err


def test_announce_lists_every_autonomous_adapter(capsys) -> None:
    adapters = [
        _FakeAdapter(name="claude_code", trust_level=2),
        _FakeAdapter(name="silent_codex", trust_level=3),
    ]
    _announce_autonomous_adapters(adapters)
    captured = capsys.readouterr()
    assert "claude_code(trust=2)" in captured.err
    assert "silent_codex(trust=3)" in captured.err


def test_announce_points_at_runbook(capsys) -> None:
    adapters = [_FakeAdapter(name="claude_code", trust_level=2)]
    _announce_autonomous_adapters(adapters)
    captured = capsys.readouterr()
    assert "local-dogfood.md" in captured.err
    assert "Trust gradient" in captured.err


def test_announce_silent_with_empty_adapter_list(capsys) -> None:
    _announce_autonomous_adapters([])
    captured = capsys.readouterr()
    assert captured.err == ""


# ---------------------------------------------------------------------------
# Layer 2 — wiring contract: banner is wired into cmd_watch / cmd_serve
# but NOT into cmd_hook. The hook flow is one-shot (per commit); polluting
# its stderr would be noisy and out of scope. Pinned here so a future
# refactor that drops cmd_watch/cmd_serve, or adds the helper to other
# entry points, surfaces as a visible test failure.
# ---------------------------------------------------------------------------


def test_banner_is_wired_into_cmd_watch_and_cmd_serve_only() -> None:
    """The banner helper must be called by cmd_watch and cmd_serve.

    Pinning the wiring (not just the helper) surfaces the
    REQUERIDO finding from the chunk-4c gate audit: a future
    contributor adding ``_announce_autonomous_adapters`` to
    cmd_hook (or any other one-shot entry point) trips this test.
    """
    import inspect

    from karasu.__main__ import cmd_hook, cmd_serve, cmd_watch

    helper = "_announce_autonomous_adapters"
    assert helper in inspect.getsource(cmd_watch)
    assert helper in inspect.getsource(cmd_serve)
    # cmd_hook is a one-shot git-hook flow — explicit non-wiring.
    assert helper not in inspect.getsource(cmd_hook)
