"""UI-13 CLI surface tests — `karasu auth set-credentials` +
`karasu ui --no-auth` startup guards.

Brief sections covered:
  * §3-B fail-closed startup (auth-on + missing/malformed
    credentials → exit 2 generic stderr).
  * §3-G --no-auth loopback-bind guard (Codex round 2 P1):
    --host non-loopback OR auth.trusted_proxies set explicitly
    in karasu.yaml → exit 2.
  * §3-G empty trusted_proxies refusal (Codex round 3 P1):
    deployed (non-loopback) bind + empty trusted_proxies
    → exit 2.
  * Bootstrap subcommand happy paths (TTY confirm + piped
    stdin)."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

import pytest

from karasu.__main__ import build_parser, cmd_auth_set_credentials, cmd_ui
from karasu.ui import server as ui_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_ui_auth_state() -> None:
    """Each test starts and ends with a pristine module state.
    cmd_ui mutates ui_server module globals via configure_auth;
    _reset_auth_state() restores the chunk-4 default."""
    ui_server._reset_auth_state()
    yield
    ui_server._reset_auth_state()


def _capture_run_ui_server(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Stub run_ui_server so cmd_ui returns without binding a
    socket. Captures the kwargs so tests can assert against
    them when the test is verifying side-effects."""
    captured: dict[str, Any] = {}

    def fake(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(ui_server, "run_ui_server", fake)
    return captured


def _write_creds_file(path: Path, *, username: str, password: str) -> None:
    from karasu.ui._auth import write_credentials

    write_credentials(path, username=username, password=password)


# ---------------------------------------------------------------------------
# karasu auth set-credentials — bootstrap subcommand
# ---------------------------------------------------------------------------


def test_auth_set_credentials_default_path_resolves_next_to_bus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --credentials, the default resolves to
    ``karasu-auth.json`` next to the configured bus log
    (mirror of the push-store sentinel resolution; brief
    §3-B "Default config dir is the same as karasu-push.json")."""
    bus_dir = tmp_path / "anchor"
    config = tmp_path / "karasu.yaml"
    config.write_text(
        f"event_bus:\n  path: {bus_dir / 'events.jsonl'}\n",
        encoding="utf-8",
    )
    # Pipe a password so the handler does not prompt.
    monkeypatch.setattr(sys, "stdin", io.StringIO("hunter2"))
    parser = build_parser()
    args = parser.parse_args(
        [
            "--config",
            str(config),
            "auth",
            "set-credentials",
            "--username",
            "victor",
        ]
    )
    rc = cmd_auth_set_credentials(args)
    assert rc == 0
    assert (bus_dir / "karasu-auth.json").is_file()


def test_auth_set_credentials_explicit_path_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "operator-chose.json"
    monkeypatch.setattr(sys, "stdin", io.StringIO("hunter2"))
    parser = build_parser()
    args = parser.parse_args(
        [
            "auth",
            "set-credentials",
            "--credentials",
            str(explicit),
            "--username",
            "victor",
        ]
    )
    rc = cmd_auth_set_credentials(args)
    assert rc == 0
    assert explicit.is_file()


def test_auth_set_credentials_empty_username_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("hunter2"))
    parser = build_parser()
    args = parser.parse_args(
        [
            "auth",
            "set-credentials",
            "--credentials",
            str(tmp_path / "auth.json"),
            "--username",
            "   ",
        ]
    )
    rc = cmd_auth_set_credentials(args)
    assert rc == 2


def test_auth_set_credentials_empty_piped_password_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    parser = build_parser()
    args = parser.parse_args(
        [
            "auth",
            "set-credentials",
            "--credentials",
            str(tmp_path / "auth.json"),
            "--username",
            "victor",
        ]
    )
    rc = cmd_auth_set_credentials(args)
    assert rc == 2


# ---------------------------------------------------------------------------
# karasu ui --no-auth — loopback-bind guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "::1", "localhost"],
)
def test_cmd_ui_no_auth_loopback_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    host: str,
) -> None:
    """Codex round 2 P1: --no-auth + a loopback bind starts
    (with the AUTH DISABLED warning) per §3-B test surface
    lines 355-359."""
    captured = _capture_run_ui_server(monkeypatch)
    parser = build_parser()
    args = parser.parse_args(
        [
            "--config",
            str(tmp_path / "missing.yaml"),
            "ui",
            "--no-auth",
            "--host",
            host,
        ]
    )
    rc = cmd_ui(args)
    assert rc == 0
    assert captured["host"] == host
    err = capsys.readouterr().err
    assert "AUTH DISABLED" in err


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "203.0.113.7"],
)
def test_cmd_ui_no_auth_non_loopback_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    host: str,
) -> None:
    """Codex round 2 P1 binding 2026-05-07: §3-B test surface
    line 360-362. --no-auth + non-loopback host → exit 2."""
    captured = _capture_run_ui_server(monkeypatch)
    parser = build_parser()
    args = parser.parse_args(
        [
            "--config",
            str(tmp_path / "missing.yaml"),
            "ui",
            "--no-auth",
            "--host",
            host,
        ]
    )
    rc = cmd_ui(args)
    assert rc == 2
    assert "loopback" in capsys.readouterr().err
    assert "host" not in captured  # run_ui_server never reached


def test_cmd_ui_no_auth_with_explicit_trusted_proxies_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Codex round 2 P1 binding: §3-B test surface line 363-364.
    --no-auth + auth.trusted_proxies set in karasu.yaml → exit 2."""
    captured = _capture_run_ui_server(monkeypatch)
    config = tmp_path / "karasu.yaml"
    config.write_text(
        "auth:\n  trusted_proxies: ['10.0.0.5']\n",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        [
            "--config",
            str(config),
            "ui",
            "--no-auth",
            "--host",
            "127.0.0.1",
        ]
    )
    rc = cmd_ui(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "trusted_proxies" in err
    assert "host" not in captured


# ---------------------------------------------------------------------------
# karasu ui (auth on) — fail-closed startup
# ---------------------------------------------------------------------------


def test_cmd_ui_auth_on_missing_credentials_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Brief §3-B: auth-on + missing credentials → exit 2 with
    a generic stderr line that names neither path nor
    fields."""
    captured = _capture_run_ui_server(monkeypatch)
    config = tmp_path / "karasu.yaml"
    config.write_text(
        f"event_bus:\n  path: {tmp_path / 'events.jsonl'}\n",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        [
            "--config",
            str(config),
            "ui",
            "--host",
            "127.0.0.1",
        ]
    )
    rc = cmd_ui(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "credentials are missing or malformed" in err
    # Privacy: never echo the resolved path or any field name.
    assert str(tmp_path) not in err
    assert "host" not in captured


def test_cmd_ui_auth_on_valid_credentials_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auth-on + valid credentials file + loopback bind → the
    server starts. configure_auth populates the module cache;
    run_ui_server is invoked with the wired paths."""
    captured = _capture_run_ui_server(monkeypatch)
    bus_dir = tmp_path / "anchor"
    bus_dir.mkdir()
    creds_path = bus_dir / "karasu-auth.json"
    _write_creds_file(creds_path, username="victor", password="hunter2")

    config = tmp_path / "karasu.yaml"
    config.write_text(
        f"event_bus:\n  path: {bus_dir / 'events.jsonl'}\n",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        [
            "--config",
            str(config),
            "ui",
            "--host",
            "127.0.0.1",
        ]
    )
    rc = cmd_ui(args)
    assert rc == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["event_log"] == bus_dir / "events.jsonl"
    # The configure_auth call populated the in-process state.
    assert ui_server.AUTH_NO_AUTH is False
    assert ui_server._AUTH_CREDS_CACHE is not None
    assert ui_server._AUTH_CREDS_CACHE.username == "victor"


def test_cmd_ui_auth_on_explicit_credentials_overrides_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_run_ui_server(monkeypatch)
    explicit = tmp_path / "ops-managed-auth.json"
    _write_creds_file(explicit, username="victor", password="hunter2")
    parser = build_parser()
    args = parser.parse_args(
        [
            "ui",
            "--credentials",
            str(explicit),
            "--host",
            "127.0.0.1",
        ]
    )
    rc = cmd_ui(args)
    assert rc == 0
    assert ui_server.AUTH_CREDENTIALS_PATH == explicit


def test_cmd_ui_auth_on_dev_posture_when_no_expected_origins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round 3 P0 audit binding 2026-05-08:
    ``deployed`` is decoupled from the bind address. With no
    auth.expected_origins configured (operator did not declare
    a public origin), the posture is dev — cookies non-Secure,
    Origin/Referer absent accepted as the dev fallback."""
    _capture_run_ui_server(monkeypatch)

    bus_dir = tmp_path / "anchor"
    bus_dir.mkdir()
    creds_path = bus_dir / "karasu-auth.json"
    _write_creds_file(creds_path, username="victor", password="hunter2")
    config = tmp_path / "karasu.yaml"
    config.write_text(
        f"event_bus:\n  path: {bus_dir / 'events.jsonl'}\n"
        "auth:\n  trusted_proxies: ['127.0.0.1', '203.0.113.7']\n",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        ["--config", str(config), "ui", "--host", "127.0.0.1"]
    )
    rc = cmd_ui(args)
    assert rc == 0
    assert ui_server.AUTH_DEPLOYED is False
    assert ui_server.AUTH_EXPECTED_ORIGINS == ()


def test_cmd_ui_auth_on_loopback_bind_with_public_origin_is_deployed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round 3 P0 regression: production shape is
    caddy/nginx terminating TLS while karasu binds 127.0.0.1.
    Configured auth.expected_origins MUST mark the posture as
    deployed even on a loopback bind — cookies Secure +
    Origin/Referer absent rejected."""
    _capture_run_ui_server(monkeypatch)

    bus_dir = tmp_path / "anchor"
    bus_dir.mkdir()
    creds_path = bus_dir / "karasu-auth.json"
    _write_creds_file(creds_path, username="victor", password="hunter2")
    config = tmp_path / "karasu.yaml"
    config.write_text(
        f"event_bus:\n  path: {bus_dir / 'events.jsonl'}\n"
        "auth:\n"
        "  trusted_proxies: ['127.0.0.1']\n"
        "  expected_origins:\n"
        "    - https://karasu.example.com\n",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        ["--config", str(config), "ui", "--host", "127.0.0.1"]
    )
    rc = cmd_ui(args)
    assert rc == 0
    # The bind is loopback BUT the operator configured the
    # public origin → deployed posture is on.
    assert ui_server.AUTH_DEPLOYED is True
    assert ui_server.AUTH_EXPECTED_ORIGINS == (
        "https://karasu.example.com",
    )


def test_cmd_ui_session_ttl_days_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--session-ttl-days plumbs through configure_auth to
    AUTH_SESSION_TTL_SECONDS. Brief §3-C 1..30 day range."""
    _capture_run_ui_server(monkeypatch)

    bus_dir = tmp_path / "anchor"
    bus_dir.mkdir()
    creds_path = bus_dir / "karasu-auth.json"
    _write_creds_file(creds_path, username="victor", password="hunter2")
    parser = build_parser()
    args = parser.parse_args(
        [
            "ui",
            "--credentials",
            str(creds_path),
            "--host",
            "127.0.0.1",
            "--session-ttl-days",
            "7",
        ]
    )
    rc = cmd_ui(args)
    assert rc == 0
    assert ui_server.AUTH_SESSION_TTL_SECONDS == 7 * 24 * 60 * 60


@pytest.mark.parametrize("days", [0, 31, -1, 100])
def test_cmd_ui_session_ttl_days_out_of_range_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    days: int,
) -> None:
    """Out-of-range TTL → exit 2 + generic stderr."""
    captured = _capture_run_ui_server(monkeypatch)
    parser = build_parser()
    args = parser.parse_args(
        [
            "ui",
            "--credentials",
            str(tmp_path / "auth.json"),
            "--host",
            "127.0.0.1",
            "--session-ttl-days",
            str(days),
        ]
    )
    rc = cmd_ui(args)
    assert rc == 2
    assert "session-ttl-days" in capsys.readouterr().err
    assert "host" not in captured


# ---------------------------------------------------------------------------
# Empty trusted_proxies + non-loopback bind (Codex round 3 P1)
# ---------------------------------------------------------------------------


def test_cmd_ui_empty_trusted_proxies_non_loopback_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Codex round 3 P1: §3-G test surface line 968-973. The
    operator-typo path closes at startup before traffic
    reaches the rate-limit derivation."""
    captured = _capture_run_ui_server(monkeypatch)
    bus_dir = tmp_path / "anchor"
    bus_dir.mkdir()
    creds_path = bus_dir / "karasu-auth.json"
    _write_creds_file(creds_path, username="victor", password="hunter2")
    config = tmp_path / "karasu.yaml"
    config.write_text(
        f"event_bus:\n  path: {bus_dir / 'events.jsonl'}\n"
        "auth:\n  trusted_proxies: []\n",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        ["--config", str(config), "ui", "--host", "0.0.0.0"]
    )
    rc = cmd_ui(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "trusted_proxies" in err
    assert "host" not in captured


def test_cmd_ui_expected_origins_and_trusted_proxies_flow_from_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """auth.expected_origins + auth.trusted_proxies in
    karasu.yaml flow through configure_auth so the live
    server enforces the deployed Origin/Referer match + the
    correct trusted-hop set."""
    _capture_run_ui_server(monkeypatch)
    bus_dir = tmp_path / "anchor"
    bus_dir.mkdir()
    creds_path = bus_dir / "karasu-auth.json"
    _write_creds_file(creds_path, username="victor", password="hunter2")
    config = tmp_path / "karasu.yaml"
    config.write_text(
        f"event_bus:\n  path: {bus_dir / 'events.jsonl'}\n"
        "auth:\n"
        "  trusted_proxies: ['127.0.0.1', '203.0.113.7']\n"
        "  expected_origins:\n"
        "    - https://karasu.example.com\n",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        ["--config", str(config), "ui", "--host", "127.0.0.1"]
    )
    rc = cmd_ui(args)
    assert rc == 0
    assert ui_server.AUTH_TRUSTED_PROXIES == frozenset(
        {"127.0.0.1", "203.0.113.7"}
    )
    assert ui_server.AUTH_EXPECTED_ORIGINS == ("https://karasu.example.com",)
