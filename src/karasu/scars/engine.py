"""Scar engine — Karasu's correction memory.

A scar is a structured rule derived from a human override. Once
recorded, the engine consults it before classification so that the
same correction does not need to be issued twice.

See ``docs/scar-engine.md``.
"""

from __future__ import annotations

import fnmatch
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


@dataclass
class Scar:
    trigger: dict[str, Any]
    correction: dict[str, Any]
    source_event: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    )

    def matches(self, classification: str, path: str) -> bool:
        trig_class = self.trigger.get("classification")
        if trig_class is not None and trig_class != classification:
            return False
        trig_path = self.trigger.get("path")
        if trig_path is not None and not fnmatch.fnmatch(path, trig_path):
            return False
        return True

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class ScarEngine:
    """Read, write and query scars."""

    def __init__(self, rules_path: str | Path) -> None:
        self.rules_path = Path(rules_path)
        self.rules_path.mkdir(parents=True, exist_ok=True)
        self._file = self.rules_path / "scars.jsonl"

    def record(self, scar: Scar) -> Scar:
        with self._file.open("a", encoding="utf-8") as fh:
            fh.write(scar.to_json() + "\n")
        return scar

    def all(self) -> Iterator[Scar]:
        if not self._file.exists():
            return
        with self._file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield Scar(**json.loads(line))

    def find(self, classification: str, path: str) -> Scar | None:
        for scar in self.all():
            if scar.matches(classification, path):
                return scar
        return None

    def apply(self, classification: str, path: str) -> dict[str, Any] | None:
        scar = self.find(classification, path)
        return scar.correction if scar is not None else None
