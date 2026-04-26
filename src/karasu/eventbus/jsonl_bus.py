"""Append-only JSONL event bus.

Every Karasu component reads from and writes to a single JSONL file.
There is no other shared state.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Event:
    """A single record on the bus.

    See ``docs/event-schema.md`` for field semantics.
    """

    type: str
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    dispatch: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=_new_id)
    timestamp: str = field(default_factory=_now)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "Event":
        payload = json.loads(line)
        return cls(**payload)


class JsonlEventBus:
    """Crash-safe append-only event log."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: Event) -> Event:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(event.to_json() + "\n")
        return event

    def read(self) -> Iterator[Event]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield Event.from_json(line)
