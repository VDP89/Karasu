from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

EVENT_LOG = Path(".karasu/events.jsonl")
STATIC_DIR = Path(__file__).parent / "static"


def _read_events(limit: int = 100) -> list[dict[str, Any]]:
    if not EVENT_LOG.exists():
        return []

    lines = EVENT_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    events = []

    for line in lines:
        try:
            raw = json.loads(line)
            events.append(
                {
                    "id": raw.get("id"),
                    "timestamp": raw.get("timestamp"),
                    "type": raw.get("type"),
                    "source": raw.get("source"),
                    "path": raw.get("data", {}).get("path"),
                    "agent": raw.get("dispatch", {}).get("agent"),
                    "requires_human": raw.get("response", {}).get("requires_human"),
                    "success": raw.get("response", {}).get("success"),
                }
            )
        except Exception:
            continue

    return events


def _crow_state(events: list[dict[str, Any]]) -> str:
    state = "idle"

    for ev in reversed(events):
        if ev.get("success") is False:
            return "error"
        if ev.get("requires_human"):
            return "waiting"
        if ev.get("type") == "file_change":
            state = "processing"

    return state


class UIHandler(BaseHTTPRequestHandler):
    def _json(self, data: dict):
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/api/events":
            events = _read_events()
            self._json({"events": events})
            return

        if self.path == "/api/health":
            events = _read_events()
            self._json(
                {
                    "status": "ok",
                    "events": len(events),
                    "crow": _crow_state(events),
                }
            )
            return

        if self.path == "/" or self.path == "/index.html":
            html = (STATIC_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
            return

        self.send_response(404)
        self.end_headers()


def run_ui_server(host: str = "127.0.0.1", port: int = 8787):
    server = ThreadingHTTPServer((host, port), UIHandler)
    print(f"karasu ui → http://{host}:{port}")
    server.serve_forever()
