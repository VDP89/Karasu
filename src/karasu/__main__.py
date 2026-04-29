"""Karasu CLI entry point.

Subcommands:

* ``karasu watch``   — start the filesystem watcher and dispatch loop.
* ``karasu status``  — print a short summary of the recorded events.
* ``karasu tail``    — print JSONL events as they are observed.
* ``karasu analyze`` — analyze event-log noise and distribution.
* ``karasu chat``    — start the Telegram interface.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
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
# F6 — anything Karasu writes inside the watched root, plus the two
# transient file types editors leave behind, must stay off the bus by
# default. Without this the JSONL bus and operator-side ``tee``
# captures (e.g. ``karasu watch | tee watch.log``) feed back into the
# watcher and inflate event volume — observed live during the
# Phase 1C dogfood (issue #25).
DEFAULT_IGNORE = (
    ".git",
    "__pycache__",
    "*.pyc",
    ".karasu/",
    "events.jsonl",
    "*.log",
    "*.tmp",
)


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


def _adapter_timeout(name: str, cfg: dict) -> float | None:
    """Read ``timeout_s`` from an agent config, or ``None`` if absent.

    Validation: must be a positive number. ``None``/missing means
    fall back to the adapter's own default. Negative or zero is
    nonsensical and silently coerces a "no timeout" semantic that
    Phase 1 does not want.
    """
    raw = cfg.get("timeout_s")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"agents.{name}.timeout_s must be a positive number, got {raw!r}"
        ) from exc
    if value <= 0:
        raise ValueError(
            f"agents.{name}.timeout_s must be > 0, got {value}"
        )
    return value


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
        timeout = _adapter_timeout("claude_code", claude)
        if timeout is not None:
            kwargs["timeout"] = timeout
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
    path = _event_path(event) or "-"
    agent = event.dispatch.get("agent") or event.response.get("agent") or "-"
    return f"{event.timestamp} {event.type} source={event.source} agent={agent} path={path} id={event.id}"


def _event_path(event: Event) -> str | None:
    raw = event.data.get("path") or event.data.get("correlates")
    return str(raw) if raw else None


def _event_time(event: Event) -> datetime | None:
    try:
        return datetime.fromisoformat(event.timestamp)
    except ValueError:
        return None


def _analyze_events(events: Sequence[Event], duplicate_window_ms: int = 100) -> dict:
    by_type: Counter[str] = Counter(event.type for event in events)
    by_path: Counter[str] = Counter(
        path for event in events if (path := _event_path(event)) is not None
    )
    by_second: Counter[str] = Counter()
    duplicate_count = 0
    previous_by_key: dict[tuple[str, str], datetime] = {}

    for event in events:
        ts = _event_time(event)
        if ts is None:
            continue
        by_second[ts.isoformat(timespec="seconds")] += 1
        path = _event_path(event)
        if path is None:
            continue
        key = (event.type, path)
        previous = previous_by_key.get(key)
        if previous is not None:
            delta_ms = (ts - previous).total_seconds() * 1000
            if 0 <= delta_ms <= duplicate_window_ms:
                duplicate_count += 1
        previous_by_key[key] = ts

    total = len(events)
    unique_paths = len(by_path)
    file_changes = by_type.get("file_change", 0)
    duplication_factor = (file_changes / unique_paths) if unique_paths else 0.0

    return {
        "total_events": total,
        "by_type": dict(by_type),
        "top_paths": dict(by_path.most_common(10)),
        "max_events_per_second": max(by_second.values(), default=0),
        "duplicate_window_ms": duplicate_window_ms,
        "duplicates_same_type_path_window": duplicate_count,
        "unique_paths": unique_paths,
        "duplication_factor_file_changes_per_path": round(duplication_factor, 2),
    }


def _print_analysis(analysis: dict) -> None:
    print(f"Events analyzed: {analysis['total_events']}")
    print("\nBy type:")
    for event_type, count in sorted(analysis["by_type"].items()):
        print(f"  {event_type}: {count}")
    print("\nDuplicates:")
    print(
        f"  same type+path within {analysis['duplicate_window_ms']}ms: "
        f"{analysis['duplicates_same_type_path_window']}"
    )
    print("\nBurst detection:")
    print(f"  max events per second: {analysis['max_events_per_second']}")
    print("\nTop paths:")
    for path, count in analysis["top_paths"].items():
        print(f"  {path}: {count}")
    print("\nSignal/noise proxy:")
    print(f"  unique paths: {analysis['unique_paths']}")
    print(
        "  file_change events per unique path: "
        f"{analysis['duplication_factor_file_changes_per_path']}x"
    )


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


def cmd_analyze(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    bus = JsonlEventBus(_bus_path(config))
    events = list(bus.read())
    analysis = _analyze_events(events, duplicate_window_ms=args.duplicate_window_ms)
    if args.json:
        print(json.dumps(analysis, indent=2, sort_keys=True))
    else:
        _print_analysis(analysis)
    return 0


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

    analyze = sub.add_parser("analyze", help="analyze event-log noise and distribution")
    analyze.add_argument("--duplicate-window-ms", type=int, default=100, help="window for duplicate detection")
    analyze.add_argument("--json", action="store_true", help="print machine-readable JSON")
    analyze.set_defaults(func=cmd_analyze)

    sub.add_parser("chat", help="start the Telegram interface").set_defaults(func=cmd_chat)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
