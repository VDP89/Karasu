"""Git-hook trigger source.

A one-shot producer invoked from ``.git/hooks/<name>`` via
``karasu hook <name>``. The CLI builds ``file_change`` events from
the hook's git state, writes them to the bus, and submits them
through the controller's worker before exiting.

The controller for a hook invocation is short-lived: the CLI
constructs it, submits the events, drains the worker, and exits.
There is no long-running thread, so this module does NOT implement
:class:`TriggerSource` — the protocol is for long-running sources
like the watcher or future webhook receivers.

The path-extraction helpers are pure: they shell out to ``git`` but
do not touch the bus or controller. Tests can mock the subprocess
boundary with ``runner=`` to verify the event shape.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Callable, Iterable

from karasu.eventbus import Event, JsonlEventBus

# subprocess.run wrapper signature — argv list -> stdout text. Tests
# pass a fake; production passes ``_default_runner`` below.
GitRunner = Callable[[list[str]], str]

# Per-hook change_type so downstream consumers can distinguish a
# pre-commit "staged" change from a post-merge "merged" change.
HOOK_CHANGE_TYPE: dict[str, str] = {
    "pre-commit": "staged",
    "post-commit": "committed",
    "post-merge": "merged",
}

SUPPORTED_HOOKS = frozenset(HOOK_CHANGE_TYPE)

_log = logging.getLogger(__name__)


def _default_runner(argv: list[str]) -> str:
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        _log.warning(
            "git command %s failed (rc=%d): %s",
            argv,
            completed.returncode,
            completed.stderr.strip(),
        )
        return ""
    return completed.stdout


def paths_for_hook(hook: str, runner: GitRunner = _default_runner) -> list[str]:
    """Return the affected paths for a given hook.

    - ``pre-commit``  → staged files (``git diff --cached --name-only``)
    - ``post-commit`` → files in the most recent commit (``git show --name-only HEAD``)
    - ``post-merge``  → files changed by the merge (``git diff-tree -r --name-only ORIG_HEAD HEAD``)

    Unknown hooks return an empty list — the CLI fails with a
    clearer error before we get here.
    """
    if hook == "pre-commit":
        out = runner(["git", "diff", "--cached", "--name-only"])
    elif hook == "post-commit":
        out = runner(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"]
        )
    elif hook == "post-merge":
        out = runner(
            [
                "git",
                "diff-tree",
                "-r",
                "--name-only",
                "--no-commit-id",
                "ORIG_HEAD",
                "HEAD",
            ]
        )
    else:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def build_events(hook: str, paths: Iterable[str]) -> list[Event]:
    """Build one ``file_change`` per affected path for this hook."""
    change_type = HOOK_CHANGE_TYPE.get(hook)
    if change_type is None:
        return []
    return [
        Event(
            type="file_change",
            source="git_hook",
            data={
                "path": path,
                "change_type": change_type,
                "git_hook": hook,
            },
        )
        for path in paths
    ]


def submit_for_hook(
    hook: str,
    bus: JsonlEventBus,
    submit: Callable[[Event], None],
    runner: GitRunner = _default_runner,
) -> int:
    """Run the full hook sequence: extract paths, build events,
    write to bus, submit to controller. Returns the number of events
    fired so the CLI can report a count.
    """
    if hook not in SUPPORTED_HOOKS:
        raise ValueError(
            f"unsupported hook {hook!r}; expected one of "
            f"{sorted(SUPPORTED_HOOKS)}"
        )
    paths = paths_for_hook(hook, runner=runner)
    if not paths:
        return 0
    events = build_events(hook, paths)
    for event in events:
        appended = bus.append(event)
        submit(appended)
    return len(events)
