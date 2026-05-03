"""Git-tree-aware path probe for :class:`PromptBuilder`.

Audit-deferred follow-up from Phase 3+ chunk 4c (PR #59). The
default probe in ``prompt_builder.py`` is ``Path.exists`` — i.e.
"is this path on disk in the working tree?". This module ships a
git-tree-aware variant that probes the COMMITTED tree at a given
ref instead.

Why two probes:

- The working-tree probe says ``True`` for a path that exists on
  disk regardless of whether the file is tracked, staged, or
  committed. Useful when the operator's workspace IS the source
  of truth.
- The git-tree probe says ``True`` only when the path resolves
  inside the named ref's tree object. Useful when the deployment
  is a bare repo (no working tree at all), or when the operator's
  workspace has diverged from HEAD and only the committed state
  should drive the prompt branch.

Both probes are injected into :class:`PromptBuilder` via the
``path_exists`` constructor kwarg. ``functools.partial`` covers
non-default ``ref`` / ``cwd``::

    from functools import partial

    from karasu.adapters import PromptBuilder
    from karasu.adapters.git_probe import git_tree_path_exists

    builder = PromptBuilder(
        path_exists=partial(
            git_tree_path_exists, ref="origin/main", cwd="/srv/repo"
        ),
    )

Failures (no git, not a repo, unknown ref, timeout) are
swallowed: the probe returns ``False`` so the prompt builder
falls back to the metadata-only branch — the safer default. A
raised exception here would break the dispatch path itself,
which is much worse than a missed "this file is editable"
optimization.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable

# Module-level so tests can patch a single name. Production
# callers should not need to override this.
GitRunner = Callable[[list[str], str | None, float], int]

# Default probe timeout — generous enough for cold-cache
# ``git cat-file`` on a large repo, short enough that an
# operator's dispatch never hangs on a wedged git process.
_DEFAULT_GIT_PROBE_TIMEOUT_S = 5.0

_log = logging.getLogger(__name__)


def _default_runner(
    argv: list[str], cwd: str | None, timeout: float
) -> int:
    """Run ``argv`` and return its exit code.

    Returns a sentinel non-zero rc on any subprocess error so
    callers can treat "command failed" and "command exited
    non-zero" identically — both mean "do not trust this probe".
    """
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        _log.debug(
            "git probe runner: %s failed (%s); treating as missing",
            argv,
            exc,
        )
        return 1
    return completed.returncode


def git_tree_path_exists(
    path: str,
    *,
    ref: str = "HEAD",
    cwd: str | Path | None = None,
    timeout: float = _DEFAULT_GIT_PROBE_TIMEOUT_S,
    runner: GitRunner = _default_runner,
) -> bool:
    """Return ``True`` iff ``path`` is in the git tree at ``ref``.

    Uses ``git cat-file -e <ref>:<path>`` which exits 0 when the
    path resolves to a blob or tree in the named ref. Returns
    ``False`` on:

    - Empty path (matches ``_default_path_exists`` semantics).
    - ``git`` not on PATH / not installed.
    - ``cwd`` is not a git repo.
    - ``ref`` is unknown.
    - The path is absent from the tree.
    - Subprocess timeout / OSError.

    Never raises. The prompt builder needs a boolean answer; an
    error in the probe should not break the dispatch path itself.
    Failures fall through to "metadata-only" treatment, which is
    the safer default for review-comment handoff.
    """
    if not path:
        return False
    cwd_str = str(cwd) if cwd is not None else None
    rc = runner(
        ["git", "cat-file", "-e", f"{ref}:{path}"],
        cwd_str,
        timeout,
    )
    return rc == 0
