"""Capture UI-14 mobile-viewport audit (§3-D SEALED).

The brief seals four mobile widths to audit: 320 / 360 / 375 /
414. The captured surfaces:

  Login (pre-auth) — UI-13 territory; UI-14 made ZERO login
  changes, so the four PNGs are a sanity check that the
  manifest body / theme-color / SW lifecycle changes haven't
  regressed the login render at narrow widths.

  Shell (post-auth) — UI-14 added a fifth slot to the footer
  (.footer-install) plus an inline Refresh button visible only
  in the §3-F update state. Both states are captured at every
  width so the auditor can see the most-chrome layout (update
  state, longest label + Refresh button) at 320 px alongside
  the default state.

Output: ``docs/ui/screenshots/UI-14-mobile/``

  00-login-320.png    320x568    iPhone SE 1st gen
  01-login-360.png    360x640    Android baseline
  02-login-375.png    375x667    iPhone SE 2/3 / 12 mini
  03-login-414.png    414x736    iPhone Plus / Pro Max
  04-shell-default-320.png    shell with Install: <state>
  05-shell-default-360.png
  06-shell-default-375.png
  07-shell-default-414.png
  08-shell-update-320.png     shell forced into the update
  09-shell-update-360.png     state via JS so the Refresh
  10-shell-update-375.png     button is visible at the
  11-shell-update-414.png     widest-chrome layout

Run from the repo root with Playwright + Chromium installed::

    pip install playwright
    python -m playwright install chromium
    python scripts/ui_14_mobile_audit.py

The script boots an in-process Karasu UI server with auth
ENABLED + ephemeral creds (mirrors ui_13_capture.py) inside an
isolated tempdir, drives Chromium headless across all 4
sealed widths, and tears the server + tempdir down. PNGs are
committed as the §3-D mobile-audit deliverable.

§3-D default is "only-if-screenshots-demand" for the <360 px
breakpoint — the script does NOT apply layout fixes; the
auditor reviews the captured PNGs and decides whether a
breakpoint is justified. Any fix lands in a follow-up commit
inside this branch.
"""

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

OUT_DIR = REPO_ROOT / "docs" / "ui" / "screenshots" / "UI-14-mobile"

# §3-D SEALED — four mobile widths. Heights pair with each
# width's typical portrait aspect for the matching device class
# so the captured PNG looks like a real device viewport, not a
# truncated rectangle.
MOBILE_VIEWPORTS: list[tuple[int, int, str]] = [
    (320, 568, "iPhone SE 1st gen"),
    (360, 640, "Android baseline"),
    (375, 667, "iPhone SE 2/3 / 12 mini"),
    (414, 736, "iPhone Plus / Pro Max"),
]

# JS injected into the shell to force the §3-F update state so
# the §11.6.9 mutual-exclusion winner (Refresh button visible)
# is captured at every width. Bypasses install.js's actual SW
# polling — the audit cares about LAYOUT, not about reproducing
# a real SW update event in headless Chromium.
FORCE_UPDATE_STATE_JS = """
const root = document.getElementById('footer-install');
if (root) {
    root.classList.remove('is-unsupported', 'is-available',
                          'is-ready', 'is-installed');
    root.classList.add('is-update');
    const label = root.querySelector('.footer-install-state');
    if (label) {
        label.textContent = 'Update available.';
        label.removeAttribute('role');
        label.removeAttribute('tabindex');
        label.style.cursor = '';
    }
    const hint = root.querySelector('.footer-install-hint');
    if (hint) {
        hint.hidden = true;
        hint.textContent = '';
    }
    const dismiss = root.querySelector('.footer-install-dismiss');
    if (dismiss) { dismiss.hidden = true; }
    const refresh = root.querySelector('.footer-install-refresh');
    if (refresh) { refresh.hidden = false; }
}
"""


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _start_server(
    workdir: Path, port: int
) -> http.server.ThreadingHTTPServer:
    """Mirror of ui_13_capture._start_server — auth ENABLED with
    ephemeral creds inside the supplied workdir. Pinned to
    127.0.0.1 + the exact origin Playwright will hit so the
    Origin / Referer middleware accepts the form POST."""
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
        target=server.serve_forever,
        daemon=True,
        name="karasu-ui-14-mobile",
    ).start()
    return server


def _login(page, base: str) -> None:
    """Drive the login form so the context picks up a session
    cookie. The form-urlencoded path is the JS-disabled
    contract per UI-13 §3-E (server returns 200 + index.html
    on success); using it keeps the script independent of the
    inline fetch flow."""
    page.goto(base + "/", wait_until="networkidle")
    page.fill("#username", "dev")
    page.fill("#password", "dev")
    page.evaluate(
        """
        const f = document.getElementById('login-form');
        f.removeAttribute('id');
        f.submit();
        """
    )
    page.wait_for_load_state("networkidle")


def _capture(port: int) -> None:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{port}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # --- pre-auth (login) at all four widths ---
            for idx, (w, h, label) in enumerate(MOBILE_VIEWPORTS):
                ctx = browser.new_context(viewport={"width": w, "height": h})
                try:
                    page = ctx.new_page()
                    page.goto(base + "/", wait_until="networkidle")
                    out = OUT_DIR / f"{idx:02d}-login-{w}.png"
                    page.screenshot(path=str(out), full_page=False)
                    print(f"  wrote {out.name} ({label})")
                finally:
                    ctx.close()

            # --- post-auth shell, default state ---
            for offset, (w, h, label) in enumerate(MOBILE_VIEWPORTS):
                idx = 4 + offset
                ctx = browser.new_context(viewport={"width": w, "height": h})
                try:
                    page = ctx.new_page()
                    _login(page, base)
                    # Settle window so install.js renders the
                    # footer-install slot at its decided state
                    # (likely "unsupported" in headless without
                    # beforeinstallprompt — that is the audit
                    # default).
                    page.wait_for_timeout(800)
                    out = OUT_DIR / f"{idx:02d}-shell-default-{w}.png"
                    page.screenshot(path=str(out), full_page=False)
                    print(f"  wrote {out.name} ({label})")
                finally:
                    ctx.close()

            # --- post-auth shell, forced update state ---
            for offset, (w, h, label) in enumerate(MOBILE_VIEWPORTS):
                idx = 8 + offset
                ctx = browser.new_context(viewport={"width": w, "height": h})
                try:
                    page = ctx.new_page()
                    _login(page, base)
                    page.wait_for_timeout(400)
                    page.evaluate(FORCE_UPDATE_STATE_JS)
                    page.wait_for_timeout(200)
                    out = OUT_DIR / f"{idx:02d}-shell-update-{w}.png"
                    page.screenshot(path=str(out), full_page=False)
                    print(f"  wrote {out.name} ({label})")
                finally:
                    ctx.close()
        finally:
            browser.close()


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="karasu-ui-14-mobile-"))
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
    print(f"UI-14 mobile captures landed under {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
