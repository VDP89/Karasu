"""Karasu CLI entry point.

Subcommands:

* ``karasu watch``   — start the filesystem watcher and dispatch loop.
* ``karasu status``  — print a short summary of the recorded events.
* ``karasu tail``    — print JSONL events as they are observed.
* ``karasu analyze`` — analyze event-log noise and distribution.
* ``karasu chat``    — start the Telegram interface.
* ``karasu hook``    — run as a git-hook trigger source (one-shot).
* ``karasu serve``   — run the GitHub webhook receiver (Phase 3+ chunk 4a).
* ``karasu peers``   — fetch a peer agent's A2A AgentCard (outbound discovery).
* ``karasu ui``      — run the local UI HTTP server (read-only surface over the bus).
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
from karasu.controller import LoopController
from karasu.eventbus import Event, JsonlEventBus, JsonlTailReader
from karasu.interface import TelegramInterface
from karasu.interface.commands import (
    capture_correct,
    capture_scar,
    format_agents,
    format_scars,
    format_status,
)
from karasu.pipeline import Pipeline
from karasu.reporter import HumanReporter
from karasu.router import Dispatcher
from karasu.scars import ScarEngine
from karasu.trust import TrustGradient
from karasu.watcher import FilesystemWatcher

DEFAULT_CONFIG = Path("karasu.yaml")
DEFAULT_BUS = Path(".karasu/events.jsonl")
DEFAULT_SCARS = Path(".karasu/scars/")
# F6 / F11 — anything Karasu writes inside the watched root, plus the
# transient file types editors leave behind, must stay off the bus by
# default. Without this the JSONL bus and operator-side ``tee``
# captures (e.g. ``karasu watch | tee watch.log``) feed back into the
# watcher and inflate event volume — observed live during the
# Phase 1C dogfood (issue #25).
#
# ``*.tmp.*`` covers Notepad's atomic-write artifacts on Windows:
# ``<original>.tmp.<PID>.<TS>`` (e.g. ``sample.py.tmp.5296.1777729004615``).
# The plain ``*.tmp`` pattern does NOT match those because they end
# in numeric digits, not ``.tmp``. Surfaced live during the Phase 3
# dogfood (issue #39).
DEFAULT_IGNORE = (
    ".git",
    "__pycache__",
    "*.pyc",
    ".karasu/",
    "events.jsonl",
    "*.log",
    "*.tmp",
    "*.tmp.*",
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


def _push_store_path(config: dict) -> Path:
    """Default path for the UI-12 push subscription store.

    Codex P1 (PR #98 round-1 audit): the store anchors next
    to ``events.jsonl`` so the gitignored ``.karasu/`` parent
    is reused. Operators can override with the
    ``event_bus.path`` config (this helper follows along).
    """
    return _bus_path(config).parent / "karasu-push.json"


def _credentials_path(config: dict) -> Path:
    """Default path for the UI-13 auth credentials store.

    Same anchor convention as the push store: next to
    ``events.jsonl`` so the gitignored bus parent dir keeps
    private material out of the repo root. Operators wiring
    a deployed instance can override with ``--credentials``.
    """
    return _bus_path(config).parent / "karasu-auth.json"


def _auth_section(config: dict) -> dict:
    """Read ``auth`` block from karasu.yaml as a dict (or {}
    when absent / wrong-shape)."""
    auth = config.get("auth")
    return auth if isinstance(auth, dict) else {}


def _auth_trusted_proxies_explicit(config: dict) -> bool:
    """True iff the operator set ``auth.trusted_proxies``
    explicitly in karasu.yaml. Used by the --no-auth gate to
    refuse a config that signals deployed intent."""
    return "trusted_proxies" in _auth_section(config)


def _auth_trusted_proxies(config: dict) -> frozenset[str]:
    """Resolve the trusted-proxy frozenset from karasu.yaml.

    Default per brief §3-G is the localhost pair
    ``["127.0.0.1", "::1"]`` — operators with a remote
    caddy/nginx host append the proxy IPs explicitly."""
    auth = _auth_section(config)
    raw = auth.get("trusted_proxies", ["127.0.0.1", "::1"])
    if not isinstance(raw, list):
        raise ValueError("auth.trusted_proxies must be a list of strings")
    return frozenset(str(x) for x in raw)


def _auth_expected_origins(config: dict) -> tuple[str, ...]:
    """Resolve the expected-origins tuple from karasu.yaml.

    Empty by default — origin_matches in dev posture (loopback
    bind) accepts absent Origin/Referer. Deployed posture must
    set this to the public origin (e.g. ``https://karasu.example``)
    so cross-site POSTs hit the §3-F 403 branch."""
    auth = _auth_section(config)
    raw = auth.get("expected_origins", [])
    if not isinstance(raw, list):
        raise ValueError("auth.expected_origins must be a list of strings")
    return tuple(str(x) for x in raw)


def _push_contact_email(config: dict) -> str:
    """VAPID ``sub`` claim contact email.

    Read from ``push.contact_email`` in karasu.yaml. Defaults
    to the placeholder per brief §10.4 — works for localhost
    dogfood; production should configure a real address.
    """
    from karasu.push_emit import DEFAULT_CONTACT_EMAIL

    push_cfg = config.get("push") or {}
    if not isinstance(push_cfg, dict):
        return DEFAULT_CONTACT_EMAIL
    raw = push_cfg.get("contact_email")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return DEFAULT_CONTACT_EMAIL


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


def _announce_autonomous_adapters(adapters: list[AgentAdapter]) -> None:
    """NICE-TO-HAVE #3 — loud stderr banner for adapters at trust>=2.

    The base-class constructor logs a structured warning per adapter,
    but operators running ``karasu watch`` / ``karasu serve``
    interactively don't always see Python logs. This banner prints
    once at startup, on stderr, in plain text so it shows up in the
    terminal regardless of logging config.

    Stays silent when no adapter is at the autonomous trust level.
    """
    from karasu.adapters.base import AUTONOMOUS_TRUST_LEVEL

    autonomous = [a for a in adapters if a.trust_level >= AUTONOMOUS_TRUST_LEVEL]
    if not autonomous:
        return
    names = ", ".join(
        f"{a.name}(trust={a.trust_level})" for a in autonomous
    )
    print(
        "⚠ trust gradient: adapter(s) "
        f"[{names}] will mutate operator state without per-call "
        "approval. See docs/local-dogfood.md \"Trust gradient — what "
        "trust_level actually does in production\".",
        file=sys.stderr,
        flush=True,
    )


def cmd_watch(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    bus = JsonlEventBus(_bus_path(config))
    classifier = _classifier(config)
    adapters = _adapters(config)
    _announce_autonomous_adapters(adapters)
    dispatcher = Dispatcher(bus=bus, adapters=adapters)
    reporter = HumanReporter(_trust(config))
    scars = ScarEngine(_scars_path(config))

    def sink(report) -> None:
        print(report.text, flush=True)

    pipeline = Pipeline(classifier, dispatcher, reporter, sink, scars=scars)

    # Phase 3 chunks 3a + 3b + 3c: pipeline runs through
    # LoopController, which (a) coordinates dispatch on a single
    # worker, (b) reacts to /correct and /scar human_decision
    # events by resubmitting the originating file_change, and
    # (c) manages registered trigger sources (the watcher here).
    controller = LoopController(pipeline, bus=bus)

    watch_cfg = config.get("watch", {})
    watcher = FilesystemWatcher(
        root=watch_cfg.get("path", "."),
        bus=bus,
        ignore=watch_cfg.get("ignore", DEFAULT_IGNORE),
        controller=controller,
        debounce_ms=int(watch_cfg.get("debounce_ms", 250)),
    )
    controller.add_source(watcher)

    # UI-12c — register PushEmit as a TriggerSource so the
    # controller manages its lifecycle alongside the watcher.
    # Bootstrap auto-generates a VAPID keypair on first start;
    # subsequent starts read the existing pair. Brief §3-A
    # binding: lives inside karasu watch (not karasu ui); the
    # cross-process file lock from UI-12c §3-G serialises the
    # prune writes against UI-12b's POST handlers.
    from karasu.push_emit import PushEmit, PushEmitConfig
    from karasu.push_emit._keys import bootstrap_if_missing
    from karasu.ui.push_store import PushStoreError

    push_config = PushEmitConfig(
        store_path=_push_store_path(config),
        bus_path=bus.path,
        contact_email=_push_contact_email(config),
        debounce_seconds=float(args.push_debounce_ms) / 1000.0,
    )

    # Codex P1 round 1 (UI-12c code audit) + brief §3-F
    # binding: VAPID bootstrap is FATAL at startup. A
    # malformed/unreadable push store must produce a loud
    # generic stderr message + non-zero exit + bus tail
    # untouched (NOT the UI server's HTTP 500 contract —
    # ``karasu watch`` is not an HTTP context).
    # ``LoopController.start()`` catches every
    # ``source.start()`` exception and continues, so we
    # preflight the bootstrap explicitly before
    # ``controller.run_forever()``. The preflight is
    # idempotent with the inner ``PushEmit.start()`` bootstrap
    # call (no-op when the store is already complete).
    try:
        bootstrap_if_missing(push_config.store_path)
    except PushStoreError:
        print(
            "error: karasu push subscription store is "
            "malformed; refusing to start. Inspect the file "
            "manually and remove or fix the corruption.",
            file=sys.stderr,
        )
        return 2

    push_emit = PushEmit(push_config)
    controller.add_source(push_emit)

    print(f"karasu watch: writing events to {bus.path}", file=sys.stderr)
    controller.run_forever()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the GitHub webhook receiver as a long-running source.

    Phase 3+ chunk 4a (#48). Reads ``KARASU_WEBHOOK_SECRET`` from
    env and fails CLOSED if it is missing, empty, or shorter than
    ``MIN_SECRET_LENGTH`` (F-WH-9). Builds the handler + source,
    registers the source with a fresh ``LoopController``, runs
    forever.
    """
    from karasu.controller.sources.webhook import (
        MIN_SECRET_LENGTH,
        WebhookConfigError,
        build_webhook_source,
    )

    # F-WH-9: fail closed before binding the port. Never start the
    # listener with an unsafe secret.
    secret = os.environ.get("KARASU_WEBHOOK_SECRET", "")
    if not secret:
        print(
            "error: KARASU_WEBHOOK_SECRET is not set; refusing to start "
            "the webhook receiver insecure",
            file=sys.stderr,
        )
        return 2
    if len(secret) < MIN_SECRET_LENGTH:
        print(
            f"error: KARASU_WEBHOOK_SECRET must be at least "
            f"{MIN_SECRET_LENGTH} bytes; got {len(secret)}",
            file=sys.stderr,
        )
        return 2

    config = _load_config(args.config)
    bus = JsonlEventBus(_bus_path(config))
    classifier = _classifier(config)
    adapters = _adapters(config)
    _announce_autonomous_adapters(adapters)
    dispatcher = Dispatcher(bus=bus, adapters=adapters)
    reporter = HumanReporter(_trust(config))
    scars = ScarEngine(_scars_path(config))

    def sink(report) -> None:
        print(report.text, flush=True)

    pipeline = Pipeline(classifier, dispatcher, reporter, sink, scars=scars)
    controller = LoopController(pipeline, bus=bus)

    # Chunk 4b: build the static A2A AgentCard so the webhook
    # receiver can serve GET /.well-known/agent-card.json. The card
    # advertises Karasu's baseline capabilities; ``base_url`` is the
    # host:port the operator bound the receiver to.
    from karasu.a2a import build_karasu_card

    card = build_karasu_card(base_url=f"http://{args.host}:{args.port}")

    try:
        source = build_webhook_source(
            secret=secret,
            bus=bus,
            submit=controller.submit,
            host=args.host,
            port=args.port,
            agent_card=card,
        )
    except WebhookConfigError as exc:
        # Should already have been caught above, but defence in
        # depth — never let an unsafe config silently slip through.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    controller.add_source(source)
    print(
        f"karasu serve: webhook receiver on http://{args.host}:{args.port}/webhook",
        file=sys.stderr,
    )
    controller.run_forever()
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Run a git-hook trigger source one-shot.

    Invoked as ``karasu hook <name>`` from a hook script
    (``.git/hooks/pre-commit`` etc.). Builds ``file_change`` events
    from the current git state, writes them to the bus, drains
    them through a controller worker, and exits.
    """
    from karasu.controller.sources.git_hook import (
        SUPPORTED_HOOKS,
        submit_for_hook,
    )

    if args.hook not in SUPPORTED_HOOKS:
        print(
            f"error: unsupported hook {args.hook!r}; expected one of "
            f"{sorted(SUPPORTED_HOOKS)}",
            file=sys.stderr,
        )
        return 2

    config = _load_config(args.config)
    bus = JsonlEventBus(_bus_path(config))
    classifier = _classifier(config)
    adapters = _adapters(config)
    # NICE-TO-HAVE #3 banner is intentionally NOT emitted here.
    # cmd_hook is a one-shot git-hook flow; the operator already
    # opted into the trust gradient when they launched cmd_watch /
    # cmd_serve in their long-running session. Polluting hook stderr
    # on every commit would be noisy and out of contract. The
    # structured logging.WARNING from AgentAdapter.__init__ still
    # fires for headless collectors.
    dispatcher = Dispatcher(bus=bus, adapters=adapters)
    reporter = HumanReporter(_trust(config))
    scars = ScarEngine(_scars_path(config))

    def sink(report) -> None:
        print(report.text, flush=True)

    pipeline = Pipeline(classifier, dispatcher, reporter, sink, scars=scars)

    # No bus subscription for one-shot hook runs — there is no
    # operator typing /correct mid-hook. Just the worker.
    controller = LoopController(pipeline)
    controller.start()
    try:
        count = submit_for_hook(args.hook, bus, controller.submit)
        if controller._queue is not None:
            controller._queue.join()
    finally:
        controller.stop()

    print(f"karasu hook {args.hook}: {count} event(s)", file=sys.stderr)
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


def _telegram_chat_id(telegram_cfg: dict) -> int | None:
    """Resolve the Telegram destination chat id.

    Order: ``KARASU_TELEGRAM_CHAT_ID`` env var, then
    ``interface.telegram.chat_id`` in YAML. Returns ``None`` when
    absent so the caller can fail-fast with a clean message instead
    of pushing the failure to the first ``send`` call.

    Raises ``ValueError`` for non-integer values so the operator
    learns at startup.
    """
    raw = os.environ.get("KARASU_TELEGRAM_CHAT_ID", "").strip()
    if not raw:
        raw = str(telegram_cfg.get("chat_id", "")).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(
            f"telegram chat id must be an integer, got {raw!r}"
        ) from exc


def cmd_chat(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    bus = JsonlEventBus(_bus_path(config))
    telegram_cfg = config.get("interface", {}).get("telegram", {}) or {}

    token = telegram_cfg.get("token") or os.environ.get("KARASU_TELEGRAM_TOKEN", "")
    if isinstance(token, str) and token.startswith("${") and token.endswith("}"):
        token = os.environ.get(token[2:-1], "")
    if not token:
        print("error: no telegram token (set KARASU_TELEGRAM_TOKEN)", file=sys.stderr)
        return 2

    try:
        chat_id = _telegram_chat_id(telegram_cfg)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if chat_id is None:
        print(
            "error: no telegram chat id (set KARASU_TELEGRAM_CHAT_ID)",
            file=sys.stderr,
        )
        return 2

    adapters = _adapters(config)
    scars = ScarEngine(_scars_path(config))
    classifier = _classifier(config)
    interface = TelegramInterface(
        token=token,
        bus=bus,
        chat_id=chat_id,
        allowed_users=telegram_cfg.get("allowed_users", []) or [],
        status_provider=lambda: format_status(bus),
        agents_provider=lambda: format_agents(adapters),
        scars_provider=lambda: format_scars(scars),
        correct_handler=lambda args: capture_correct(bus, scars, classifier, args),
        scar_handler=lambda args: capture_scar(bus, scars, classifier, args),
    )
    reporter = HumanReporter(_trust(config))
    reader = JsonlTailReader(bus.path, start_at_end=True)

    print(
        f"karasu chat: forwarding agent_response events to chat_id={chat_id}",
        file=sys.stderr,
    )
    interval = float(telegram_cfg.get("poll_interval", 0.5))
    interface.run_application(reader, reporter, poll_interval=interval)
    return 0


def _parse_retry_http_statuses(raw: str) -> frozenset[int]:
    """Argparse type-hook for ``--retry-http-statuses``.

    Empty string → empty frozenset (matches the documented default;
    keeps the round-trip ``CLI flag → fetch_card kwarg`` clean
    even when the operator passes ``--retry-http-statuses ''``).
    Otherwise comma-split → ``int(...)`` per part → range-check
    against the HTTP status range. Bad input fails fast with
    ``argparse.ArgumentTypeError`` so the operator sees a usage
    error, not a silent set membership miss at fetch time.
    """
    if not raw:
        return frozenset()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            code = int(part)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"--retry-http-statuses must be comma-separated "
                f"integers, got {part!r}"
            )
        if code < 100 or code >= 600:
            raise argparse.ArgumentTypeError(
                f"--retry-http-statuses must be HTTP status codes "
                f"(100-599), got {code}"
            )
        out.add(code)
    return frozenset(out)


def cmd_peers(args: argparse.Namespace) -> int:
    """Fetch and print a peer agent's A2A AgentCard.

    Outbound discovery counterpart to ``karasu serve``'s inbound
    ``/.well-known/agent-card.json``. No bus access, no side
    effects — read-only HTTP GET against the peer.
    """
    from karasu.a2a import AgentCardFetchError, fetch_card

    try:
        card = fetch_card(
            args.url,
            timeout=args.timeout,
            retries=args.retries,
            retry_http_statuses=args.retry_http_statuses,
        )
    except AgentCardFetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(card, indent=2))
        return 0

    name = card.get("name", "<unknown>")
    version = card.get("version", "<unknown>")
    print(f"name:        {name}")
    print(f"version:     {version}")
    description = card.get("description")
    if description:
        print(f"description: {description}")
    url = card.get("url")
    if url:
        print(f"url:         {url}")

    capabilities = card.get("capabilities") or {}
    print("capabilities:")
    print(f"  streaming:         {capabilities.get('streaming', False)}")
    print(
        f"  pushNotifications: "
        f"{capabilities.get('pushNotifications', False)}"
    )

    skills = card.get("skills") or []
    print(f"skills ({len(skills)}):")
    for skill in skills:
        skill_id = skill.get("id", "?")
        skill_name = skill.get("name", "")
        print(f"  - {skill_id}: {skill_name}")
        skill_desc = (skill.get("description") or "").strip()
        if skill_desc:
            print(f"      {skill_desc}")
    return 0


def cmd_auth_set_credentials(args: argparse.Namespace) -> int:
    """``karasu auth set-credentials`` — bootstrap or rotate the
    UI-13 auth credentials store (brief §3-B).

    Stdin pipe fallback (no TTY) lets ops automation set the
    password without an interactive prompt; documented in
    docs/deploy-runbook.md (chunk 9). Interactive flow uses
    getpass with a confirmation prompt.

    Default path resolves contextually next to the bus log
    (mirror of --push-store) so the private creds file stays
    under the gitignored ``.karasu/`` anchor.
    """
    from karasu.ui._auth import write_credentials

    config = _load_config(args.config)
    creds_path = args.credentials
    if creds_path is None:
        creds_path = _credentials_path(config)

    username = (args.username or "").strip()
    if not username and sys.stdin.isatty():
        username = input("Username: ").strip()
    if not username:
        sys.stderr.write("error: username required\n")
        return 2

    if not sys.stdin.isatty():
        password = sys.stdin.read().rstrip("\n")
        if not password:
            sys.stderr.write("error: password required (stdin empty)\n")
            return 2
    else:
        import getpass

        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm:  ")
        if not password:
            sys.stderr.write("error: password required\n")
            return 2
        if password != confirm:
            sys.stderr.write("error: password mismatch\n")
            return 2

    write_credentials(creds_path, username=username, password=password)
    sys.stdout.write(
        f"karasu auth credentials written to {creds_path}\n"
        "  -> mode 0600 on POSIX (advisory on Windows; verify NTFS ACLs).\n"
    )
    return 0


def _refuse(message: str) -> int:
    """Print a generic fail-closed error to stderr + exit 2.

    Mirrors the UI-12c bootstrap-fatal pattern (PushStoreError
    → cmd_watch returns 2). Brief §3-B + §3-G generic-message
    discipline: never echo file paths or secret material."""
    sys.stderr.write("error: " + message + "\n")
    return 2


def cmd_ui(args: argparse.Namespace) -> int:
    """Run the local Karasu UI HTTP server.

    UI-13 wires the auth perimeter at startup. Default posture
    is auth ENABLED with the credentials file resolved next to
    the bus log; ``--no-auth`` flips to dev posture and refuses
    if combined with a non-loopback bind or with an explicit
    ``auth.trusted_proxies`` in karasu.yaml (signals deployed
    intent — Codex round 2 P1 binding).

    Honours ``event_bus.path`` from ``karasu.yaml`` (UI-9
    deferred follow-up): an operator running ``karasu watch``
    against a non-default bus path can point ``karasu ui`` at
    the same log without a separate flag.
    """
    from karasu.ui._auth import AuthCredentialsError, is_loopback_bind
    from karasu.ui.server import configure_auth, run_ui_server

    config = _load_config(args.config)
    bus_path = _bus_path(config)
    push_store_path = args.push_store
    if push_store_path is None:
        # Codex P1 (PR #98 round-1 audit): default must resolve
        # next to the bus anchor — typically ``.karasu/`` which
        # is already gitignored — so the future private store
        # (UI-12b writers, UI-12c VAPID material) stays beside
        # ``events.jsonl`` instead of leaking into the repo root.
        push_store_path = bus_path.parent / "karasu-push.json"

    # ------------------------------------------------------------
    # UI-13 auth posture decision (brief §3-B + §3-G)
    # ------------------------------------------------------------
    no_auth = bool(args.no_auth)
    host_is_loopback = is_loopback_bind(args.host)
    # ``deployed`` controls cookie Secure flag + Origin/Referer
    # absent-rejection. Loopback bind → dev posture; non-loopback
    # → deployed posture per the brief's §3-A TLS expectation.
    deployed = not host_is_loopback

    try:
        trusted_proxies = _auth_trusted_proxies(config)
        expected_origins = _auth_expected_origins(config)
    except ValueError as exc:
        return _refuse(str(exc))

    if no_auth:
        # Codex round 2 P1 binding: --no-auth ONLY valid when
        # the bind host resolves entirely to loopback.
        if not host_is_loopback:
            return _refuse(
                "--no-auth requires --host on a loopback address "
                "(127.0.0.1, ::1, or localhost); refusing to start."
            )
        # Codex round 2 P1 binding: an explicit trusted_proxies
        # in karasu.yaml signals deployed intent and is
        # incompatible with auth being disabled.
        if _auth_trusted_proxies_explicit(config):
            return _refuse(
                "--no-auth incompatible with auth.trusted_proxies in "
                "karasu.yaml (signals deployed intent); refusing to start."
            )
        # Loud-stderr warning per brief §3-B line 326-328.
        sys.stderr.write(
            "WARNING karasu.ui.auth: AUTH DISABLED -- dev only, "
            "NOT for production. See docs/deploy-runbook.md.\n"
        )
        try:
            configure_auth(no_auth=True)
        except AuthCredentialsError:
            # Defensive — configure_auth(no_auth=True) does NOT
            # load creds, so this branch should be unreachable.
            return _refuse(
                "karasu auth credentials are missing or malformed; "
                "refusing to start. See docs/deploy-runbook.md for bring-up."
            )
    else:
        # Codex round 3 P1 binding: empty trusted_proxies +
        # non-loopback bind closes the operator-typo path
        # before traffic reaches the rate-limit derivation.
        if not trusted_proxies and not host_is_loopback:
            return _refuse(
                "deployed posture requires non-empty auth.trusted_proxies; "
                "refusing to start. See docs/deploy-runbook.md for the "
                "trusted-hop walk requirements."
            )
        creds_path = args.credentials
        if creds_path is None:
            creds_path = _credentials_path(config)
        try:
            configure_auth(
                credentials_path=creds_path,
                no_auth=False,
                deployed=deployed,
                trusted_proxies=trusted_proxies,
                expected_origins=expected_origins,
            )
        except AuthCredentialsError:
            return _refuse(
                "karasu auth credentials are missing or malformed; "
                "refusing to start. See docs/deploy-runbook.md for bring-up."
            )

    run_ui_server(
        host=args.host,
        port=args.port,
        event_log=bus_path,
        scars_path=_scars_path(config),
        config_path=args.config,
        push_store_path=push_store_path,
    )
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
    watch = sub.add_parser("watch", help="start the filesystem watcher")
    watch.add_argument(
        "--push-debounce-ms",
        type=int,
        default=5000,
        metavar="MS",
        help=(
            "UI-12c per-(endpoint, category) trailing debounce "
            "window in milliseconds. Brief §10.5 default 5000. "
            "Lower for tight dogfood loops; higher for noisier "
            "buses."
        ),
    )
    watch.set_defaults(func=cmd_watch)
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

    hook = sub.add_parser(
        "hook", help="run as a git hook trigger source (one-shot)"
    )
    hook.add_argument(
        "hook",
        choices=("pre-commit", "post-commit", "post-merge"),
        help="git hook name",
    )
    hook.set_defaults(func=cmd_hook)

    serve = sub.add_parser(
        "serve",
        help="run the GitHub webhook receiver (long-running TriggerSource)",
    )
    serve.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    serve.add_argument("--port", type=int, default=8080, help="HTTP bind port")
    serve.set_defaults(func=cmd_serve)

    ui = sub.add_parser(
        "ui",
        help=(
            "run the local Karasu UI HTTP server (read-only "
            "surface over the bus)"
        ),
    )
    ui.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    ui.add_argument(
        "--port",
        type=int,
        default=8787,
        help="HTTP bind port (default: 8787)",
    )
    ui.add_argument(
        "--push-store",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "path to the push subscription store (UI-12 brief "
            "§3-F PRIVATE STORE). When omitted, defaults to "
            "``karasu-push.json`` next to the configured bus "
            "(typically ``.karasu/karasu-push.json``) so the "
            "private store stays under the gitignored bus "
            "anchor. UI-12a is read-only against this path; "
            "UI-12b earns the writers, UI-12c earns VAPID key "
            "generation."
        ),
    )
    ui.add_argument(
        "--no-auth",
        action="store_true",
        default=False,
        help=(
            "UI-13 dev flag — disable the auth perimeter for "
            "localhost iteration. ONLY valid when --host is a "
            "loopback address (127.0.0.1, ::1, localhost) AND "
            "karasu.yaml does NOT declare auth.trusted_proxies "
            "(non-default value signals deployed intent). "
            "Emits a loud-stderr 'AUTH DISABLED' warning at "
            "startup. NEVER set in any documented "
            "deploy-runbook.md path."
        ),
    )
    ui.add_argument(
        "--credentials",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "UI-13 path to the auth credentials store. When "
            "omitted, defaults to ``karasu-auth.json`` next to "
            "the configured bus (typically "
            "``.karasu/karasu-auth.json``). Bootstrap with "
            "``karasu auth set-credentials``."
        ),
    )
    ui.set_defaults(func=cmd_ui)

    # UI-13 §3-B bootstrap CLI: ``karasu auth set-credentials``.
    # Two-level subcommand so the auth namespace can grow
    # (``karasu auth rotate``, ``karasu auth show``, etc.) in
    # follow-up chunks without crowding the top-level help.
    auth = sub.add_parser(
        "auth",
        help="auth credentials management (UI-13)",
    )
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    set_creds = auth_sub.add_parser(
        "set-credentials",
        help=(
            "bootstrap or rotate karasu-auth.json. "
            "Interactive prompt or stdin pipe."
        ),
    )
    set_creds.add_argument(
        "--credentials",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "default: ``karasu-auth.json`` next to the bus log; "
            "matches the cmd_ui --credentials flag."
        ),
    )
    set_creds.add_argument(
        "--username",
        default=None,
        metavar="NAME",
        help=(
            "username for the credentials. When omitted and "
            "stdin is a TTY, prompts interactively; when "
            "omitted on a piped stdin, exits 2."
        ),
    )
    set_creds.set_defaults(func=cmd_auth_set_credentials)

    from karasu.a2a import (
        DEFAULT_FETCH_RETRIES,
        DEFAULT_FETCH_RETRY_HTTP_STATUSES,
        DEFAULT_FETCH_TIMEOUT,
        RECOMMENDED_RETRY_HTTP_STATUSES,
    )

    peers = sub.add_parser(
        "peers",
        help=(
            "fetch and print a peer agent's A2A AgentCard "
            "(outbound discovery)"
        ),
    )
    peers.add_argument(
        "url",
        help=(
            "base URL of the peer agent (e.g. http://127.0.0.1:8080); "
            "/.well-known/agent-card.json is appended automatically "
            "if absent"
        ),
    )
    peers.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_FETCH_TIMEOUT,
        help=(
            f"HTTP timeout in seconds (default: {DEFAULT_FETCH_TIMEOUT})"
        ),
    )
    peers.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_FETCH_RETRIES,
        help=(
            "additional retry attempts on transient network errors "
            "(URLError only by default; see --retry-http-statuses to "
            "extend coverage). Backoff is exponential. Default: "
            f"{DEFAULT_FETCH_RETRIES} (no retries — preserves "
            "single-shot semantics)."
        ),
    )
    _recommended = ",".join(
        str(s) for s in sorted(RECOMMENDED_RETRY_HTTP_STATUSES)
    )
    peers.add_argument(
        "--retry-http-statuses",
        type=_parse_retry_http_statuses,
        default=DEFAULT_FETCH_RETRY_HTTP_STATUSES,
        metavar="CODES",
        help=(
            "comma-separated HTTP status codes that should trigger "
            "the same retry loop as URLError. Empty by default "
            "(non-2xx HTTP statuses surface immediately). "
            f"Recommended for transient proxy errors: {_recommended}. "
            "Shares the --retries budget with URLError retries."
        ),
    )
    peers.add_argument(
        "--json",
        action="store_true",
        help="print the raw card JSON instead of formatted text",
    )
    peers.set_defaults(func=cmd_peers)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
