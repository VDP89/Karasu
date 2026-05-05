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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class Scar:
    trigger: dict[str, Any]
    correction: dict[str, Any]
    source_event: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created: str = field(default_factory=_now_iso)

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
    """Read, write and query scars.

    Storage is an append-only JSONL file. Two record shapes share
    the file:

    * **Scar records** — the dataclass above, written by
      :meth:`record`. Identified by the absence of a ``"type"``
      field at the top level.
    * **Revoke records** — written by :meth:`revoke`. Identified
      by ``"type": "revoke"`` at the top level. Schema:

      .. code-block:: json

          {
            "type": "revoke",
            "scar_id": "<existing-scar-id>",
            "revoked_at": "<iso8601-ms>",
            "reason": "<optional free text>"
          }

    UI-10 introduced the revoke pathway. The append-only
    invariant is preserved: a revoke is a NEW record, never a
    mutation of the original Scar entry. :meth:`all` and
    :meth:`find` filter revoked scars out so the pipeline stops
    consulting them on next dispatch.
    """

    def __init__(self, rules_path: str | Path) -> None:
        self.rules_path = Path(rules_path)
        self.rules_path.mkdir(parents=True, exist_ok=True)
        self._file = self.rules_path / "scars.jsonl"

    def record(self, scar: Scar) -> Scar:
        with self._file.open("a", encoding="utf-8") as fh:
            fh.write(scar.to_json() + "\n")
        return scar

    def revoke(self, scar_id: str, reason: str | None = None) -> bool:
        """Append a revoke record for ``scar_id``.

        Returns ``True`` if the scar exists and was not already
        revoked; ``False`` otherwise. Idempotent at the caller's
        boundary: a second revoke for the same id is a no-op
        (returns ``False``) and writes nothing.

        ``reason`` is trimmed by the caller; an empty / None
        ``reason`` is omitted from the persisted record entirely
        rather than serialised as ``null`` or ``""`` (matches the
        UI-10 brief §10.2).
        """
        scars, revoked = self._load_state()
        if scar_id in revoked:
            return False
        if not any(s.id == scar_id for s in scars):
            return False
        record: dict[str, Any] = {
            "type": "revoke",
            "scar_id": scar_id,
            "revoked_at": _now_iso(),
        }
        if reason:
            record["reason"] = reason
        with self._file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True

    def all(self) -> Iterator[Scar]:
        scars, revoked = self._load_state()
        for scar in scars:
            if scar.id not in revoked:
                yield scar

    def find(self, classification: str, path: str) -> Scar | None:
        for scar in self.all():
            if scar.matches(classification, path):
                return scar
        return None

    def apply(self, classification: str, path: str) -> dict[str, Any] | None:
        scar = self.find(classification, path)
        return scar.correction if scar is not None else None

    def _load_state(self) -> tuple[list[Scar], set[str]]:
        """Read the JSONL once and split it into (scars, revoked_ids).

        Used by :meth:`all`, :meth:`find`, and :meth:`revoke` so
        the file is parsed exactly once per call instead of
        re-tailed for the revoke check. Single source of truth
        for the two-record-shape decoding.
        """
        if not self._file.exists():
            return [], set()
        scars: list[Scar] = []
        revoked: set[str] = set()
        with self._file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") == "revoke":
                    scar_id = payload.get("scar_id")
                    if isinstance(scar_id, str):
                        revoked.add(scar_id)
                    continue
                try:
                    scars.append(Scar(**payload))
                except TypeError:
                    continue
        return scars, revoked
