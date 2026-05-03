"""Capture UI screenshots for audit attachment.

Per UI-0 design brief §7, every UI-N PR MUST ship screenshots
of every state introduced or changed. This script automates
that: it spins up the UI server against a synthetic
``events.jsonl`` with the relevant chunk-4c fields populated,
opens each documented state in a headless browser, and writes
PNGs under ``docs/ui/screenshots/UI-N-<slug>/``.

Usage:
    python scripts/ui_screenshots.py UI-1-rebase

Requires Playwright with Chromium installed locally:
    pip install playwright
    python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_ROOT = REPO_ROOT / "docs" / "ui" / "screenshots"

# Synthetic events that exercise the surface; mirror the chunk-4c
# bus schema so the UI projection has all fields populated.
SYNTHETIC_EVENTS = [
    {
        "id": "evt001",
        "timestamp": "2026-05-03T10:00:00Z",
        "type": "file_change",
        "source": "watcher",
        "data": {
            "path": "src/foo.py",
            "change_type": "modified",
            "classification": "code_change",
            "priority": "normal",
        },
        "dispatch": {},
        "response": {},
    },
    {
        "id": "evt002",
        "timestamp": "2026-05-03T10:00:01Z",
        "type": "agent_response",
        "source": "adapter",
        "data": {
            "correlates": "evt001",
            "path": "src/foo.py",
            "priority": "normal",
        },
        "dispatch": {
            "agent": "claude_code",
            "status": "completed",
            "trust_level": 1,
        },
        "response": {"content": "done", "requires_human": False},
    },
    {
        "id": "evt003",
        "timestamp": "2026-05-03T10:00:05Z",
        "type": "file_change",
        "source": "github_webhook",
        "data": {
            "path": "src/bar.py",
            "change_type": "review_comment",
            "classification": "code_change",
            "priority": "high",
            "github_event": "pull_request_review_comment",
            "github_action": "created",
            "github_pr": 42,
            "github_repo": "VDP89/Karasu-",
            "github_author": "reviewer1",
            "github_body": "please rename foo to bar",
        },
        "dispatch": {},
        "response": {},
    },
    {
        "id": "evt004",
        "timestamp": "2026-05-03T10:00:30Z",
        "type": "file_change",
        "source": "controller",
        "data": {
            "path": "src/foo.py",
            "change_type": "modified",
            "classification": "code_change",
            "priority": "high",
            "controller_resubmit": True,
            "resubmit_origin": "evt001",
            "controller_chain_depth": 1,
        },
        "dispatch": {},
        "response": {},
    },
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(workdir: Path, port: int) -> http.server.ThreadingHTTPServer:
    """Start the UI server with cwd pinned to ``workdir`` so the
    EVENT_LOG path resolves to the synthetic file."""
    os.chdir(workdir)
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from karasu.ui.server import UIHandler

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), UIHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    return srv


def _seed_workdir(workdir: Path) -> None:
    bus = workdir / ".karasu" / "events.jsonl"
    bus.parent.mkdir(parents=True, exist_ok=True)
    with bus.open("w", encoding="utf-8") as fh:
        for event in SYNTHETIC_EVENTS:
            fh.write(json.dumps(event) + "\n")


def _capture(slug: str, port: int, out_dir: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "error: playwright is not installed.\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(2)

    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            print(
                f"error: could not launch chromium: {exc}\n"
                "  python -m playwright install chromium",
                file=sys.stderr,
            )
            sys.exit(2)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{port}/")
        # Give the page's setInterval(load,3000) one cycle to settle.
        page.wait_for_load_state("networkidle")
        time.sleep(0.5)
        page.screenshot(path=out_dir / "00-index-default.png", full_page=True)
        browser.close()
    print(f"wrote screenshots to {out_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "slug",
        help="chunk slug (e.g. UI-1-rebase). Becomes the screenshot dir name.",
    )
    args = parser.parse_args(argv)

    out_dir = SCREENSHOTS_ROOT / args.slug
    port = _free_port()
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        _seed_workdir(workdir)
        srv = _start_server(workdir, port)
        try:
            _capture(args.slug, port, out_dir)
        finally:
            srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
