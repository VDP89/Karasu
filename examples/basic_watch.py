"""Minimal watcher example.

Run from a checkout of any project to start emitting ``file_change``
events to ``./.karasu/events.jsonl``::

    python examples/basic_watch.py /path/to/project
"""

from __future__ import annotations

import sys
from pathlib import Path

from karasu.eventbus import JsonlEventBus
from karasu.watcher import FilesystemWatcher


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    bus = JsonlEventBus(root / ".karasu" / "events.jsonl")
    watcher = FilesystemWatcher(
        root=root,
        bus=bus,
        ignore=(".git", "__pycache__", "*.pyc", ".karasu/"),
    )
    print(f"watching {root} -> {bus.path}")
    watcher.run_forever()


if __name__ == "__main__":
    main()
