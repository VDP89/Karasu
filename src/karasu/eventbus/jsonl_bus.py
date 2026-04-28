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


class JsonlTailReader:
    """Stateful reader that returns events appended after construction.

    Each call to :meth:`read_new` returns the events appended since the
    previous call. Partial trailing lines (writer mid-flush) are left
    unconsumed and picked up on the next call.

    Defaults to starting at EOF — historical events are not replayed.
    Pass ``start_at_end=False`` to replay from the start of the file.
    """

    def __init__(self, path: str | Path, start_at_end: bool = True) -> None:
        self.path = Path(path)
        if start_at_end and self.path.exists():
            self._offset = self.path.stat().st_size
        else:
            self._offset = 0

    @property
    def offset(self) -> int:
        return self._offset

    def read_new(self) -> list[Event]:
        if not self.path.exists():
            return []
        with self.path.open("rb") as fh:
            fh.seek(self._offset)
            chunk = fh.read()
        if not chunk:
            return []
        last_nl = chunk.rfind(b"\n")
        if last_nl < 0:
            # No complete line yet; leave offset where it is.
            return []

        complete = chunk[: last_nl + 1]
        events: list[Event] = []
        for raw in complete.split(b"\n"):
            raw = raw.strip()
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="replace")
                events.append(Event.from_json(line))
            except (json.JSONDecodeError, TypeError):
                # Malformed line — skip silently, don't break the tail loop.
                continue

        # Advance only after the whole complete chunk has been parsed.
        # Returning a list keeps consumption atomic: a caller cannot
        # partially consume the result and lose already-advanced events.
        self._offset += len(complete)
        return events
