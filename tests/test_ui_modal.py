"""Playwright regression for UI-10 modal cancel + confirm paths.

Brief §7.7 (audit cadence escalated for write paths):

  > Confirmation-flow regression test: a Playwright test that
  > exercises the click → modal → cancel path AND the click →
  > modal → confirm → POST path, asserting that cancel does NOT
  > mutate the bus.

The HTTP shape locks in tests/test_ui_server_http.py already pin
the wire contract on the server side. This module covers the
client side: the modal really opens on a click, Cancel really
closes WITHOUT issuing a POST, and Confirm really fires the POST
and refreshes the drawer.

Skipped silently when Playwright is not installed so the rest of
the suite stays green for contributors who skip the optional
browser dependency. The screenshot capture flow already requires
Playwright, so anyone running the audit pipeline pays the install
cost once.
"""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from karasu.ui import server as ui_server

playwright = pytest.importorskip("playwright.sync_api")


# ---------------------------------------------------------------------------
# Server lifecycle helper — the same pattern as test_ui_server_http.py but
# launched here so the modal test process has its own server (Playwright's
# browser launches are slow; not worth the cross-module fixture share).
# ---------------------------------------------------------------------------


@pytest.fixture
def modal_http(tmp_path: Path) -> Iterator[tuple[str, int, Path, Path]]:
    original_event_log = ui_server.EVENT_LOG
    original_scars_path = ui_server.SCARS_PATH
    bus = tmp_path / "events.jsonl"
    scars_dir = tmp_path / "scars"
    ui_server.configure(event_log=bus, scars_path=scars_dir)
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.UIHandler)
    thread = threading.Thread(
        target=server.serve_forever, name="karasu-ui-modal-test", daemon=True
    )
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield host, port, bus, scars_dir
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        ui_server.configure(
            event_log=original_event_log,
            scars_path=original_scars_path,
        )


def _seed_bus_and_scars(bus: Path, scars_dir: Path) -> str:
    """Seed: one human_decision event on the bus + one scar in
    ScarEngine. Returns the seeded scar id so the test can assert
    on its disappearance after revoke."""
    bus.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "id": "modal-test-001",
        "timestamp": "2026-05-05T12:00:00Z",
        "type": "human_decision",
        "source": "interface",
        "data": {"user": 1, "text": "/scar prio=high *.py"},
        "dispatch": {},
        "response": {},
    }
    bus.write_text(json.dumps(event) + "\n", encoding="utf-8")

    scars_dir.mkdir(parents=True, exist_ok=True)
    scar_id = "modal-test-scar-001"
    scar = {
        "id": scar_id,
        "trigger": {"classification": "code_change", "path": "*.py"},
        "correction": {"priority": "high"},
        "source_event": None,
        "created": "2026-05-05T11:55:00.000+00:00",
    }
    (scars_dir / "scars.jsonl").write_text(
        json.dumps(scar) + "\n", encoding="utf-8"
    )
    return scar_id


def _bus_lines(bus: Path) -> list[str]:
    if not bus.exists():
        return []
    return [
        line for line in bus.read_text(encoding="utf-8").splitlines() if line
    ]


def test_cancel_path_does_not_mutate_bus(
    modal_http: tuple[str, int, Path, Path],
) -> None:
    """Click → modal → Cancel: modal closes; the bus has the
    same number of lines as before; the scar is still active.
    Brief §7.7 binding."""
    host, port, bus, scars_dir = modal_http
    scar_id = _seed_bus_and_scars(bus, scars_dir)
    initial_lines = _bus_lines(bus)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"http://{host}:{port}/")
            page.wait_for_load_state("networkidle")
            # Wait for the timeline to render the seeded event.
            page.wait_for_selector(".event-row", timeout=5000)
            # Click the row → drawer opens, scars section fetches.
            page.locator(".event-row").first.click()
            page.wait_for_selector(
                "#drawer-scars-list .drawer-scar-revoke", timeout=5000
            )
            # Click the inline Revoke button in the drawer →
            # modal opens.
            page.locator(
                "#drawer-scars-list .drawer-scar-revoke"
            ).first.click()
            page.locator("#revoke-modal").wait_for(
                state="visible", timeout=2000
            )
            # Cancel.
            page.locator("#modal-cancel").click()
            # Modal hidden again.
            page.locator("#revoke-modal").wait_for(
                state="hidden", timeout=2000
            )
            # Drawer still open (pin §11.6.5).
            assert page.locator("#event-drawer.is-open").count() == 1
        finally:
            browser.close()

    after_lines = _bus_lines(bus)
    assert after_lines == initial_lines, (
        "Cancel must NOT append to the bus"
    )
    # Scar still active.
    from karasu.scars import ScarEngine

    engine = ScarEngine(scars_dir)
    assert any(s.id == scar_id for s in engine.all())


def test_confirm_path_posts_and_refreshes_drawer(
    modal_http: tuple[str, int, Path, Path],
) -> None:
    """Click → modal → Revoke: POST fires; modal closes; scar
    is gone from /api/scars; a human_decision event with
    data.action="scar_revoke" lands on the bus."""
    host, port, bus, scars_dir = modal_http
    scar_id = _seed_bus_and_scars(bus, scars_dir)
    initial_lines = _bus_lines(bus)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"http://{host}:{port}/")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(".event-row", timeout=5000)
            page.locator(".event-row").first.click()
            page.wait_for_selector(
                "#drawer-scars-list .drawer-scar-revoke", timeout=5000
            )
            page.locator(
                "#drawer-scars-list .drawer-scar-revoke"
            ).first.click()
            page.locator("#revoke-modal").wait_for(
                state="visible", timeout=2000
            )
            # Type a reason so the bus event carries it.
            page.locator("#modal-reason").fill("not applicable anymore")
            # Confirm.
            page.locator("#modal-revoke").click()
            # Modal hidden again.
            page.locator("#revoke-modal").wait_for(
                state="hidden", timeout=2000
            )
            # Drawer scars section should re-render to show
            # "no active scars" — the just-revoked scar
            # disappeared from /api/scars (the second active
            # was the only one we seeded).
            page.locator("#drawer-scars-empty").wait_for(
                state="visible", timeout=3000
            )
        finally:
            browser.close()

    # Bus has one MORE line: the scar_revoke human_decision.
    after_lines = _bus_lines(bus)
    assert len(after_lines) == len(initial_lines) + 1
    new_event = json.loads(after_lines[-1])
    assert new_event["type"] == "human_decision"
    assert new_event["source"] == "ui"
    assert new_event["data"]["action"] == "scar_revoke"
    assert new_event["data"]["scar_id"] == scar_id
    assert new_event["data"]["reason"] == "not applicable anymore"

    # Scar gone from ScarEngine.
    from karasu.scars import ScarEngine

    engine = ScarEngine(scars_dir)
    assert not any(s.id == scar_id for s in engine.all())


def test_esc_closes_modal_first_then_drawer(
    modal_http: tuple[str, int, Path, Path],
) -> None:
    """Pin §11.6.5: first Esc closes the modal; second Esc
    closes the drawer."""
    host, port, bus, scars_dir = modal_http
    _seed_bus_and_scars(bus, scars_dir)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"http://{host}:{port}/")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(".event-row", timeout=5000)
            page.locator(".event-row").first.click()
            page.wait_for_selector(
                "#drawer-scars-list .drawer-scar-revoke", timeout=5000
            )
            page.locator(
                "#drawer-scars-list .drawer-scar-revoke"
            ).first.click()
            page.locator("#revoke-modal").wait_for(
                state="visible", timeout=2000
            )
            # First Esc → modal closes; drawer stays open.
            page.keyboard.press("Escape")
            page.locator("#revoke-modal").wait_for(
                state="hidden", timeout=2000
            )
            assert page.locator("#event-drawer.is-open").count() == 1
            # Second Esc → drawer closes.
            page.keyboard.press("Escape")
            # Drawer slide-out is 240ms; allow one settle.
            page.wait_for_timeout(400)
            assert page.locator("#event-drawer.is-open").count() == 0
        finally:
            browser.close()


def test_modal_backdrop_click_closes_only_modal(
    modal_http: tuple[str, int, Path, Path],
) -> None:
    """Pin §11.6.5: click outside the modal (backdrop click)
    closes ONLY the modal — drawer stays open."""
    host, port, bus, scars_dir = modal_http
    _seed_bus_and_scars(bus, scars_dir)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"http://{host}:{port}/")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(".event-row", timeout=5000)
            page.locator(".event-row").first.click()
            page.wait_for_selector(
                "#drawer-scars-list .drawer-scar-revoke", timeout=5000
            )
            page.locator(
                "#drawer-scars-list .drawer-scar-revoke"
            ).first.click()
            page.locator("#revoke-modal").wait_for(
                state="visible", timeout=2000
            )
            # Click the modal backdrop. Synthesise the click via
            # JS dispatch because Playwright's element click on
            # the backdrop would aim at the centre of the
            # viewport — where the modal is — and hit the modal
            # box instead. The handler is wired directly to the
            # backdrop click event.
            page.evaluate(
                "document.getElementById('modal-backdrop').click()"
            )
            page.locator("#revoke-modal").wait_for(
                state="hidden", timeout=2000
            )
            assert page.locator("#event-drawer.is-open").count() == 1
        finally:
            browser.close()
