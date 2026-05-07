"""Dev-only bootstrap for previewing the UI-13 login surface.

Boots ``karasu.ui.server`` with auth ENABLED + an ephemeral
credentials file written to a temp dir, so a browser hitting
``http://127.0.0.1:8787/`` lands on the login screen rendered
by ``static/login.html`` + ``static/css/login.css``.

This script exists for visual verification during UI-13
chunks 5+ (login polish, sw.js cache split, frontend CSRF).
It is NOT a deploy mechanism — chunk 7 ships the proper
``karasu auth set-credentials`` + ``karasu ui --auth`` CLI
surface.

Run from the repo root:

    python scripts/ui_login_preview.py

Then open http://127.0.0.1:8787/ in a browser. Credentials:
    username: dev
    password: dev
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from karasu.ui import server as ui_server  # noqa: E402
from karasu.ui._auth import write_credentials  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="karasu-ui-13-preview-"))
    creds_path = tmp / "auth.json"
    write_credentials(creds_path, username="dev", password="dev")

    ui_server.configure(
        event_log=tmp / "events.jsonl",
        scars_path=tmp / "scars",
        config_path=tmp / "karasu.yaml",
        push_store_path=tmp / "karasu-push.json",
    )
    ui_server.configure_auth(
        credentials_path=creds_path,
        no_auth=False,
        deployed=False,
        trusted_proxies=frozenset({"127.0.0.1", "::1"}),
        expected_origins=(),
    )
    print(
        "karasu ui-13 login preview\n"
        f"  tmpdir : {tmp}\n"
        f"  creds  : {creds_path}\n"
        f"  user   : dev\n"
        f"  pass   : dev\n"
        f"  url    : http://127.0.0.1:8787/\n"
    )
    ui_server.run_ui_server(host="127.0.0.1", port=8787)
    return 0


if __name__ == "__main__":
    sys.exit(main())
