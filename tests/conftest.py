"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from karasu.eventbus import JsonlEventBus


@pytest.fixture
def bus(tmp_path: Path) -> JsonlEventBus:
    return JsonlEventBus(tmp_path / "events.jsonl")
