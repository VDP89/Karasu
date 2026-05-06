from pathlib import Path

import pytest

from karasu.__main__ import (
    DEFAULT_IGNORE,
    _adapter_timeout,
    _adapters,
    _agent_config,
    _normalize_handles,
    _telegram_chat_id,
    build_parser,
    cmd_ui,
)


def test_default_ignore_covers_self_generated_paths() -> None:
    # F6 — the bus, log captures, and editor tmp files must be on the
    # default ignore list so a fresh ``karasu.yaml`` without an explicit
    # ``watch.ignore`` does not amplify its own output.
    expected = {"events.jsonl", "*.log", "*.tmp", "*.tmp.*", ".karasu/"}
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


# ---------------------------------------------------------------------------
# F8 — adapter timeout_s configurable from YAML
# ---------------------------------------------------------------------------


def test_adapter_timeout_returns_none_when_absent() -> None:
    assert _adapter_timeout("claude_code", {"command": "claude"}) is None


def test_adapter_timeout_parses_int() -> None:
    assert _adapter_timeout("claude_code", {"timeout_s": 180}) == 180.0


def test_adapter_timeout_parses_float() -> None:
    assert _adapter_timeout("claude_code", {"timeout_s": 12.5}) == 12.5


def test_adapter_timeout_parses_string_number() -> None:
    # YAML can occasionally hand back strings if quoted; coerce.
    assert _adapter_timeout("claude_code", {"timeout_s": "60"}) == 60.0


def test_adapter_timeout_rejects_non_numeric() -> None:
    with pytest.raises(ValueError, match="claude_code.timeout_s"):
        _adapter_timeout("claude_code", {"timeout_s": "soon"})


def test_adapter_timeout_rejects_zero() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        _adapter_timeout("claude_code", {"timeout_s": 0})


def test_adapter_timeout_rejects_negative() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        _adapter_timeout("claude_code", {"timeout_s": -10})


def test_adapters_applies_timeout_from_yaml() -> None:
    config = {"agents": {"claude_code": {"command": "claude", "timeout_s": 200}}}
    adapters = _adapters(config)
    assert len(adapters) == 1
    assert adapters[0].timeout == 200.0


def test_adapters_keeps_default_timeout_when_yaml_omits_it() -> None:
    # Adapter ships with a 120 s default; absence of timeout_s in YAML
    # must not silently override it with anything else.
    config = {"agents": {"claude_code": {"command": "claude"}}}
    adapters = _adapters(config)
    assert adapters[0].timeout == 120.0


def test_telegram_chat_id_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARASU_TELEGRAM_CHAT_ID", "12345")
    assert _telegram_chat_id({}) == 12345


def test_telegram_chat_id_falls_back_to_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KARASU_TELEGRAM_CHAT_ID", raising=False)
    assert _telegram_chat_id({"chat_id": 999}) == 999


def test_telegram_chat_id_env_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARASU_TELEGRAM_CHAT_ID", "1")
    assert _telegram_chat_id({"chat_id": 2}) == 1


def test_telegram_chat_id_returns_none_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KARASU_TELEGRAM_CHAT_ID", raising=False)
    assert _telegram_chat_id({}) is None


def test_telegram_chat_id_rejects_non_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARASU_TELEGRAM_CHAT_ID", "not-a-number")
    with pytest.raises(ValueError, match="must be an integer"):
        _telegram_chat_id({})


def test_telegram_chat_id_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARASU_TELEGRAM_CHAT_ID", "  77  ")
    assert _telegram_chat_id({}) == 77


# ---------------------------------------------------------------------------
# cmd_ui — push store default resolution (Codex P1 on PR #98 round 1)
# ---------------------------------------------------------------------------
#
# UI-12 brief §3-F + §10.3 ratify ``karasu-push.json`` next to
# ``events.jsonl``. Parser default was a literal ``Path("karasu-
# push.json")`` which resolves against cwd, leaking the future
# private store outside the gitignored bus directory. The fix:
# parser default is the sentinel ``None``; ``cmd_ui`` resolves
# the default as ``_bus_path(config).parent / "karasu-push.json"``
# so the store anchors to the bus regardless of cwd.


def _capture_run_ui_server(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path | None]:
    """Stub ``run_ui_server`` and return the kwargs dict that
    will be populated when ``cmd_ui`` calls it. ``cmd_ui``
    imports ``run_ui_server`` lazily from
    ``karasu.ui.server`` so monkeypatching the module
    attribute before the call lands the stub on the lookup."""
    captured: dict[str, Path | None] = {}

    def fake_run_ui_server(**kwargs: object) -> None:
        for key, value in kwargs.items():
            captured[key] = value  # type: ignore[assignment]

    from karasu.ui import server as ui_server_module

    monkeypatch.setattr(
        ui_server_module, "run_ui_server", fake_run_ui_server
    )
    return captured


def test_cli_ui_push_store_parser_default_is_sentinel_none() -> None:
    """The argparse default must be ``None`` (sentinel) so
    ``cmd_ui`` can distinguish "operator did not pass the
    flag" from "operator explicitly chose this path". A literal
    Path default would erase that distinction and re-introduce
    the cwd-relative bug."""
    parser = build_parser()
    args = parser.parse_args(["ui"])
    assert args.push_store is None


def test_cli_ui_push_store_default_uses_default_bus_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``--push-store`` and without an
    ``event_bus.path`` in karasu.yaml, the store resolves to
    ``.karasu/karasu-push.json`` (parent of DEFAULT_BUS =
    ``.karasu/events.jsonl``). The store ends up under the
    gitignored ``.karasu/`` directory exactly as the brief
    ratifies."""
    captured = _capture_run_ui_server(monkeypatch)

    missing_config = tmp_path / "does-not-exist.yaml"
    parser = build_parser()
    args = parser.parse_args(
        ["--config", str(missing_config), "ui"]
    )
    cmd_ui(args)

    assert captured["push_store_path"] == Path(
        ".karasu/karasu-push.json"
    )


def test_cli_ui_push_store_default_resolves_next_to_custom_bus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``event_bus.path`` is configured, the default
    push store anchors to that bus's parent dir, not the cwd
    or DEFAULT_BUS. This is the specific case Codex P1 called
    out: an operator running ``karasu watch`` against a
    non-default bus path must NOT have ``karasu ui`` write
    a sibling push store to the repo root."""
    captured = _capture_run_ui_server(monkeypatch)

    custom_bus_dir = tmp_path / "custom-anchor"
    config_path = tmp_path / "karasu.yaml"
    config_path.write_text(
        "event_bus:\n"
        f"  path: {custom_bus_dir / 'events.jsonl'}\n",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        ["--config", str(config_path), "ui"]
    )
    cmd_ui(args)

    assert (
        captured["push_store_path"]
        == custom_bus_dir / "karasu-push.json"
    )


def test_cli_ui_push_store_explicit_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit ``--push-store PATH`` flag wins over the
    default-next-to-bus resolution. The flag is the documented
    operator override per the help text; the default
    resolution must not silently swallow it."""
    captured = _capture_run_ui_server(monkeypatch)

    explicit = tmp_path / "operator-chose-this.json"
    config_path = tmp_path / "karasu.yaml"
    config_path.write_text(
        "event_bus:\n  path: /some/other/anchor/events.jsonl\n",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args([
        "--config",
        str(config_path),
        "ui",
        "--push-store",
        str(explicit),
    ])
    cmd_ui(args)

    assert captured["push_store_path"] == explicit
