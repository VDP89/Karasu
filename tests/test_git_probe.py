"""Tests for the git-tree-aware path probe.

PR #59 follow-up. The default ``PromptBuilder`` probe consults
the working tree (``Path.exists``); this module ships a probe
that consults the committed tree at a given ref. Tests cover
both the unit behaviour (with a mocked runner) and an
end-to-end run against a real ``git init`` repo created in
``tmp_path``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from karasu.adapters import PromptBuilder, git_tree_path_exists
from karasu.adapters.base import AgentRequest
from karasu.adapters.git_probe import _default_runner


# ---------------------------------------------------------------------------
# Unit tests with a mocked runner
# ---------------------------------------------------------------------------


def test_git_tree_path_exists_returns_true_on_rc_zero() -> None:
    """``git cat-file -e`` exits 0 when the path is in the tree."""
    runner_calls: list[list[str]] = []

    def fake_runner(argv: list[str], cwd, timeout: float) -> int:
        runner_calls.append(argv)
        return 0

    assert git_tree_path_exists(
        "src/karasu/__main__.py", runner=fake_runner
    ) is True
    assert runner_calls == [
        ["git", "cat-file", "-e", "HEAD:src/karasu/__main__.py"]
    ]


def test_git_tree_path_exists_returns_false_on_rc_nonzero() -> None:
    """rc != 0 covers: path absent, ref unknown, not a repo."""

    def fake_runner(argv: list[str], cwd, timeout: float) -> int:
        return 1

    assert git_tree_path_exists("missing.py", runner=fake_runner) is False


def test_git_tree_path_exists_returns_false_on_empty_path() -> None:
    """Empty path matches ``_default_path_exists`` semantics: no
    workspace lookup at all. The runner must NOT be invoked —
    reaching git for an empty path would treat ``HEAD:`` as a
    directory query and could return rc=0 unexpectedly."""
    called = False

    def fake_runner(argv: list[str], cwd, timeout: float) -> int:
        nonlocal called
        called = True
        return 0

    assert git_tree_path_exists("", runner=fake_runner) is False
    assert called is False


def test_git_tree_path_exists_passes_ref_through() -> None:
    captured: dict[str, list[str]] = {}

    def fake_runner(argv: list[str], cwd, timeout: float) -> int:
        captured["argv"] = argv
        return 0

    git_tree_path_exists("foo.py", ref="origin/main", runner=fake_runner)
    assert captured["argv"][3] == "origin/main:foo.py"


def test_git_tree_path_exists_passes_cwd_through() -> None:
    captured: dict[str, str | None] = {}

    def fake_runner(argv: list[str], cwd, timeout: float) -> int:
        captured["cwd"] = cwd
        return 0

    git_tree_path_exists(
        "foo.py", cwd=Path("/srv/repo"), runner=fake_runner
    )
    assert captured["cwd"] == "/srv/repo"


def test_git_tree_path_exists_passes_string_cwd_through_unchanged() -> None:
    captured: dict[str, str | None] = {}

    def fake_runner(argv: list[str], cwd, timeout: float) -> int:
        captured["cwd"] = cwd
        return 0

    git_tree_path_exists("foo.py", cwd="/srv/repo", runner=fake_runner)
    assert captured["cwd"] == "/srv/repo"


def test_git_tree_path_exists_default_cwd_is_none() -> None:
    """Default cwd=None lets git default to its own resolution
    (current process cwd). Pinned so a future change to "guess via
    Path.cwd()" is a deliberate decision, not an accident."""
    captured: dict[str, str | None] = {}

    def fake_runner(argv: list[str], cwd, timeout: float) -> int:
        captured["cwd"] = cwd
        return 0

    git_tree_path_exists("foo.py", runner=fake_runner)
    assert captured["cwd"] is None


# ---------------------------------------------------------------------------
# Default runner — covers subprocess error fallthrough
# ---------------------------------------------------------------------------


def test_default_runner_returns_nonzero_on_filenotfound() -> None:
    """git not on PATH → FileNotFoundError. The runner must swallow
    it and return a sentinel non-zero rc so the probe falls back
    to "metadata-only" rather than raising into the dispatch
    path."""
    with patch(
        "karasu.adapters.git_probe.subprocess.run",
        side_effect=FileNotFoundError("git: not found"),
    ):
        rc = _default_runner(
            ["git", "cat-file", "-e", "HEAD:foo.py"], None, 5.0
        )
    assert rc != 0


def test_default_runner_returns_nonzero_on_timeout() -> None:
    with patch(
        "karasu.adapters.git_probe.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5.0),
    ):
        rc = _default_runner(
            ["git", "cat-file", "-e", "HEAD:foo.py"], None, 5.0
        )
    assert rc != 0


def test_default_runner_returns_nonzero_on_oserror() -> None:
    with patch(
        "karasu.adapters.git_probe.subprocess.run",
        side_effect=OSError("permission denied"),
    ):
        rc = _default_runner(
            ["git", "cat-file", "-e", "HEAD:foo.py"], None, 5.0
        )
    assert rc != 0


# ---------------------------------------------------------------------------
# End-to-end against a real git repo in tmp_path
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    return shutil.which("git") is not None


def _init_repo(repo: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "t@x"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=repo,
        check=True,
    )


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
def test_real_repo_committed_file_is_present(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "tracked.py").write_text("print('hi')\n")
    subprocess.run(["git", "add", "tracked.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=repo, check=True
    )

    assert git_tree_path_exists("tracked.py", cwd=repo) is True


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
def test_real_repo_untracked_file_is_absent(tmp_path: Path) -> None:
    """The probe consults the COMMITTED tree, not the working tree.
    A file that exists on disk but has never been committed must
    return False — that's the whole point of the git-tree probe."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "tracked.py").write_text("print('hi')\n")
    subprocess.run(["git", "add", "tracked.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=repo, check=True
    )
    # Untracked sibling — exists on disk, not in HEAD.
    (repo / "scratch.py").write_text("# uncommitted\n")

    assert git_tree_path_exists("scratch.py", cwd=repo) is False


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
def test_real_repo_missing_path_is_absent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "tracked.py").write_text("print('hi')\n")
    subprocess.run(["git", "add", "tracked.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=repo, check=True
    )

    assert git_tree_path_exists("never_existed.py", cwd=repo) is False


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
def test_real_repo_unknown_ref_is_absent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "tracked.py").write_text("print('hi')\n")
    subprocess.run(["git", "add", "tracked.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=repo, check=True
    )

    assert git_tree_path_exists(
        "tracked.py", ref="refs/heads/does-not-exist", cwd=repo
    ) is False


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
def test_not_a_repo_is_absent(tmp_path: Path) -> None:
    """Plain directory — no .git. The probe must return False
    rather than raising. ``cat-file`` on a non-repo exits non-zero."""
    assert git_tree_path_exists("anything.py", cwd=tmp_path) is False


# ---------------------------------------------------------------------------
# Integration with PromptBuilder
# ---------------------------------------------------------------------------


def test_prompt_builder_uses_injected_git_probe_for_metadata_only() -> None:
    """When the injected probe says "missing", PromptBuilder emits
    the metadata-only github prompt. Verifies the existing
    injection point (PR #59) still routes correctly when a
    git-tree probe is plugged in."""

    def always_missing(path: str) -> bool:
        return False

    builder = PromptBuilder(path_exists=always_missing)
    request = AgentRequest(
        classification="code_change",
        path="src/foo.py",
        priority="normal",
        metadata={
            "github_body": "looks wrong",
            "github_author": "alice",
            "github_pr": 42,
            "github_repo": "vdp89/karasu-",
        },
    )
    prompt = builder.build(request)

    assert "(metadata-only)" in prompt
    assert "Do NOT attempt edits" in prompt


def test_prompt_builder_uses_injected_git_probe_for_present_path() -> None:
    """When the injected probe says "present", PromptBuilder emits
    the full github handoff (no metadata-only suffix, no
    "Do NOT attempt edits" note)."""

    def always_present(path: str) -> bool:
        return True

    builder = PromptBuilder(path_exists=always_present)
    request = AgentRequest(
        classification="code_change",
        path="src/foo.py",
        priority="normal",
        metadata={
            "github_body": "nit: rename the var",
            "github_author": "alice",
            "github_pr": 42,
            "github_repo": "vdp89/karasu-",
        },
    )
    prompt = builder.build(request)

    assert "(metadata-only)" not in prompt
    assert "Do NOT attempt edits" not in prompt
