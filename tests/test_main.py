import pytest

from karasu.__main__ import DEFAULT_IGNORE, _adapters, _agent_config, _normalize_handles


def test_default_ignore_covers_self_generated_paths() -> None:
    # F6 — the bus, log captures, and editor tmp files must be on the
    # default ignore list so a fresh ``karasu.yaml`` without an explicit
    # ``watch.ignore`` does not amplify its own output.
    expected = {"events.jsonl", "*.log", "*.tmp", ".karasu/"}
    missing = expected - set(DEFAULT_IGNORE)
    assert not missing, f"DEFAULT_IGNORE missing: {sorted(missing)}"


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


def test_adapters_preserves_default_handles_when_yaml_omits_them() -> None:
    config = {"agents": {"claude_code": {"command": "claude"}}}
    adapters = _adapters(config)
    assert len(adapters) == 1
    # ClaudeCodeAdapter ships with these defaults; absence of `handles`
    # in YAML must leave them intact rather than turning the adapter
    # into a catch-all.
    assert adapters[0].handles == ("code_change", "bug_fix", "implementation")


def test_adapters_uses_explicit_handles_from_yaml() -> None:
    config = {
        "agents": {
            "claude_code": {"command": "claude", "handles": ["code_change"]}
        }
    }
    adapters = _adapters(config)
    assert adapters[0].handles == ("code_change",)


def test_adapters_registers_claude_with_empty_config_dict() -> None:
    # `agents.claude_code: {}` means "use all defaults" — must still
    # register the adapter, not silently skip it.
    adapters = _adapters({"agents": {"claude_code": {}}})
    assert len(adapters) == 1
    assert adapters[0].name == "claude_code"
    assert adapters[0].handles == ("code_change", "bug_fix", "implementation")


def test_adapters_skips_claude_when_key_absent() -> None:
    assert _adapters({"agents": {}}) == []
    assert _adapters({}) == []


def test_agent_config_returns_dict_unchanged() -> None:
    assert _agent_config("claude_code", {"command": "claude"}) == {"command": "claude"}
    assert _agent_config("claude_code", {}) == {}


def test_agent_config_treats_none_and_false_as_disabled() -> None:
    assert _agent_config("claude_code", None) is None
    assert _agent_config("claude_code", False) is None


def test_agent_config_rejects_scalar_values() -> None:
    with pytest.raises(ValueError, match="agents.claude_code must be a mapping"):
        _agent_config("claude_code", "claude")
    with pytest.raises(ValueError, match="agents.codex must be a mapping"):
        _agent_config("codex", 42)
    with pytest.raises(ValueError, match="agents.claude_code must be a mapping"):
        _agent_config("claude_code", True)


def test_agent_config_rejects_list() -> None:
    with pytest.raises(ValueError, match="agents.claude_code must be a mapping"):
        _agent_config("claude_code", ["a", "b"])


def test_adapters_skips_claude_when_disabled_with_false() -> None:
    # Common YAML toggle: `agents.claude_code: false` to disable the
    # adapter without removing config keys around it. Must not crash.
    assert _adapters({"agents": {"claude_code": False}}) == []


def test_adapters_skips_claude_when_disabled_with_null() -> None:
    assert _adapters({"agents": {"claude_code": None}}) == []


def test_adapters_raises_on_scalar_agent_section() -> None:
    with pytest.raises(ValueError, match="agents.claude_code must be a mapping"):
        _adapters({"agents": {"claude_code": "claude"}})
