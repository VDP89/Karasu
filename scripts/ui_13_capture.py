"""Capture UI-13 login surface visual artefacts.

Two PNGs land under ``docs/ui/screenshots/UI-13-auth/``:

  00-login-pristine.png  — first visit, blank fields, error
                           slot hidden.
  01-login-error.png     — post-submit failure, error slot
                           visible per §3-E re-render.

Run from the repo root with Playwright + Chromium installed::

    pip install playwright
    python -m playwright install chromium
    python scripts/ui_13_capture.py

The script boots an in-process Karasu UI server with auth
ENABLED + ephemeral creds, drives Chromium headless to
capture the two states, and tears the server down. The
PNGs are committed as the chunk-9 visual deliverable per
UI-0 §7."""

from __future__ import annotations

import http.server
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from karasu.ui import server as ui_server  # noqa: E402
from karasu.ui._auth import write_credentials  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "ui" / "screenshots" / "UI-13-auth"
VIEWPORT = (960, 600)


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _start_server(
    workdir: Path, port: int
) -> http.server.ThreadingHTTPServer:
    creds_path = workdir / "karasu-auth.json"
    write_credentials(creds_path, username="dev", password="dev")

    ui_server.configure(
        event_log=workdir / "events.jsonl",
        scars_path=workdir / "scars",
        config_path=workdir / "karasu.yaml",
        push_store_path=workdir / "karasu-push.json",
    )
    ui_server.configure_auth(
        credentials_path=creds_path,
        no_auth=False,
        deployed=False,
        trusted_proxies=frozenset({"127.0.0.1", "::1"}),
        expected_origins=(f"http://127.0.0.1:{port}",),
    )
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), ui_server.UIHandler
    )
    threading.Thread(
        target=server.serve_forever, daemon=True, name="karasu-ui-13-capture"
    ).start()
    return server


def _capture(port: int) -> None:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{port}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            ctx = browser.new_context(
                viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}
            )
            page = ctx.new_page()

            # 00 — pristine login surface.
            page.goto(base + "/", wait_until="networkidle")
            page.screenshot(
                path=str(OUT_DIR / "00-login-pristine.png"),
                full_page=False,
            )

            # 01 — submit wrong creds via the form-urlencoded
            # path so the server's §3-E 200 + login.html
            # re-render with the error slot visible fires.
            page.fill("#username", "dev")
            page.fill("#password", "wrong-password")
            # Use form-mode submission (not the JS fetch path)
            # so the screenshot reflects the JS-disabled
            # contract: server returns 200 + re-rendered
            # login.html with the error slot visible.
            page.evaluate(
                """
                const f = document.getElementById('login-form');
                f.removeAttribute('id');
                f.submit();
                """
            )
            page.wait_for_load_state("networkidle")
            page.screenshot(
                path=str(OUT_DIR / "01-login-error.png"),
                full_page=False,
            )

            ctx.close()
        finally:
            browser.close()


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="karasu-ui-13-capture-"))
    port = _free_port()
    server = _start_server(workdir, port)
    try:
        # Give the server a beat to bind.
        time.sleep(0.2)
        _capture(port)
    finally:
        server.shutdown()
        server.server_close()
        ui_server._reset_auth_state()
        shutil.rmtree(workdir, ignore_errors=True)
    print(f"UI-13 captures landed under {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
