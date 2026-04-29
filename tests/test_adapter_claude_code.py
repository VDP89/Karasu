"""Tests for the Claude Code CLI adapter.

The adapter wraps the local ``claude`` executable via ``subprocess.run``.
We test the argv we hand to ``subprocess`` rather than the response
shape: the adapter is a thin contract layer, and ``-p`` (non-interactive
print mode) is the difference between a working call and a 120 s hang
on the adapter timeout.
"""

from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace

import pytest

from karasu.adapters import claude_code as claude_code_module
from karasu.adapters.claude_code import ClaudeCodeAdapter
from karasu.adapters.base import AgentRequest


def _request() -> AgentRequest:
    return AgentRequest(
        classification="code_change",
        path="src/foo.py",
        priority="normal",
    )


def test_build_argv_contains_print_flag_before_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force the lookup to return None so the test does not depend on a
    # local ``claude`` install; the unresolved branch keeps the
    # original token.
    monkeypatch.setattr(claude_code_module.shutil, "which", lambda _name: None)
    adapter = ClaudeCodeAdapter()
    argv = adapter._build_argv(_request())

    assert argv[0] == "claude"
    assert "-p" in argv
    # The prompt must come after ``-p``; otherwise the CLI parses it as
    # a positional argument before knowing it is in non-interactive
    # mode.
    assert argv.index("-p") < len(argv) - 1
    assert argv[-1].startswith("Karasu dispatch:")


def test_build_argv_preserves_user_supplied_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ``command`` may include a path or extra flags. The print flag
    # must still be appended after whatever the user supplied so the
    # caller cannot accidentally drop it.
    monkeypatch.setattr(claude_code_module.shutil, "which", lambda _name: None)
    adapter = ClaudeCodeAdapter(command="/usr/local/bin/claude --debug")
    argv = adapter._build_argv(_request())

    assert argv[:3] == ["/usr/local/bin/claude", "--debug", "-p"]


def test_build_argv_resolves_executable_via_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # On Windows the npm-installed ``claude`` is a ``.cmd`` shim, which
    # subprocess.run cannot find without an absolute path. The adapter
    # resolves the first token via ``shutil.which`` so the same call
    # works on every platform.
    fake_path = os.path.join("C:" + os.sep, "fake", "claude.CMD")
    monkeypatch.setattr(
        claude_code_module.shutil, "which", lambda name: fake_path if name == "claude" else None
    )
    adapter = ClaudeCodeAdapter()
    argv = adapter._build_argv(_request())

    assert argv[0] == fake_path
    assert "-p" in argv


def test_dispatch_invokes_claude_with_print_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = ClaudeCodeAdapter()

    response = adapter.dispatch(_request())

    assert response.success is True
    assert response.content == "ok"
    assert "-p" in captured["argv"]
