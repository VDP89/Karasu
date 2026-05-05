"""Run Google Lighthouse against the local Karasu UI server.

Codex pin #2 from the UI-8 audit (PR #80): Lighthouse is allowed
as VERIFICATION, not as design driver. The thresholds locked
below are the audit contract from UI-0 §10:

    Performance      >= 95
    Accessibility    >= 95
    Best Practices   >= 95
    SEO              >= 90  (lower bar — operator surface, no
                              public marketing copy, no JSON-LD,
                              no canonical-tag concerns)

A failing threshold is a P0 for the chunk that introduced the
regression. Lighthouse "improve PWA score" suggestions that
would add chrome (install prompt component, connection badge,
update toast, etc.) are explicitly OUT of scope — see
docs/ui/lighthouse/README.md for the ignore list.

The runner spins up a Karasu UI server in a temp dir with a
seeded synthetic bus, runs ``lighthouse <url> --output=json``
via npx, parses the JSON, prints the scores + the failing
audit ids, asserts the thresholds, and writes the report to
``docs/ui/lighthouse/YYYY-MM-DD.json`` (filename derived from
the UTC date at run time — e.g. ``2026-05-04.json``). Same-day
re-runs overwrite the previous report deliberately; one
canonical report per day. Codex P2 polish on PR #81 audit
spelled out the literal filename here so the operator does not
look for a literal ``<date>.json``.

Usage:
    python scripts/ui_lighthouse.py
    python scripts/ui_lighthouse.py --skip-pwa   # default behaviour
    python scripts/ui_lighthouse.py --url URL    # override target

Requires:
    - Node.js >= 18
    - Lighthouse CLI (resolved via ``npx --yes lighthouse``)
    - Chrome / Chromium (Lighthouse drives a real browser)

PWA category is skipped by default because Lighthouse's
installable-PWA audits depend on HTTPS; the local dev server
is HTTP and the manual SW verification path lives in
docs/ui/screenshots/UI-8-pwa/README.md instead.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.server
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LIGHTHOUSE_DIR = REPO_ROOT / "docs" / "ui" / "lighthouse"

# Threshold contract — UI-0 §10. Bump only with an audit-locked
# rationale recorded in docs/ui/lighthouse/README.md.
THRESHOLDS = {
    "performance": 95,
    "accessibility": 95,
    "best-practices": 95,
    "seo": 90,
}

# Categories to evaluate. PWA skipped by default — see module
# docstring for the HTTPS rationale.
DEFAULT_CATEGORIES = ("performance", "accessibility", "best-practices", "seo")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(workdir: Path, port: int) -> http.server.ThreadingHTTPServer:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from karasu.ui import server as ui_server

    ui_server.configure(workdir / ".karasu" / "events.jsonl")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), ui_server.UIHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    return srv


def _seed_workdir(workdir: Path) -> None:
    """Seed a small synthetic bus so the Lighthouse run hits the
    populated branches of the surface (timeline + map + drawer
    JS) instead of the empty-state fallback. The exact corpus is
    a 4-event tail mirroring the UI-3..UI-7 default capture
    seed."""
    bus = workdir / ".karasu" / "events.jsonl"
    bus.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "id": "lh-001",
            "timestamp": "2026-05-04T12:00:00Z",
            "type": "file_change",
            "source": "watcher",
            "data": {
                "path": "src/foo.py",
                "classification": "code_change",
                "priority": "normal",
            },
            "dispatch": {},
            "response": {},
        },
        {
            "id": "lh-002",
            "timestamp": "2026-05-04T12:00:01Z",
            "type": "agent_response",
            "source": "adapter",
            "data": {
                "correlates": "lh-001",
                "path": "src/foo.py",
                "priority": "normal",
            },
            "dispatch": {
                "agent": "claude_code",
                "status": "completed",
                "trust_level": 1,
            },
            "response": {"content": "ok", "requires_human": False},
        },
    ]
    with bus.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


def _resolve_lighthouse() -> list[str]:
    """Return the command prefix to invoke Lighthouse. Prefers a
    locally-installed binary on PATH; falls back to ``npx --yes``.

    On Windows, npm wraps node binaries in .cmd shims. shutil.which
    resolves the absolute path so subprocess.run(shell=False) finds
    them — direct ``["lighthouse", ...]`` would fail with a
    FileNotFoundError on Windows even when the shim is installed."""
    direct = shutil.which("lighthouse")
    if direct is not None:
        return [direct]
    npx = shutil.which("npx")
    if npx is not None:
        return [npx, "--yes", "lighthouse"]
    print(
        "error: neither 'lighthouse' nor 'npx' is on PATH.\n"
        "  install Node.js >= 18 and run:\n"
        "    npm install -g lighthouse\n"
        "  or rely on npx (bundled with Node).",
        file=sys.stderr,
    )
    sys.exit(2)


def _run_lighthouse(
    url: str, categories: tuple[str, ...]
) -> dict[str, Any]:
    """Run Lighthouse against ``url`` and return the parsed JSON
    report. The CLI writes JSON to stdout when --output=json is
    set; a non-zero exit code surfaces a Lighthouse-side error
    (the network was unreachable, Chrome failed to launch, etc.)
    rather than a threshold failure — those are inspected after
    parsing."""
    cmd = [
        *_resolve_lighthouse(),
        url,
        "--output=json",
        "--quiet",
        "--chrome-flags=--headless --no-sandbox",
        f"--only-categories={','.join(categories)}",
    ]
    print(f"  running: {' '.join(cmd)}")
    try:
        # ``text=True`` defaults to the locale codec (cp1252 on
        # Windows) which crashes on the UTF-8 bytes Lighthouse
        # emits — caught the first time the script ran in
        # autonomous mode against the local stack. Pin
        # ``encoding="utf-8"`` so the read works on every host;
        # ``errors="replace"`` keeps a stray non-UTF8 byte from
        # taking down the report parse.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        print(
            "error: lighthouse failed.\n"
            f"  stderr: {exc.stderr.strip()[:500]}",
            file=sys.stderr,
        )
        sys.exit(2)
    except subprocess.TimeoutExpired:
        print(
            "error: lighthouse timed out (300 s).\n"
            "  the local server may be unreachable, OR Chromium "
            "took too long to render.",
            file=sys.stderr,
        )
        sys.exit(2)
    return json.loads(result.stdout)


def _evaluate_thresholds(report: dict[str, Any]) -> tuple[bool, list[str]]:
    """Walk the Lighthouse categories block and assert every
    threshold. Returns (all_passed, failing_lines)."""
    categories = report.get("categories", {})
    failures: list[str] = []
    for category_id, threshold in THRESHOLDS.items():
        category = categories.get(category_id)
        if category is None:
            failures.append(
                f"  {category_id:<16} MISSING from report"
            )
            continue
        score_raw = category.get("score")
        if score_raw is None:
            failures.append(
                f"  {category_id:<16} score is null (Lighthouse skipped this category)"
            )
            continue
        score = round(score_raw * 100)
        ok = score >= threshold
        line = (
            f"  {category_id:<16} {score:>3} / {threshold:>3}  "
            f"{'PASS' if ok else 'FAIL'}"
        )
        print(line)
        if not ok:
            failures.append(line)
    return (not failures), failures


def _print_failing_audits(report: dict[str, Any]) -> None:
    """List the audit ids that scored below 1.0 inside any
    failing category, so the operator knows which lighthouse
    items to inspect."""
    audits = report.get("audits", {})
    for category_id, category in report.get("categories", {}).items():
        if category_id not in THRESHOLDS:
            continue
        for ref in category.get("auditRefs", []):
            audit = audits.get(ref["id"], {})
            score = audit.get("score")
            if score is not None and score < 1.0:
                print(
                    f"    [{category_id}] {ref['id']}: "
                    f"{audit.get('title', '?')}"
                )


def _save_report(report: dict[str, Any], when: dt.datetime) -> Path:
    LIGHTHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    out = LIGHTHOUSE_DIR / f"{when.strftime('%Y-%m-%d')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=None,
        help="Override the target URL (default: spin up local UI server).",
    )
    parser.add_argument(
        "--include-pwa",
        action="store_true",
        help=(
            "Add the PWA category to the run. Off by default because "
            "the local server is HTTP — PWA installable audits need "
            "HTTPS."
        ),
    )
    args = parser.parse_args(argv)

    categories = DEFAULT_CATEGORIES
    if args.include_pwa:
        categories = (*categories, "pwa")

    # ``datetime.utcnow()`` is deprecated in 3.12+; use timezone-
    # aware UTC instead so the report filename / metadata stays
    # unambiguous across hosts.
    when = dt.datetime.now(dt.timezone.utc)

    if args.url is not None:
        url = args.url
        srv = None
    else:
        port = _free_port()
        url = f"http://127.0.0.1:{port}/"
        # We hold the workdir / server alive via context manager
        # so the chromium-driven Lighthouse run sees the seeded
        # bus.
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            _seed_workdir(workdir)
            srv = _start_server(workdir, port)
            try:
                report = _run_lighthouse(url, categories)
            finally:
                srv.shutdown()
        ok, failures = _evaluate_thresholds(report)
        if not ok:
            print("\nfailing audits:", file=sys.stderr)
            _print_failing_audits(report)
        path = _save_report(report, when)
        print(f"\nreport: {path.relative_to(REPO_ROOT)}")
        return 0 if ok else 1

    # External-URL path (for CI / staging audits). No server boot.
    report = _run_lighthouse(url, categories)
    ok, failures = _evaluate_thresholds(report)
    if not ok:
        print("\nfailing audits:", file=sys.stderr)
        _print_failing_audits(report)
    path = _save_report(report, when)
    print(f"\nreport: {path.relative_to(REPO_ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
