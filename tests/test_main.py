import pytest

from karasu.__main__ import _adapters, _normalize_handles


def test_normalize_handles_accepts_list() -> None:
    assert _normalize_handles("agent", ["a", "b"]) == ("a", "b")


def test_normalize_handles_accepts_tuple() -> None:
    assert _normalize_handles("agent", ("a", "b")) == ("a", "b")


def test_normalize_handles_accepts_none() -> None:
    assert _normalize_handles("agent", None) == ()


def test_normalize_handles_rejects_string() -> None:
    with pytest.raises(ValueError, match="agents.claude_code.handles"):
        _normalize_handles("claude_code", "code_change")


def test_normalize_handles_rejects_int() -> None:
    with pytest.raises(ValueError):
        _normalize_handles("agent", 1)


def test_normalize_handles_rejects_non_string_elements() -> None:
    with pytest.raises(ValueError, match="non-string items"):
        _normalize_handles("agent", ["code_change", 1, None])


def test_adapters_rejects_scalar_handles() -> None:
    config = {
        "agents": {
            "claude_code": {"command": "claude", "handles": "code_change", "trust_level": 1}
        }
    }
    with pytest.raises(ValueError, match="claude_code.handles"):
        _adapters(config)


def test_adapters_skips_codex_without_repo() -> None:
    config = {"agents": {"codex": {"repo": "", "handles": ["code_review"]}}}
    assert _adapters(config) == []
