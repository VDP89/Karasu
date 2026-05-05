"""Unit tests for ScarEngine.revoke + revoked-state filtering.

UI-10 introduces the revoke pathway. The append-only invariant
holds: revoking a scar appends a revoke record; the original
Scar JSON line stays untouched. ``all()`` and ``find()`` filter
revoked scars on the next read, so the pipeline stops applying
them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from karasu.scars import Scar, ScarEngine


def _scar(classification: str = "high", path_glob: str = "*.py") -> Scar:
    return Scar(
        trigger={"classification": classification, "path": path_glob},
        correction={"priority": "high"},
    )


def test_revoke_unknown_id_returns_false(tmp_path: Path) -> None:
    engine = ScarEngine(tmp_path / "scars")
    assert engine.revoke("does-not-exist") is False


def test_revoke_existing_scar_returns_true(tmp_path: Path) -> None:
    engine = ScarEngine(tmp_path / "scars")
    scar = engine.record(_scar())
    assert engine.revoke(scar.id) is True


def test_revoke_is_idempotent_second_call_returns_false(tmp_path: Path) -> None:
    engine = ScarEngine(tmp_path / "scars")
    scar = engine.record(_scar())
    assert engine.revoke(scar.id) is True
    assert engine.revoke(scar.id) is False


def test_revoked_scar_is_filtered_from_all(tmp_path: Path) -> None:
    engine = ScarEngine(tmp_path / "scars")
    s1 = engine.record(_scar(classification="high", path_glob="*.py"))
    s2 = engine.record(_scar(classification="low", path_glob="*.md"))
    engine.revoke(s1.id)
    remaining = list(engine.all())
    assert len(remaining) == 1
    assert remaining[0].id == s2.id


def test_revoked_scar_is_filtered_from_find(tmp_path: Path) -> None:
    engine = ScarEngine(tmp_path / "scars")
    scar = engine.record(_scar(classification="high", path_glob="*.py"))
    assert engine.find("high", "src/foo.py") is not None
    engine.revoke(scar.id)
    assert engine.find("high", "src/foo.py") is None


def test_revoked_scar_apply_returns_none(tmp_path: Path) -> None:
    engine = ScarEngine(tmp_path / "scars")
    scar = engine.record(_scar(classification="high", path_glob="*.py"))
    assert engine.apply("high", "src/foo.py") == {"priority": "high"}
    engine.revoke(scar.id)
    assert engine.apply("high", "src/foo.py") is None


def test_revoke_appends_record_does_not_mutate_original(tmp_path: Path) -> None:
    """Append-only invariant: original Scar line stays present
    on disk; the revoke is a new line."""
    engine = ScarEngine(tmp_path / "scars")
    scar = engine.record(_scar())
    engine.revoke(scar.id, reason="not applicable anymore")
    lines = (tmp_path / "scars" / "scars.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert "type" not in first  # original Scar — no top-level type
    assert first["id"] == scar.id
    assert second["type"] == "revoke"
    assert second["scar_id"] == scar.id
    assert second["reason"] == "not applicable anymore"
    assert "revoked_at" in second


def test_revoke_without_reason_omits_field(tmp_path: Path) -> None:
    """Brief §10.2: empty reason MUST NOT serialise as null
    or empty string — the field is omitted entirely."""
    engine = ScarEngine(tmp_path / "scars")
    scar = engine.record(_scar())
    engine.revoke(scar.id)  # no reason
    lines = (tmp_path / "scars" / "scars.jsonl").read_text(encoding="utf-8").splitlines()
    revoke_record = json.loads(lines[1])
    assert revoke_record["type"] == "revoke"
    assert "reason" not in revoke_record


def test_revoke_with_empty_string_reason_omits_field(tmp_path: Path) -> None:
    """Defensive: a caller that passes ``""`` (instead of None)
    after trimming gets the same omission semantics."""
    engine = ScarEngine(tmp_path / "scars")
    scar = engine.record(_scar())
    engine.revoke(scar.id, reason="")
    lines = (tmp_path / "scars" / "scars.jsonl").read_text(encoding="utf-8").splitlines()
    revoke_record = json.loads(lines[1])
    assert "reason" not in revoke_record


def test_revoke_state_persists_across_engine_instances(tmp_path: Path) -> None:
    """A second ScarEngine instance over the same directory
    sees the revoke (state lives on disk, not in memory)."""
    rules_path = tmp_path / "scars"
    engine1 = ScarEngine(rules_path)
    scar = engine1.record(_scar())
    engine1.revoke(scar.id)

    engine2 = ScarEngine(rules_path)
    assert list(engine2.all()) == []
    assert engine2.find("high", "src/foo.py") is None


def test_revoke_record_with_unknown_scar_id_is_ignored_on_load(
    tmp_path: Path,
) -> None:
    """Defensive: a revoke record referencing a scar id that does
    not exist in the file is recorded as revoked but harmless —
    no crash on load, no false-positive matches."""
    rules_path = tmp_path / "scars"
    rules_path.mkdir(parents=True)
    (rules_path / "scars.jsonl").write_text(
        json.dumps({
            "type": "revoke",
            "scar_id": "phantom-id",
            "revoked_at": "2026-05-05T00:00:00.000+00:00",
        }) + "\n",
        encoding="utf-8",
    )
    engine = ScarEngine(rules_path)
    assert list(engine.all()) == []


def test_revoke_then_record_new_scar_does_not_resurrect(
    tmp_path: Path,
) -> None:
    """If the operator records a NEW scar after revoking an old
    one, the new scar is active; the old revocation does NOT
    apply to it (different id)."""
    engine = ScarEngine(tmp_path / "scars")
    s1 = engine.record(_scar(classification="high", path_glob="*.py"))
    engine.revoke(s1.id)
    s2 = engine.record(_scar(classification="low", path_glob="*.md"))
    actives = list(engine.all())
    assert len(actives) == 1
    assert actives[0].id == s2.id


def test_corrupt_line_is_skipped_not_crashed(tmp_path: Path) -> None:
    """A partial / corrupt JSONL line (e.g. a writer crashing
    mid-flush) must not abort the read — same behaviour as the
    bus log tail."""
    rules_path = tmp_path / "scars"
    rules_path.mkdir(parents=True)
    good = _scar()
    (rules_path / "scars.jsonl").write_text(
        good.to_json() + "\n" + "{not valid json\n",
        encoding="utf-8",
    )
    engine = ScarEngine(rules_path)
    survivors = list(engine.all())
    assert len(survivors) == 1
    assert survivors[0].id == good.id


def test_revoke_record_with_non_string_scar_id_is_ignored(
    tmp_path: Path,
) -> None:
    """Defensive: a malformed revoke record (scar_id is a number,
    null, etc.) is tolerated on load — neither crashes nor
    revokes anything."""
    rules_path = tmp_path / "scars"
    rules_path.mkdir(parents=True)
    scar = _scar()
    bad_revoke = json.dumps({
        "type": "revoke",
        "scar_id": 12345,
        "revoked_at": "2026-05-05T00:00:00.000+00:00",
    })
    (rules_path / "scars.jsonl").write_text(
        scar.to_json() + "\n" + bad_revoke + "\n",
        encoding="utf-8",
    )
    engine = ScarEngine(rules_path)
    survivors = list(engine.all())
    assert len(survivors) == 1
    assert survivors[0].id == scar.id
