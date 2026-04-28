"""Karasu CLI entry point.

Subcommands:

* ``karasu watch``  — start the filesystem watcher and dispatch loop.
* ``karasu status`` — print a short summary of the recorded events.
* ``karasu tail``   — print JSONL events as they are observed.
* ``karasu chat``   — start the Telegram interface.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Sequence

import yaml

from karasu import __version__
from karasu.adapters import AgentAdapter, ClaudeCodeAdapter, CodexAdapter
from karasu.classifier import ClassificationRule, RuleClassifier
from karasu.eventbus import Event, JsonlEventBus, JsonlTailReader
from karasu.interface import TelegramInterface
from karasu.pipeline import Pipeline
from karasu.reporter import HumanReporter
from karasu.router import Dispatcher
from karasu.scars import ScarEngine
from karasu.trust import TrustGradient
from karasu.watcher import FilesystemWatcher

DEFAULT_CONFIG = Path("karasu.yaml")
DEFAULT_BUS = Path(".karasu/events.jsonl")
DEFAULT_SCARS = Path(".karasu/scars/")
DEFAULT_IGNORE = (".git", "__pycache__", "*.pyc", ".karasu/")


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _bus_path(config: dict) -> Path:
    return Path(config.get("event_bus", {}).get("path", str(DEFAULT_BUS)))


def _scars_path(config: dict) -> Path:
    return Path(config.get("scars", {}).get("rules_path", str(DEFAULT_SCARS)))


def _classifier(config: dict) -> RuleClassifier:
    rules = [
        ClassificationRule(**entry)
        for entry in config.get("classify", {}).get("patterns", [])
    ]
    return RuleClassifier(rules)


def _normalize_handles(name: str, handles) -> tuple[str, ...]:
    if handles is None:
        return ()
    if isinstance(handles, str) or not isinstance(handles, (list, tuple)):
        raise ValueError(
            f"agents.{name}.handles must be a list of strings, got {type(handles).__name__}: {handles!r}"
        )
    bad = [item for item in handles if not isinstance(item, str)]
    if bad:
        raise ValueError(
            f"agents.{name}.handles must contain only strings, got non-string items: {bad!r}"
        )
    return tuple(handles)


def _agent_config(name: str, value) -> dict | None:
    """Coerce an ``agents.<name>`` YAML entry into a config mapping.

    Conventions:
    - key absent, ``null``, or ``false`` → adapter disabled (returns ``None``).
    - mapping (including empty ``{}``) → adapter enabled, returned as-is.
    - anything else (scalar, list) → ``ValueError`` with the section name.
    """
    if value is None or value is False:
        return None
    if isinstance(value, dict):
        return value
    raise ValueError(
        f"agents.{name} must be a mapping, null, or false to disable; "
        f"got {type(value).__name__}: {value!r}"
    )


def _adapters(config: dict) -> list[AgentAdapter]:
    agents_cfg = config.get("agents", {}) or {}
    adapters: list[AgentAdapter] = []
    claude = _agent_config("claude_code", agents_cfg.get("claude_code"))
    if claude is not None:
        kwargs: dict = {
            "command": claude.get("command", "claude"),
            "trust_level": int(claude.get("trust_level", 1)),
        }
        # Only override the adapter's default handle set when the YAML
        # explicitly provides one. _normalize_handles returns () for
        # absent/null and AgentAdapter treats empty handles as a
        # wildcard, which would silently make the adapter catch-all.
        if claude.get("handles") is not None:
            kwargs["handles"] = _normalize_handles("claude_code", claude["handles"])
        adapters.append(ClaudeCodeAdapter(**kwargs))
    codex = _agent_config("codex", agents_cfg.get("codex"))
    if codex is not None and codex.get("repo"):
        kwargs = {
            "repo": codex["repo"],
            "token": os.environ.get("KARASU_CODEX_TOKEN"),
            "trust_level": int(codex.get("trust_level", 0)),
        }
        if codex.get("handles") is not None:
            kwargs["handles"] = _normalize_handles("codex", codex["handles"])
        adapters.append(CodexAdapter(**kwargs))
    return adapters


def _trust(config: dict) -> TrustGradient:
    levels = {
        name: int(cfg.get("trust_level", 0))
        for name, cfg in (config.get("agents", {}) or {}).items()
        if isinstance(cfg, dict)
    }
    return TrustGradient(levels)


def _format_tail_event(event: Event) -> str:
    path = event.data.get("path") or event.data.get("correlates") or "-"
    agent = event.dispatch.get("agent") or event.response.get("agent") or "-"
    return f"{event.timestamp} {event.type} source={event.source} agent={agent} path={path} id={event.id}"


def cmd_watch(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    bus = JsonlEventBus(_bus_path(config))
    classifier = _classifier(config)
    dispatcher = Dispatcher(bus=bus, adapters=_adapters(config))
    reporter = HumanReporter(_trust(config))
    scars = ScarEngine(_scars_path(config))

    def sink(report) -> None:
        print(report.text, flush=True)

    pipeline = Pipeline(classifier, dispatcher, reporter, sink, scars=scars)

    watch_cfg = config.get("watch", {})
    watcher = FilesystemWatcher(
        root=watch_cfg.get("path", "."),
        bus=bus,
        ignore=watch_cfg.get("ignore", DEFAULT_IGNORE),
        on_event=pipeline,
        debounce_ms=int(watch_cfg.get("debounce_ms", 250)),
    )
    print(f"karasu watch: writing events to {bus.path}", file=sys.stderr)
    watcher.run_forever()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    bus = JsonlEventBus(_bus_path(config))
    counts: Counter[str] = Counter()
    last_ts = ""
    for event in bus.read():
        counts[event.type] += 1
        last_ts = event.timestamp
    print(f"karasu {__version__}")
    print(f"event log: {bus.path}")
    print(f"events: {sum(counts.values())}")
    for event_type, count in sorted(counts.items()):
        print(f"  {event_type}: {count}")
    if last_ts:
        print(f"last event: {last_ts}")
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    bus = JsonlEventBus(_bus_path(config))
    reader = JsonlTailReader(bus.path, start_at_end=not args.from_start)
    seen = 0

    while True:
        for event in reader.read_new():
            if args.json:
                print(event.to_json(), flush=True)
            else:
                print(_format_tail_event(event), flush=True)
            seen += 1
            if args.limit is not None and seen >= args.limit:
                return 0

        if not args.follow:
            return 0
        time.sleep(args.interval)


def cmd_chat(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    bus = JsonlEventBus(_bus_path(config))
    telegram_cfg = config.get("interface", {}).get("telegram", {})
    token = telegram_cfg.get("token") or os.environ.get("KARASU_TELEGRAM_TOKEN", "")
    if token.startswith("${") and token.endswith("}"):
        token = os.environ.get(token[2:-1], "")
    if not token:
        print("error: no telegram token (set KARASU_TELEGRAM_TOKEN)", file=sys.stderr)
        return 2
    interface = TelegramInterface(
        token=token,
        bus=bus,
        allowed_users=telegram_cfg.get("allowed_users", []),
    )
    interface.run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="karasu", description=__doc__)
    parser.add_argument("--version", action="version", version=f"karasu {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="path to karasu.yaml (default: ./karasu.yaml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("watch", help="start the filesystem watcher").set_defaults(func=cmd_watch)
    sub.add_parser("status", help="print a summary of the event log").set_defaults(func=cmd_status)

    tail = sub.add_parser("tail", help="print events from the JSONL event log")
    tail.add_argument("--from-start", action="store_true", help="read existing events from the beginning")
    tail.add_argument("--follow", action="store_true", help="keep polling for new events")
    tail.add_argument("--interval", type=float, default=0.5, help="poll interval when --follow is set")
    tail.add_argument("--limit", type=int, default=None, help="stop after N events")
    tail.add_argument("--json", action="store_true", help="print raw event JSON")
    tail.set_defaults(func=cmd_tail)

    sub.add_parser("chat", help="start the Telegram interface").set_defaults(func=cmd_chat)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
