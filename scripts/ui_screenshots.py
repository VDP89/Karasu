"""Capture UI screenshots for audit attachment.

Per UI-0 design brief §7, every UI-N PR MUST ship screenshots
of every state introduced or changed. This script automates
that: it spins up the UI server against a synthetic
``events.jsonl`` with the relevant chunk-4c fields populated,
opens each documented state in a headless browser, and writes
PNGs under ``docs/ui/screenshots/UI-N-<slug>/``.

Usage:
    python scripts/ui_screenshots.py UI-2-tokens

Requires Playwright with Chromium installed locally:
    pip install playwright
    python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import http.server
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_ROOT = REPO_ROOT / "docs" / "ui" / "screenshots"
RECORDINGS_ROOT = REPO_ROOT / "docs" / "ui" / "recordings"

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

# UI-5 — per-state synthetic event corpora.
#
# ``_crow_state`` in ``src/karasu/ui/server.py`` derives the crow's
# display state from the event tail with precedence:
#
#   error      any event with status="failed"
#   waiting    any event with requires_human=True
#   processing the latest event is a file_change
#   idle       otherwise
#
# Each corpus below is built so that the precedence path lands on
# the named state. The four corpora share a small file_change
# baseline so the timeline stays populated (the audit needs to
# see the editorial shell behind the crow, not an empty surface).
def _ui5_event(idx: int, **overrides):
    """Build a UI-5 synthetic event with sensible defaults."""
    base = {
        "id": f"ui5-{idx:03d}",
        "timestamp": f"2026-05-03T11:00:{idx:02d}Z",
        "type": "file_change",
        "source": "watcher",
        "data": {
            "path": "src/karasu/example.py",
            "change_type": "modified",
            "classification": "code_change",
            "priority": "normal",
        },
        "dispatch": {},
        "response": {},
    }
    base.update(overrides)
    return base


_BASELINE = [
    _ui5_event(1),
    _ui5_event(
        2,
        type="agent_response",
        source="adapter",
        data={
            "correlates": "ui5-001",
            "path": "src/karasu/example.py",
            "priority": "normal",
        },
        dispatch={
            "agent": "claude_code",
            "status": "completed",
            "trust_level": 1,
        },
        response={"content": "ok", "requires_human": False},
    ),
]

# UI-6 — flight_route corpora.
#
# ``_flight_route`` projects the LATEST event into a (source, target)
# pair on /api/health.flight. Each corpus below crafts a tail whose
# latest event lands on a specific flight pair, with the previous
# events kept short and incidental so the timeline beside the map
# stays readable in the audit PNG.
def _ui6_event(idx: int, **overrides):
    base = {
        "id": f"ui6-{idx:03d}",
        "timestamp": f"2026-05-04T12:00:{idx:02d}Z",
        "type": "file_change",
        "source": "watcher",
        "data": {
            "path": "src/karasu/example.py",
            "change_type": "modified",
            "classification": "code_change",
            "priority": "normal",
        },
        "dispatch": {},
        "response": {},
    }
    base.update(overrides)
    return base


# Lightweight tail prefix shared across the per-flight corpora so
# the timeline panel beside the map is not empty during the
# capture. The latest event in each corpus determines the flight.
_UI6_PREFIX = [
    _ui6_event(1),
    _ui6_event(
        2,
        type="agent_response",
        source="adapter",
        data={
            "correlates": "ui6-001",
            "path": "src/karasu/example.py",
            "priority": "normal",
        },
        dispatch={
            "agent": "claude_code",
            "status": "completed",
            "trust_level": 1,
        },
        response={"content": "ok", "requires_human": False},
    ),
]


FLIGHT_CORPORA: dict[str, list[dict]] = {
    # latest = file_change watcher → user → karasu
    "flight-user-karasu": _UI6_PREFIX
    + [_ui6_event(3, timestamp="2026-05-04T12:01:00Z")],
    # latest = file_change with pending dispatch to claude_code →
    # karasu → claude
    "flight-karasu-claude": _UI6_PREFIX
    + [
        _ui6_event(
            4,
            timestamp="2026-05-04T12:01:05Z",
            dispatch={
                "agent": "claude_code",
                "status": "pending",
                "trust_level": 1,
            },
        ),
    ],
    # latest = agent_response from claude → claude → karasu
    "flight-claude-karasu": _UI6_PREFIX
    + [
        _ui6_event(
            5,
            timestamp="2026-05-04T12:01:10Z",
            type="agent_response",
            source="adapter",
            data={
                "correlates": "ui6-001",
                "path": "src/karasu/example.py",
                "priority": "normal",
            },
            dispatch={
                "agent": "claude_code",
                "status": "completed",
                "trust_level": 1,
            },
            response={"content": "ok", "requires_human": False},
        ),
    ],
    # latest = github_webhook ingress → github → karasu
    "flight-github-karasu": _UI6_PREFIX
    + [
        _ui6_event(
            6,
            timestamp="2026-05-04T12:01:15Z",
            source="github_webhook",
            data={
                "path": "src/karasu/example.py",
                "change_type": "review_comment",
                "classification": "code_change",
                "priority": "high",
                "github_event": "pull_request_review_comment",
                "github_action": "created",
                "github_pr": 42,
                "github_repo": "VDP89/Karasu-",
                "github_author": "reviewer1",
            },
        ),
    ],
    # latest = controller_resubmit → user → karasu (operator scar)
    "flight-controller-resubmit": _UI6_PREFIX
    + [
        _ui6_event(
            7,
            timestamp="2026-05-04T12:01:20Z",
            source="controller",
            data={
                "path": "src/karasu/example.py",
                "change_type": "modified",
                "classification": "code_change",
                "priority": "high",
                "controller_resubmit": True,
                "resubmit_origin": "ui6-001",
                "controller_chain_depth": 1,
            },
        ),
    ],
    # latest = unknown event type → flight is None (crow parked).
    "flight-parked": _UI6_PREFIX
    + [
        _ui6_event(
            8,
            timestamp="2026-05-04T12:01:25Z",
            type="future_event_type",
        ),
    ],
}


# UI-10 — operator surface needs a human_decision event for the
# drawer to render the revoke section, plus at least one active
# scar in ScarEngine so the section reads as actionable. The
# corpus pairs a /scar audit record on the bus with an
# already-recorded scar so the drawer + the modal both have
# something to show.
UI10_HUMAN_DECISION = {
    "id": "ui10-hd-001",
    "timestamp": "2026-05-05T11:00:30Z",
    "type": "human_decision",
    "source": "interface",
    "data": {
        "user": 12345,
        "text": "/scar prio=high *.py",
    },
    "dispatch": {},
    "response": {},
}

UI10_FILE_CHANGE = {
    "id": "ui10-fc-001",
    "timestamp": "2026-05-05T11:00:00Z",
    "type": "file_change",
    "source": "watcher",
    "data": {
        "path": "src/karasu/example.py",
        "change_type": "modified",
        "classification": "code_change",
        "priority": "normal",
    },
    "dispatch": {},
    "response": {},
}

UI10_EVENTS = [UI10_FILE_CHANGE, UI10_HUMAN_DECISION]

UI10_SCARS = [
    {
        "id": "ui10-scar-001",
        "trigger": {"classification": "code_change", "path": "*.py"},
        "correction": {"priority": "high"},
        "source_event": "ui10-fc-001",
        "created": "2026-05-05T10:55:00.000+00:00",
    },
    {
        "id": "ui10-scar-002",
        "trigger": {"classification": "code_change", "path": "tests/*"},
        "correction": {"priority": "low"},
        "source_event": None,
        "created": "2026-05-05T10:58:00.000+00:00",
    },
]

UI11A_AGENT_RESPONSE = {
    "id": "ui11a-ar-001",
    "timestamp": "2026-05-05T15:15:00Z",
    "type": "agent_response",
    "source": "adapter",
    "data": {
        "correlates": "ui11a-fc-001",
        "path": "src/karasu/ui/server.py",
        "classification": "implementation",
        "priority": "normal",
    },
    "dispatch": {
        "agent": "claude_code",
        "status": "completed",
        "trust_level": 2,
    },
    "response": {
        "content": "UI-11a trust display is ready for review.",
        "requires_human": False,
    },
}

UI11A_EVENTS = [
    {
        "id": "ui11a-fc-001",
        "timestamp": "2026-05-05T15:14:30Z",
        "type": "file_change",
        "source": "watcher",
        "data": {
            "path": "src/karasu/ui/server.py",
            "classification": "implementation",
            "priority": "normal",
        },
        "dispatch": {
            "agent": "claude_code",
            "status": "dispatched",
            "trust_level": 2,
        },
        "response": {},
    },
    UI11A_AGENT_RESPONSE,
]

UI11B_AGENT_RESPONSE = {
    "id": "ui11b-ar-001",
    "timestamp": "2026-05-05T16:15:00Z",
    "type": "agent_response",
    "source": "adapter",
    "data": {
        "correlates": "ui11b-fc-001",
        "path": "src/karasu/ui/server.py",
        "classification": "implementation",
        "priority": "normal",
    },
    "dispatch": {
        "agent": "claude_code",
        "status": "completed",
        "trust_level": 1,
    },
    "response": {
        "content": "Trust adjust write path is ready for review.",
        "requires_human": False,
    },
}

UI11B_EVENTS = [
    {
        "id": "ui11b-fc-001",
        "timestamp": "2026-05-05T16:14:30Z",
        "type": "file_change",
        "source": "watcher",
        "data": {
            "path": "src/karasu/ui/server.py",
            "classification": "implementation",
            "priority": "normal",
        },
        "dispatch": {
            "agent": "claude_code",
            "status": "dispatched",
            "trust_level": 1,
        },
        "response": {},
    },
    UI11B_AGENT_RESPONSE,
]

UI11B_CONFIG = {
    "agents": {
        "claude_code": {
            "trust_level": 1,
            "handles": ["implementation"],
        }
    }
}


STATE_CORPORA: dict[str, list[dict]] = {
    "idle": _BASELINE,
    "processing": _BASELINE
    + [
        _ui5_event(3, timestamp="2026-05-03T11:00:10Z"),
    ],
    "waiting": _BASELINE
    + [
        _ui5_event(
            4,
            timestamp="2026-05-03T11:00:15Z",
            type="agent_response",
            source="adapter",
            data={
                "correlates": "ui5-001",
                "path": "src/karasu/example.py",
                "priority": "normal",
            },
            dispatch={
                "agent": "claude_code",
                "status": "completed",
                "trust_level": 1,
            },
            response={
                "content": "I need a human decision before continuing.",
                "requires_human": True,
            },
        ),
    ],
    "error": _BASELINE
    + [
        _ui5_event(
            5,
            timestamp="2026-05-03T11:00:20Z",
            type="agent_response",
            source="adapter",
            data={
                "correlates": "ui5-001",
                "path": "src/karasu/example.py",
                "priority": "normal",
            },
            dispatch={
                "agent": "claude_code",
                "status": "failed",
                "trust_level": 1,
            },
            response={"content": "adapter error", "requires_human": False},
        ),
    ],
}

# Capture plan per slug. Each entry is a sequence of screenshots
# to take. Optional steps:
#   ``seed``        — true (default) seeds the synthetic 4-event
#                     bus before navigating; false truncates the
#                     bus file so the page renders the empty state
#                     (UI-3 entry condition).
#   ``seed_events`` — name of a STATE_CORPORA entry. Overrides
#                     the default 4-event corpus with a state-
#                     specific one whose tail wins the
#                     ``_crow_state`` precedence path. UI-5
#                     uses this so each crow PNG seeds the
#                     event the crow's display state derives
#                     from. Implies ``seed=True``.
#   ``viewport``    — {"width": W, "height": H} overrides the
#                     default 1440x900 for that single capture.
#   ``scroll_to``   — bring a section into view via locator.
#   ``focus``       — put keyboard focus on a selector for
#                     :focus-visible.
#   ``hover``       — trigger a mouse-over state.
#   ``wait_ms``     — sleep inside the page (used for animation
#                     mid-frames or to let setInterval poll once).
#   ``eval_js``     — string of JavaScript run via page.evaluate
#                     after the seed/wait/etc. steps. UI-5 uses
#                     this on the error PNG to freeze the shake
#                     keyframe at its leftmost extreme so the
#                     posed still is deterministic; the moving
#                     truth lives in the .webm.
CAPTURES: dict[str, list[dict]] = {
    "UI-1-rebase": [
        {"name": "00-index-default.png", "url": "/", "full_page": True},
    ],
    "UI-2-tokens": [
        {
            "name": "00-design-system-default.png",
            "url": "/design-system",
            "full_page": True,
        },
        {
            "name": "01-design-system-focus.png",
            "url": "/design-system",
            "scroll_to": "#focus",
            "focus": ".focus-button.primary",
            "wait_ms": 200,
            "full_page": False,
        },
        {
            "name": "02-design-system-motion.png",
            "url": "/design-system",
            "scroll_to": "#motion",
            "hover": ".motion-row:nth-of-type(3)",
            "wait_ms": 100,
            "full_page": False,
        },
        {
            "name": "03-index-with-tokens.png",
            "url": "/",
            "full_page": False,
        },
    ],
    "UI-3-shell": [
        {
            "name": "00-shell-empty-state.png",
            "url": "/",
            "seed": False,
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            "name": "01-shell-with-events.png",
            "url": "/",
            "seed": True,
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            "name": "02-shell-narrow-viewport.png",
            "url": "/",
            "seed": True,
            "viewport": {"width": 720, "height": 1024},
            "wait_ms": 3500,
            "full_page": True,
        },
    ],
    "UI-4-timeline": [
        {
            "name": "00-timeline-default.png",
            "url": "/",
            "seed": True,
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            "name": "01-timeline-hover.png",
            "url": "/",
            "seed": True,
            "wait_ms": 3500,
            "hover": ".event-row:first-child",
            "full_page": False,
        },
        {
            "name": "02-timeline-focus.png",
            "url": "/",
            "seed": True,
            "wait_ms": 3500,
            "press_tab": 1,
            "full_page": False,
        },
        {
            "name": "03-timeline-narrow-viewport.png",
            "url": "/",
            "seed": True,
            "viewport": {"width": 720, "height": 1024},
            "wait_ms": 3500,
            "full_page": True,
        },
    ],
    "UI-5-crow": [
        {
            "name": "00-crow-idle.png",
            "url": "/",
            "seed_events": "idle",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            "name": "01-crow-processing.png",
            "url": "/",
            "seed_events": "processing",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            "name": "02-crow-waiting.png",
            "url": "/",
            "seed_events": "waiting",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # Frozen-frame intentional. The error keyframe is a
            # 240ms one-shot beat (no loop) and capturing it mid-
            # animation is non-deterministic. We seed the error
            # bus, let the surface settle into the .error class
            # via the regular polling tick, then pin the transform
            # to the keyframe's 25 % position (translateX -2 px,
            # the leftmost shake) so the posed still shows the
            # beat's visible signature. The moving truth lives
            # in UI-5-crow.webm. The screenshots README explains
            # this contract for the auditor.
            "name": "03-crow-error.png",
            "url": "/",
            "seed_events": "error",
            "wait_ms": 3500,
            "eval_js": (
                "const g = document.getElementById('crow-glyph');"
                "g.style.animation = 'none';"
                "g.style.transform = 'translateX(-2px)';"
            ),
            "full_page": False,
        },
        {
            # The hero crow on the empty state — same path data
            # as the header glyph at 96 px, breathing the ambient
            # 4 s loop. Demonstrates the canonical asset at its
            # largest documented display size.
            "name": "04-empty-state-with-canonical-crow.png",
            "url": "/",
            "seed": False,
            "wait_ms": 3500,
            "full_page": False,
        },
    ],
    # UI-6 — Live Map captures.
    #
    # Each PNG seeds a flight corpus whose latest event lands the
    # /api/health.flight projection on a specific (source, target)
    # pair, then waits long enough for the polling tick to fetch
    # /api/health and the JS to apply the transition. The wide
    # viewport (1440x900) shows the side-by-side map+timeline
    # layout per the operator's UI-6 layout decision (>= 1280 px:
    # split; < 1280 px: stacked).
    "UI-6-livemap": [
        {
            # Empty state stays the first impression — the map
            # only appears once events populate the projection
            # (UI-3 / UI-5 contract carried into UI-6).
            "name": "00-empty-state-no-map.png",
            "url": "/",
            "seed": False,
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # Latest event is a watcher file_change → user → karasu.
            # The crow flies into the watchtower from the user
            # node on the left edge.
            "name": "01-flight-user-to-karasu.png",
            "url": "/",
            "seed_events": "flight-user-karasu",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # Latest event is a file_change with a router-assigned
            # claude_code dispatch in flight → karasu → claude.
            # The map narrates the outbound leg the timeline
            # cannot read on its own.
            "name": "02-flight-karasu-to-claude.png",
            "url": "/",
            "seed_events": "flight-karasu-claude",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # Latest event is an agent_response from claude →
            # claude → karasu. Inbound leg, the response landed.
            "name": "03-flight-claude-to-karasu.png",
            "url": "/",
            "seed_events": "flight-claude-karasu",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # Latest event is a github_webhook ingress →
            # github → karasu.
            "name": "04-flight-github-to-karasu.png",
            "url": "/",
            "seed_events": "flight-github-karasu",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # Latest event is a controller_resubmit (operator
            # scar) → user → karasu. Same destination pair as
            # the watcher file_change, but the auditor reads the
            # timeline beside it to confirm the controller_resubmit
            # marker; the map stays semantically right.
            "name": "05-flight-controller-resubmit.png",
            "url": "/",
            "seed_events": "flight-controller-resubmit",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # Latest event has no mapped flight pair → projection
            # returns null; the crow parks (hidden) and the map
            # nodes return to their resting --fg-2 colour.
            "name": "06-flight-parked.png",
            "url": "/",
            "seed_events": "flight-parked",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # Narrow viewport collapses the side-by-side layout
            # to stacked (map on top, timeline below). The map's
            # aspect-ratio recovers to 4/3 to keep nodes readable
            # at narrow widths.
            "name": "07-livemap-narrow-viewport.png",
            "url": "/",
            "seed_events": "flight-claude-karasu",
            "viewport": {"width": 720, "height": 1280},
            "wait_ms": 3500,
            "full_page": True,
        },
    ],
    # UI-11a — trust gradient read display.
    #
    # Opens the existing drawer on an agent_response event and
    # verifies the read-only trust_level row is visible. No modal,
    # no Adjust button, no POST path in this chunk.
    "UI-11a-trust-display": [
        {
            "name": "00-drawer-trust-visible.png",
            "url": "/",
            "seed_events": UI11A_EVENTS,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 500,
            "full_page": False,
        },
    ],
    # UI-11b - trust gradient write affordance.
    #
    # Drawer-earned only: every PNG opens from a concrete
    # agent_response row. The modal copy and post-confirm drawer
    # annotation both state that the change is recorded intent for
    # the next watcher run, not live adapter mutation.
    "UI-11b-trust-write": [
        {
            "name": "00-drawer-with-adjust.png",
            "url": "/",
            "seed_events": UI11B_EVENTS,
            "seed_config": UI11B_CONFIG,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 500,
            "full_page": False,
        },
        {
            "name": "01-modal-default.png",
            "url": "/",
            "seed_events": UI11B_EVENTS,
            "seed_config": UI11B_CONFIG,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "eval_js": (
                "document.querySelector("
                "  '#drawer-trust-row .drawer-trust-adjust'"
                ").click()"
            ),
            "post_eval_wait_ms": 400,
            "full_page": False,
        },
        {
            "name": "02-modal-with-reason.png",
            "url": "/",
            "seed_events": UI11B_EVENTS,
            "seed_config": UI11B_CONFIG,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "eval_js": (
                "document.querySelector("
                "  '#drawer-trust-row .drawer-trust-adjust'"
                ").click();"
                "document.querySelector("
                "  'input[name=\"trust-level\"][value=\"2\"]'"
                ").click();"
                "const r = document.getElementById('trust-modal-reason');"
                "r.value = 'dogfood branch';"
                "r.dispatchEvent(new Event('input'));"
            ),
            "post_eval_wait_ms": 400,
            "full_page": False,
        },
        {
            "name": "03-modal-reduced-motion.png",
            "url": "/",
            "seed_events": UI11B_EVENTS,
            "seed_config": UI11B_CONFIG,
            "reduced_motion": True,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "eval_js": (
                "document.querySelector("
                "  '#drawer-trust-row .drawer-trust-adjust'"
                ").click()"
            ),
            "post_eval_wait_ms": 400,
            "full_page": False,
        },
        {
            "name": "04-post-confirm-annotation.png",
            "url": "/",
            "seed_events": UI11B_EVENTS,
            "seed_config": UI11B_CONFIG,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "eval_js": (
                "document.querySelector("
                "  '#drawer-trust-row .drawer-trust-adjust'"
                ").click();"
                "document.querySelector("
                "  'input[name=\"trust-level\"][value=\"2\"]'"
                ").click();"
                "document.getElementById('trust-modal-reason').value = "
                "'dogfood branch';"
                "document.getElementById('trust-modal-confirm').click();"
            ),
            "post_eval_wait_ms": 1400,
            "full_page": False,
        },
    ],
    # UI-10 — scar revoke flow.
    #
    # Drawer is opened against a human_decision event so the
    # .drawer-scars section is visible; ScarEngine is seeded
    # with two active scars so the section reads as actionable.
    # The PNGs walk: drawer with revoke button → modal default
    # → modal with operator-typed reason → modal under
    # prefers-reduced-motion (the chromatic whitelist contract
    # from UI-2 covers it; the audit verifies the PNG) → post-
    # revoke surface (one scar gone, one remaining).
    "UI-10-scar-revoke": [
        {
            # Drawer open on the human_decision event with the
            # revoke section visible. Pin §11.6.1 (revoke lives
            # only inside the existing drawer) — the audit can
            # see both that the section IS in the drawer AND
            # that no toolbar / floating button competes.
            "name": "00-drawer-with-revoke.png",
            "url": "/",
            "seed_events": UI10_EVENTS,
            "seed_scars": UI10_SCARS,
            "wait_ms": 3500,
            # The first .event-row click resolves to the most
            # recent event, which is the human_decision (latest
            # by timestamp).
            "click": ".event-row:first-child",
            "post_click_wait_ms": 500,
            "full_page": False,
        },
        {
            # Modal default state — opened by clicking the first
            # Revoke button in the drawer's scars section. Pin
            # §11.6.2 (modal mandatory; no inline shortcut).
            "name": "01-modal-default.png",
            "url": "/",
            "seed_events": UI10_EVENTS,
            "seed_scars": UI10_SCARS,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "eval_js": (
                "document.querySelector("
                "  '#drawer-scars-list .drawer-scar-revoke'"
                ").click()"
            ),
            "post_eval_wait_ms": 400,
            "full_page": False,
        },
        {
            # Modal with the operator's typed reason — verifies
            # the textarea renders without breaking the layout
            # and that the focus ring sits on the right element.
            "name": "02-modal-with-reason.png",
            "url": "/",
            "seed_events": UI10_EVENTS,
            "seed_scars": UI10_SCARS,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "eval_js": (
                "(() => {"
                "  document.querySelector("
                "    '#drawer-scars-list .drawer-scar-revoke'"
                "  ).click();"
                "  const r = document.getElementById('modal-reason');"
                "  r.value = 'workflow changed; rule no longer applies';"
                "  r.focus();"
                "})()"
            ),
            "post_eval_wait_ms": 400,
            "full_page": False,
        },
        {
            # Modal with prefers-reduced-motion: reduce. The
            # backdrop's opacity transition is NOT on the UI-2
            # chromatic whitelist, so it becomes effectively
            # instant — the modal still appears; the slide-in
            # is suppressed. PNG audit verifies the structural
            # integrity (no flicker, no half-faded backdrop).
            "name": "03-modal-reduced-motion.png",
            "url": "/",
            "seed_events": UI10_EVENTS,
            "seed_scars": UI10_SCARS,
            "reduced_motion": True,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "eval_js": (
                "document.querySelector("
                "  '#drawer-scars-list .drawer-scar-revoke'"
                ").click()"
            ),
            "post_eval_wait_ms": 400,
            "full_page": False,
        },
        {
            # Post-revoke surface — one scar revoked via direct
            # ScarEngine call (mirrors the POST path); drawer
            # re-fetches /api/scars and the section now reads
            # as one-row instead of two. Pin §11.6.4 (operator
            # MUST see the revocation). The PNG verifies the
            # annotation is visible without the operator having
            # to infer it from the timeline.
            "name": "04-post-revoke-surface.png",
            "url": "/",
            "seed_events": UI10_EVENTS,
            # Only the second scar remains active.
            "seed_scars": [UI10_SCARS[1]],
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "full_page": False,
        },
        {
            # Optional hover state on the destructive button.
            # Brief §11 def of done: PNG is encouraged (not
            # blocking) for future regression coverage of the
            # --danger token's hover alias.
            "name": "05-modal-revoke-hover.png",
            "url": "/",
            "seed_events": UI10_EVENTS,
            "seed_scars": UI10_SCARS,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "eval_js": (
                "document.querySelector("
                "  '#drawer-scars-list .drawer-scar-revoke'"
                ").click()"
            ),
            "post_eval_wait_ms": 400,
            # post_eval_hover (NOT pre-eval hover) so the hover
            # targets the modal Revoke button after the modal
            # is open.
            "post_eval_hover": "#modal-revoke",
            "full_page": False,
        },
    ],
    # UI-7 — Detail drawer captures.
    #
    # Opens the drawer via Playwright click() on either a timeline
    # row or a map node, asserts the drawer settled, and screenshots
    # the full shell. Each PNG seeds the same UI-6 corpora so the
    # underlying surface (map + timeline) is the same across the
    # set; only the drawer state varies.
    "UI-7-detail": [
        {
            # Closed state — drawer hidden, shell as UI-6 left it.
            # The audit verifies that with no click yet, nothing on
            # the surface betrays the presence of the drawer
            # markup (no chrome leak, no visible backdrop).
            "name": "00-drawer-closed.png",
            "url": "/",
            "seed_events": "flight-karasu-claude",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # Drawer opened from a timeline row click.
            # The pre-screenshot click() targets the FIRST timeline
            # row (the LATEST event, top of the list) — its body
            # is the file_change with the claude_code dispatch.
            # The drawer header reads "file_change" + the
            # timestamp; the body shows the highlighted JSON
            # projection.
            "name": "01-drawer-from-timeline-row.png",
            "url": "/",
            "seed_events": "flight-karasu-claude",
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "full_page": False,
        },
        {
            # Drawer opened from a map node click.
            # Click target is the claude node (the target of the
            # current flight). The handler resolves to the latest
            # event whose _flight_route pair touches claude — the
            # same file_change as above for this corpus.
            "name": "02-drawer-from-map-node-claude.png",
            "url": "/",
            "seed_events": "flight-karasu-claude",
            "wait_ms": 3500,
            "click": ".map-node[data-node='claude']",
            "post_click_wait_ms": 400,
            "full_page": False,
        },
        {
            # Drawer opened from a node with no traffic yet.
            # Codex node clicked while the corpus only has
            # claude / user events — the resolver returns null
            # and the drawer renders the empty sentence body.
            "name": "03-drawer-empty-node.png",
            "url": "/",
            "seed_events": "flight-claude-karasu",
            "wait_ms": 3500,
            "click": ".map-node[data-node='codex']",
            "post_click_wait_ms": 400,
            "full_page": False,
        },
        {
            # Drawer opened with a github_webhook event payload —
            # exercises the highlighter against a busier projection
            # (github_event, github_pr, github_repo, github_author
            # all populated).
            "name": "04-drawer-github-webhook.png",
            "url": "/",
            "seed_events": "flight-github-karasu",
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "full_page": False,
        },
        {
            # Narrow viewport — the drawer takes 100vw at <= 720px
            # so the operator on a tablet can read the JSON without
            # squinting.
            "name": "05-drawer-narrow-viewport.png",
            "url": "/",
            "seed_events": "flight-karasu-claude",
            "viewport": {"width": 720, "height": 1280},
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 400,
            "full_page": True,
        },
    ],
    # UI-8 — PWA shell + offline page captures.
    #
    # No .webm by design (Codex P2 binding: UI-8 is the first
    # chunk after UI-5 to legitimately skip the recording — the
    # offline page is static, the only motion is the existing
    # crow ambient breathing already covered by UI-5.webm).
    #
    # The "manifest installed" PNG is a normal index.html capture;
    # the manifest itself is metadata the browser exposes on the
    # install prompt, not a visual the operator sees on the page.
    # The PNG verifies that index.html still renders correctly
    # WITH the manifest link + SW registration in place (no
    # regression from UI-7).
    # UI-9 — reduced-motion smoke pass.
    #
    # Each capture forces ``prefers-reduced-motion: reduce`` on
    # the Playwright context (via emulate_media). The chunk
    # verifies that every UI-N visible state stays reachable
    # without motion-derived layout instability — drawer slides
    # become instant, crow ambient breathing pauses, flight
    # transitions snap instead of arc.
    #
    # The PNGs are intentionally NOT pixel-comparable to the
    # default-motion captures (the crow's tilt / hover state
    # may sit at a different keyframe instant); the audit looks
    # at structural integrity and at the absence of motion-
    # derived flicker, not at exact frame parity.
    "UI-9-tests": [
        {
            "name": "00-empty-state-reduced-motion.png",
            "url": "/",
            "seed": False,
            "reduced_motion": True,
            "wait_ms": 1500,
            "full_page": False,
        },
        {
            "name": "01-timeline-reduced-motion.png",
            "url": "/",
            "seed_events": "flight-claude-karasu",
            "reduced_motion": True,
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            "name": "02-livemap-reduced-motion.png",
            "url": "/",
            "seed_events": "flight-karasu-claude",
            "reduced_motion": True,
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            "name": "03-drawer-reduced-motion.png",
            "url": "/",
            "seed_events": "flight-karasu-claude",
            "reduced_motion": True,
            "wait_ms": 3500,
            "click": ".event-row:first-child",
            "post_click_wait_ms": 100,
            "full_page": False,
        },
        {
            "name": "04-offline-reduced-motion.png",
            "url": "/offline.html",
            "seed": False,
            "reduced_motion": True,
            "eval_js": (
                "var p = 'C:/Users/op/.karasu/events.jsonl';"
                "localStorage.setItem('karasu:bus_path', p);"
                "document.getElementById('offline-bus-value')"
                "  .textContent = p;"
            ),
            "wait_ms": 200,
            "full_page": False,
        },
    ],
    "UI-8-pwa": [
        {
            # Index page after the SW + manifest land. Visual
            # surface is identical to UI-7's drawer-closed
            # capture; the audit verifies the additions
            # (manifest link in <head>, theme-color meta, SW
            # registration) do NOT regress the rendered shell.
            "name": "00-index-with-manifest.png",
            "url": "/",
            "seed_events": "flight-karasu-claude",
            "wait_ms": 3500,
            "full_page": False,
        },
        {
            # /offline.html served directly. The route is
            # reachable from the server outside of the SW
            # navigation-fallback path so the auditor can open
            # it during the screenshot pass without faking a
            # network failure. Hero crow in .crow.offline pose
            # (rotate 4 deg + opacity 0.7), single editorial
            # sentence, last-known bus_path muted.
            #
            # localStorage seed runs via eval_js BEFORE goto so
            # the page boots with a populated bus path; without
            # the seed the page would show the em-dash
            # placeholder (the empty-storage default branch).
            # The captured PNG demonstrates the populated
            # branch since that's the more informative state
            # for the auditor.
            "name": "01-offline-page-default.png",
            "url": "/offline.html",
            "seed": False,
            # The offline page reads localStorage in its inline
            # boot script and paints the bus value into the DOM
            # once. To capture the populated branch without an
            # extra reload, we set localStorage AND mutate the
            # rendered text node directly — the resulting PNG
            # matches what a fresh page-load with that storage
            # value would show.
            "eval_js": (
                "var p = 'C:/Users/op/.karasu/events.jsonl';"
                "localStorage.setItem('karasu:bus_path', p);"
                "document.getElementById('offline-bus-value')"
                "  .textContent = p;"
            ),
            "wait_ms": 200,
            "full_page": False,
        },
        {
            # /offline.html with empty localStorage. This is the
            # branch a freshly-installed PWA hits if the bus has
            # never been reached — Codex P1 binding: muted
            # "bus —" placeholder, NEVER undefined / null /
            # fake path. The capture proves the placeholder
            # actually renders.
            "name": "02-offline-page-empty-storage.png",
            "url": "/offline.html",
            "seed": False,
            # Same DOM-mutation pattern as 01: clear localStorage
            # AND set the rendered text to the em-dash placeholder
            # so the PNG honestly shows the empty-storage branch.
            "eval_js": (
                "localStorage.removeItem('karasu:bus_path');"
                "document.getElementById('offline-bus-value')"
                "  .textContent = '—';"
            ),
            "wait_ms": 200,
            "full_page": False,
        },
        {
            # Narrow viewport — the offline shell stays
            # readable on tablet / phone form factors. Same
            # populated-bus-path branch as 01 for consistency.
            "name": "03-offline-narrow-viewport.png",
            "url": "/offline.html",
            "seed": False,
            "viewport": {"width": 720, "height": 1280},
            "eval_js": (
                "var p = 'C:/Users/op/.karasu/events.jsonl';"
                "localStorage.setItem('karasu:bus_path', p);"
                "document.getElementById('offline-bus-value')"
                "  .textContent = p;"
            ),
            "wait_ms": 200,
            "full_page": True,
        },
    ],

    # UI-12a — push notification read display.
    # Three PNGs land in this chunk: ``off`` (supported but
    # unconfigured), ``denied`` (browser-side permission
    # refusal), and ``on`` (supported + at least one
    # subscription in the store). All three override
    # browserPushSupport() because headless Chromium reports
    # Notification.permission === 'denied' by default (no user
    # gesture, no grant_permissions wiring); without the
    # override the ``off`` and ``on`` captures would
    # short-circuit on the denied branch and erase the visual
    # contrast. The override pins each capture to its intended
    # branch regardless of the headless browser default; the
    # production CSS — not the override — is what preserves
    # the §11.6.11 PASSIVE READ-ONLY pin.
    #   "off"     — supported browser, empty store. Override
    #               browserPushSupport() to return 'supported'
    #               so loadPushState() proceeds to fetch
    #               /api/push, sees subscription_count=0, and
    #               renders ``Notifications: off`` in --fg-2.
    #   "denied"  — operator denied the OS-level Notification
    #               permission. Override returns 'denied';
    #               loadPushState() short-circuits before the
    #               fetch and renders ``Notifications: denied``
    #               in --warn.
    #   "on"      — supported browser, populated store. Same
    #               override as ``off`` plus a ``push_seed``
    #               that writes a single throwaway subscription
    #               to the tempdir's push store BEFORE the
    #               capture. /api/push then reports
    #               subscription_count=1 and the JS lands on
    #               the ``is-on`` branch (--accent). The fake
    #               endpoint never leaves the tempdir; the
    #               negative-shape HTTP test in
    #               test_ui_server_http.py guarantees raw
    #               endpoint material does not reach the wire
    #               either way (Codex P2 on PR #98 round 1).
    "UI-12-push": [
        {
            "name": "00-footer-push-off.png",
            "url": "/",
            "seed": False,
            "wait_ms": 800,
            "eval_js": (
                "window.browserPushSupport = function () {"
                "  return 'supported';"
                "};"
                "window.loadPushState();"
            ),
            "post_eval_wait_ms": 200,
            "full_page": False,
        },
        {
            "name": "01-footer-push-denied.png",
            "url": "/",
            "seed": False,
            "wait_ms": 800,
            "eval_js": (
                "window.browserPushSupport = function () {"
                "  return 'denied';"
                "};"
                "window.loadPushState();"
            ),
            "post_eval_wait_ms": 200,
            "full_page": False,
        },
        {
            "name": "02-footer-push-on.png",
            "url": "/",
            "seed": False,
            "wait_ms": 800,
            "push_seed": [
                {
                    "endpoint": (
                        "https://example.test/screenshot-fake-endpoint"
                    ),
                    "endpoint_hash": (
                        "0000000000000000000000000000000000000000"
                        "000000000000000000000000"
                    ),
                    "keys": {
                        "p256dh": "screenshot-fake-p256dh",
                        "auth": "screenshot-fake-auth",
                    },
                    "categories": ["attention", "errors", "corrections"],
                    "created_at": "2026-05-06T00:00:00Z",
                }
            ],
            "eval_js": (
                "window.browserPushSupport = function () {"
                "  return 'supported';"
                "};"
                "window.loadPushState();"
            ),
            "post_eval_wait_ms": 200,
            "full_page": False,
        },
        # UI-12b §7.1 — modal default state. Footer "off" with
        # the modal opened on top: lede + 3 categories
        # pre-checked + foot copy + Cancel | Enable
        # notifications. push_seed=[] writes the store with
        # VAPID + zero subscriptions (the writer's normal
        # bootstrap state, where the operator has manually
        # seeded VAPID per docs/local-dogfood.md but not yet
        # subscribed any browser).
        {
            "name": "03-modal-default.png",
            "url": "/",
            "seed": False,
            "wait_ms": 800,
            "push_seed": [],
            "eval_js": (
                "window.browserPushSupport = function () { return 'supported'; };"
                "(async () => {"
                "  await window.loadPushState();"
                "  await new Promise((r) => setTimeout(r, 100));"
                "  if (typeof window.openPushModal === 'function') {"
                "    window.openPushModal();"
                "  }"
                "})();"
            ),
            "post_eval_wait_ms": 600,
            "full_page": True,
        },
        # UI-12b §7.1 — modal with one category unchecked.
        # Same setup as 03 plus a click on the "errors"
        # checkbox so the post-eval state shows two checked,
        # one unchecked.
        {
            "name": "04-modal-one-unchecked.png",
            "url": "/",
            "seed": False,
            "wait_ms": 800,
            "push_seed": [],
            "eval_js": (
                "window.browserPushSupport = function () { return 'supported'; };"
                "(async () => {"
                "  await window.loadPushState();"
                "  await new Promise((r) => setTimeout(r, 100));"
                "  if (typeof window.openPushModal === 'function') {"
                "    window.openPushModal();"
                "    await new Promise((r) => setTimeout(r, 100));"
                "    const errorsBox = document.querySelector("
                "      'input[name=\"push-category\"][value=\"errors\"]'"
                "    );"
                "    if (errorsBox) errorsBox.checked = false;"
                "  }"
                "})();"
            ),
            "post_eval_wait_ms": 600,
            "full_page": True,
        },
        # UI-12b §7.1 — modal post-subscribe. Push store seeded
        # with one subscription + VAPID; the modal renders the
        # state row ("Subscribed: 1 subscription"), the
        # "Update categories" primary, and the "Unsubscribe
        # this browser" secondary at the foot.
        {
            "name": "05-modal-post-subscribe.png",
            "url": "/",
            "seed": False,
            "wait_ms": 800,
            "push_seed": [
                {
                    "endpoint": (
                        "https://example.test/screenshot-fake-endpoint"
                    ),
                    "endpoint_hash": (
                        "0000000000000000000000000000000000000000"
                        "000000000000000000000000"
                    ),
                    "keys": {
                        "p256dh": "screenshot-fake-p256dh",
                        "auth": "screenshot-fake-auth",
                    },
                    "categories": ["attention", "errors", "corrections"],
                    "created_at": "2026-05-06T00:00:00Z",
                }
            ],
            "eval_js": (
                "window.browserPushSupport = function () { return 'supported'; };"
                "(async () => {"
                "  await window.loadPushState();"
                "  await new Promise((r) => setTimeout(r, 100));"
                "  if (typeof window.openPushModal === 'function') {"
                "    window.openPushModal();"
                "  }"
                "})();"
            ),
            "post_eval_wait_ms": 600,
            "full_page": True,
        },
        # UI-12b §7.1 — modal with reduced-motion media query
        # forced. The modal still opens; the slide-in transition
        # is clamped to instant via reset.css's chromatic
        # whitelist (UI-2 contract). Captures the same modal
        # default state as 03 but with prefers-reduced-motion:
        # reduce so the screenshot proves the contract holds
        # on the modal primitive.
        {
            "name": "06-modal-reduced-motion.png",
            "url": "/",
            "seed": False,
            "wait_ms": 800,
            "reduced_motion": True,
            "push_seed": [],
            "eval_js": (
                "window.browserPushSupport = function () { return 'supported'; };"
                "(async () => {"
                "  await window.loadPushState();"
                "  await new Promise((r) => setTimeout(r, 100));"
                "  if (typeof window.openPushModal === 'function') {"
                "    window.openPushModal();"
                "  }"
                "})();"
            ),
            "post_eval_wait_ms": 600,
            "full_page": True,
        },
    ],
}

# Recording plan per slug. Each entry is a single video capture:
# one Playwright context with ``record_video_dir`` set, walking
# through a sequence of state seeds inside the same page. The
# .webm is renamed post-hoc from Playwright's auto-generated
# filename to ``<slug>.webm`` under ``RECORDINGS_ROOT``.
#
# UI-5 uses a 1024x640 viewport to keep the raw VP8/VP9 output
# under the 500 KB cap without depending on ffmpeg. The frame
# sequence covers all four states plus a recovery beat; total
# wall time ~5 s.
#
# Each frame entry mirrors the screenshot step vocabulary
# (``seed_events``, ``wait_ms``, ``eval_js``); ``_record_video``
# applies them in order between the page.goto and the context
# close.
RECORDINGS: dict[str, dict] = {
    "UI-5-crow": {
        "viewport": {"width": 1024, "height": 640},
        "url": "/",
        "frames": [
            {"seed_events": "idle", "wait_ms": 800},
            {"seed_events": "processing", "wait_ms": 1000},
            {"seed_events": "waiting", "wait_ms": 1000},
            {"seed_events": "error", "wait_ms": 1000},
            {"seed_events": "idle", "wait_ms": 800},
        ],
    },
    # UI-6 — Live Map .webm.
    #
    # Walks the dispatch chain so the auditor sees multiple flights
    # in one recording: file_change watcher → router-assigned to
    # claude → response from claude → github webhook ingress →
    # human_decision (rendered via the controller-resubmit corpus,
    # same user→karasu pair) → empty (parked).
    #
    # Viewport is 1024x640 — full-shell context per Codex pin #5
    # (the auditor must confirm the SHELL stays still from a single
    # frame, not see a cropped close-up of the flying crow).
    #
    # Per-frame wait is 1000 ms so each 600 ms ease-mag transition
    # finishes inside the frame and the next seed lands on a settled
    # surface; total wall time ~6 s.
    "UI-6-livemap": {
        "viewport": {"width": 1024, "height": 640},
        "url": "/",
        "frames": [
            {"seed_events": "flight-user-karasu", "wait_ms": 1000},
            {"seed_events": "flight-karasu-claude", "wait_ms": 1000},
            {"seed_events": "flight-claude-karasu", "wait_ms": 1000},
            {"seed_events": "flight-github-karasu", "wait_ms": 1000},
            {"seed_events": "flight-controller-resubmit", "wait_ms": 1000},
            {"seed_events": "flight-parked", "wait_ms": 800},
        ],
    },
    # UI-7 — Detail drawer .webm.
    #
    # Walks the open / switch / close sequence inside ONE
    # Playwright context: open from timeline row → switch to
    # opening from a map node → close (Esc / X). Full-shell
    # 1024×640 per Codex pin #5; the auditor must see that the
    # SHELL stays still while only the drawer slides.
    #
    # 1024 px is below the 1280 px split breakpoint, so the
    # timeline renders stacked under the map in this recording —
    # which is fine: the drawer slide is the audit focus and
    # both layouts trigger the same drawer.
    # UI-10 — full revoke flow: drawer open, modal open, modal
    # confirm, drawer re-renders the scars list. Pin §11.6.6
    # (audit gate on .webm: must read as deliberate ScarEngine
    # action, not settings-panel management). 1024x640 viewport
    # per pin #5 from UI-3 audit (full-shell context).
    "UI-10-scar-revoke": {
        "viewport": {"width": 1024, "height": 640},
        "url": "/",
        "frames": [
            # Boot: human_decision event on bus, two active
            # scars. Drawer closed.
            {
                "seed_events": UI10_EVENTS,
                "seed_scars": UI10_SCARS,
                "wait_ms": 1200,
            },
            # Click the timeline row → drawer opens with the
            # human_decision detail + the active-scars section.
            {
                "eval_js": (
                    "document.querySelector('.event-row').click()"
                ),
                "wait_ms": 900,
            },
            # Click the first scar's Revoke button → modal opens.
            {
                "eval_js": (
                    "document.querySelector("
                    "  '#drawer-scars-list .drawer-scar-revoke'"
                    ").click()"
                ),
                "wait_ms": 900,
            },
            # Type a reason so the textarea is part of the
            # operator-feel verification.
            {
                "eval_js": (
                    "(() => {"
                    "  const r = document.getElementById('modal-reason');"
                    "  r.value = 'workflow changed';"
                    "  r.dispatchEvent(new Event('input'));"
                    "})()"
                ),
                "wait_ms": 600,
            },
            # Click Revoke → POST /api/scars/{id}/revoke fires;
            # modal closes; drawer re-fetches /api/scars (the
            # revoked scar disappears from the list); the
            # human_decision event the bus emitted lands on
            # /api/events by the next tick.
            {
                "eval_js": (
                    "document.getElementById('modal-revoke').click()"
                ),
                "wait_ms": 1500,
            },
            # Settle frame so the operator sees the post-revoke
            # state for a beat before the recording cuts.
            {"wait_ms": 800},
        ],
    },
    "UI-11b-trust-write": {
        "viewport": {"width": 1024, "height": 640},
        "url": "/",
        "frames": [
            {
                "seed_events": UI11B_EVENTS,
                "seed_config": UI11B_CONFIG,
                "wait_ms": 1200,
            },
            {
                "eval_js": "document.querySelector('.event-row').click()",
                "wait_ms": 900,
            },
            {
                "eval_js": (
                    "document.querySelector("
                    "  '#drawer-trust-row .drawer-trust-adjust'"
                    ").click()"
                ),
                "wait_ms": 900,
            },
            {
                "eval_js": (
                    "document.querySelector("
                    "  'input[name=\"trust-level\"][value=\"2\"]'"
                    ").click();"
                    "const r = document.getElementById('trust-modal-reason');"
                    "r.value = 'dogfood branch';"
                    "r.dispatchEvent(new Event('input'));"
                ),
                "wait_ms": 600,
            },
            {
                "eval_js": (
                    "document.getElementById('trust-modal-confirm').click()"
                ),
                "wait_ms": 1500,
            },
            {"wait_ms": 800},
        ],
    },
    "UI-7-detail": {
        "viewport": {"width": 1024, "height": 640},
        "url": "/",
        "frames": [
            # Boot frame: corpus seeded, drawer closed.
            {"seed_events": "flight-karasu-claude", "wait_ms": 800},
            # Open from a timeline row click.
            {
                "eval_js": "document.querySelector('.event-row').click()",
                "wait_ms": 700,
            },
            # Close via Esc.
            {
                "eval_js": (
                    "document.dispatchEvent("
                    "  new KeyboardEvent('keydown', {key: 'Escape'})"
                    ");"
                ),
                "wait_ms": 500,
            },
            # Open from a map-node click (claude).
            {
                "eval_js": (
                    "document.querySelector("
                    "  '.map-node[data-node=\"claude\"]'"
                    ").dispatchEvent(new MouseEvent('click', "
                    "  {bubbles: true}));"
                ),
                "wait_ms": 700,
            },
            # Close via backdrop click.
            {
                "eval_js": "document.getElementById('drawer-backdrop').click()",
                "wait_ms": 500,
            },
        ],
    },
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(workdir: Path, port: int) -> http.server.ThreadingHTTPServer:
    """Start the UI server reading ``workdir/.karasu/events.jsonl``.

    Uses ``ui_server.configure`` to point EVENT_LOG and SCARS_PATH
    at the synthetic surfaces instead of ``os.chdir``. Changing
    the process cwd would leave the tempdir locked on Windows
    when ``TemporaryDirectory`` runs cleanup, raising a misleading
    PermissionError after the screenshots have already been
    captured successfully.

    UI-10 added the ``scars_path`` configure argument so the
    drawer's /api/scars + POST /revoke flow exercises a per-run
    isolated rules directory.
    """
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from karasu.ui import server as ui_server

    ui_server.configure(
        event_log=workdir / ".karasu" / "events.jsonl",
        scars_path=workdir / ".karasu" / "scars",
        config_path=workdir / "karasu.yaml",
        # UI-12a — pin the push store to a path INSIDE the
        # tempdir so the screenshot run cannot read whatever
        # ``karasu-push.json`` happens to be in the operator's
        # cwd. Codex P2 on PR #98 round 1.
        push_store_path=workdir / ".karasu" / "karasu-push.json",
    )
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), ui_server.UIHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    return srv


def _seed_workdir(
    workdir: Path,
    populate: bool = True,
    events: list[dict] | None = None,
    scars: list[dict] | None = None,
    config: dict | None = None,
    push_subscriptions: list[dict] | None = None,
) -> None:
    """Reset the synthetic bus + scar rules before each capture.

    ``populate=True`` writes the four-event corpus; ``populate=
    False`` clears the file so the page renders against an
    empty bus (the UI-3 empty state). When ``events`` is
    provided it overrides the default corpus regardless of
    ``populate`` — UI-5 uses this to seed a state-specific
    event tail so the precedence-winning ``_crow_state`` lands
    on the desired display state.

    UI-10 added ``scars``: a list of scar dicts written to
    ``.karasu/scars/scars.jsonl`` so the drawer's revoke flow
    has something to render. ``None`` (default) clears the
    file so the section reads as the "no active scars" branch.
    Re-running the helper between captures keeps the surface
    deterministic without relying on the previous capture's
    cleanup.
    """
    bus = workdir / ".karasu" / "events.jsonl"
    bus.parent.mkdir(parents=True, exist_ok=True)
    with bus.open("w", encoding="utf-8") as fh:
        if events is not None:
            for event in events:
                fh.write(json.dumps(event) + "\n")
        elif populate:
            for event in SYNTHETIC_EVENTS:
                fh.write(json.dumps(event) + "\n")

    scars_dir = workdir / ".karasu" / "scars"
    scars_dir.mkdir(parents=True, exist_ok=True)
    scars_file = scars_dir / "scars.jsonl"
    with scars_file.open("w", encoding="utf-8") as fh:
        if scars:
            for scar in scars:
                fh.write(json.dumps(scar) + "\n")

    config_path = workdir / "karasu.yaml"
    if config is None:
        if config_path.exists():
            config_path.unlink()
    else:
        config_path.write_text(json.dumps(config), encoding="utf-8")

    # UI-12a — push store. Pinned inside the tempdir's
    # ``.karasu/`` so the captures cannot depend on a real
    # local ``karasu-push.json``. ``None`` clears the file so
    # the surface reads as the empty-state branch; a list
    # writes a synthetic store with one fake VAPID public key
    # plus the supplied subscriptions. The fake key + endpoints
    # are throwaway by design — they exist only inside the
    # tempdir and never leave it.
    push_store_path = workdir / ".karasu" / "karasu-push.json"
    if push_subscriptions is None:
        if push_store_path.exists():
            push_store_path.unlink()
    else:
        store = {
            "vapid": {
                "public": "screenshot-fake-vapid-public-do-not-use",
                "private": "screenshot-fake-vapid-private-do-not-use",
            },
            "subscriptions": push_subscriptions,
        }
        push_store_path.write_text(
            json.dumps(store), encoding="utf-8"
        )


def _resolve_seed_events(plan: dict) -> list[dict] | None:
    """Translate a plan's ``seed_events`` (a corpora key, or a
    literal list) into the events to write to the bus. ``None``
    means use the plan's ``seed`` field instead.

    The lookup walks STATE_CORPORA first (UI-5) then FLIGHT_CORPORA
    (UI-6). Keys are namespaced by prefix (``flight-...``) so a
    collision between the two registries is impossible by
    convention; the registries themselves stay separate so the
    crow_state corpora and the flight_route corpora are
    independently auditable.
    """
    spec = plan.get("seed_events")
    if spec is None:
        return None
    if isinstance(spec, str):
        if spec in STATE_CORPORA:
            return STATE_CORPORA[spec]
        if spec in FLIGHT_CORPORA:
            return FLIGHT_CORPORA[spec]
        raise ValueError(
            f"seed_events {spec!r} not in STATE_CORPORA or FLIGHT_CORPORA "
            f"(known: {sorted(set(STATE_CORPORA) | set(FLIGHT_CORPORA))})"
        )
    if isinstance(spec, list):
        return spec
    raise TypeError(f"seed_events must be str or list, got {type(spec).__name__}")


def _apply_step(page, plan: dict) -> None:
    """Apply the optional pre-screenshot steps for one capture
    entry (scroll, focus, hover, press_tab, wait). Each is a
    no-op when the relevant key is absent.

    ``wait_ms`` runs FIRST so the page's setInterval-driven
    state (e.g. UI-3 / UI-4 polling /api/events) settles before
    the focus / hover / press_tab steps target an element that
    only existed once the JS rendered. UI-4 needs this: the
    timeline rows are JS-rendered after the first poll, and
    targeting ``.event-row:first-child`` before the wait would
    miss the elements entirely.
    """
    if "wait_ms" in plan:
        page.wait_for_timeout(plan["wait_ms"])
    if "scroll_to" in plan:
        page.locator(plan["scroll_to"]).scroll_into_view_if_needed()
    if "focus" in plan:
        page.locator(plan["focus"]).focus()
    if "hover" in plan:
        page.locator(plan["hover"]).hover()
    if "press_tab" in plan:
        for _ in range(int(plan["press_tab"])):
            page.keyboard.press("Tab")
    if "click" in plan:
        page.locator(plan["click"]).first.click()
    if "post_click_wait_ms" in plan:
        # Settle window between the click that opens an animated
        # element (e.g. UI-7's drawer slide) and the screenshot.
        # Separate from ``wait_ms`` so the click timing is explicit.
        page.wait_for_timeout(plan["post_click_wait_ms"])
    if "eval_js" in plan:
        page.evaluate(plan["eval_js"])
    if "post_eval_wait_ms" in plan:
        # Settle window between an eval that opens an animated
        # element (e.g. UI-10's modal slide-in) and the
        # screenshot. Separate from ``wait_ms`` so the eval
        # timing is explicit.
        page.wait_for_timeout(plan["post_eval_wait_ms"])
    if "post_eval_hover" in plan:
        # Hover applied AFTER eval_js so a step that opens an
        # element via JS (e.g. UI-10's modal) can hover one of
        # the now-visible children. The pre-eval ``hover`` step
        # would target an element that does not exist yet and
        # time out.
        page.locator(plan["post_eval_hover"]).hover()


def _capture(slug: str, port: int, out_dir: Path, workdir: Path) -> None:
    plans = CAPTURES.get(slug)
    if not plans:
        print(
            f"error: no capture plan for slug {slug!r}.\n"
            f"  known slugs: {', '.join(sorted(CAPTURES))}",
            file=sys.stderr,
        )
        sys.exit(2)

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
        default_viewport = {"width": 1440, "height": 900}
        for plan in plans:
            viewport = plan.get("viewport", default_viewport)
            # New context per capture so a viewport override on
            # one entry does not leak into the next. Cheap on
            # Chromium; Playwright contexts are lightweight.
            context = browser.new_context(viewport=viewport)
            page = context.new_page()
            try:
                # UI-9 — force prefers-reduced-motion: reduce on
                # the page when the plan asks for it. The
                # chromatic whitelist in reset.css restricts
                # transition-property under this media; the
                # capture verifies the surface still renders
                # without motion-derived layout shift.
                if plan.get("reduced_motion"):
                    page.emulate_media(reduced_motion="reduce")
                seed_events = _resolve_seed_events(plan)
                _seed_workdir(
                    workdir,
                    populate=plan.get("seed", True),
                    events=seed_events,
                    scars=plan.get("seed_scars"),
                    config=plan.get("seed_config"),
                    push_subscriptions=plan.get("push_seed"),
                )
                page.goto(f"http://127.0.0.1:{port}{plan['url']}")
                page.wait_for_load_state("networkidle")
                _apply_step(page, plan)
                page.screenshot(
                    path=out_dir / plan["name"],
                    full_page=plan.get("full_page", False),
                )
                print(f"  wrote {plan['name']}")
            finally:
                context.close()
        browser.close()
    print(f"wrote {len(plans)} screenshots to {out_dir}")


def _record_video(slug: str, port: int, workdir: Path) -> None:
    """Record a single .webm walking through a state-transition
    sequence inside ONE Playwright context.

    Playwright auto-names the recording inside ``record_video_dir``
    (the page id with a ``.webm`` suffix). We rename it post-hoc
    to ``<slug>.webm`` under ``RECORDINGS_ROOT`` so the audit
    artifact has a stable path.

    The state seed between frames is performed by writing to the
    bus file and then calling ``tick()`` in the page so the
    ``/api/health`` poll is forced immediately rather than waiting
    for the natural 3 s ``setInterval``. This keeps the recording
    inside the 5 s budget without lowering the production poll
    rate (option (b)) or skipping the server-driven path (option
    (c)) — the choice noted in the planning conversation.
    """
    plan = RECORDINGS.get(slug)
    if plan is None:
        print(
            f"error: no recording plan for slug {slug!r}.\n"
            f"  known slugs: {', '.join(sorted(RECORDINGS))}",
            file=sys.stderr,
        )
        sys.exit(2)

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

    RECORDINGS_ROOT.mkdir(parents=True, exist_ok=True)
    final_path = RECORDINGS_ROOT / f"{slug}.webm"
    if final_path.exists():
        final_path.unlink()

    with tempfile.TemporaryDirectory() as raw_dir:
        raw_path = Path(raw_dir)
        viewport = plan.get("viewport", {"width": 1024, "height": 640})
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
            context = browser.new_context(
                viewport=viewport,
                record_video_dir=str(raw_path),
                record_video_size=viewport,
            )
            page = context.new_page()
            try:
                # Boot frame: the page renders against whatever the
                # server sees on the bus right now. We seed the
                # first frame's events BEFORE goto so the page's
                # initial fetch already lands on the desired state
                # — no perceptible class swap on first paint.
                first = plan["frames"][0]
                _seed_workdir(
                    workdir,
                    events=_resolve_seed_events(first),
                    scars=first.get("seed_scars"),
                    config=first.get("seed_config"),
                )
                page.goto(f"http://127.0.0.1:{port}{plan['url']}")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(first.get("wait_ms", 800))

                for frame in plan["frames"][1:]:
                    seed_events = _resolve_seed_events(frame)
                    if seed_events is not None:
                        _seed_workdir(
                            workdir,
                            events=seed_events,
                            scars=frame.get("seed_scars"),
                            config=frame.get("seed_config"),
                        )
                        # Force an immediate /api/health + /api/events
                        # round-trip so the next CSS class swap fires
                        # without waiting for the 3 s polling tick.
                        # ``tick`` is a top-level async function in
                        # the page script.
                        page.evaluate("async () => { await tick(); }")
                    if "eval_js" in frame:
                        page.evaluate(frame["eval_js"])
                    page.wait_for_timeout(frame.get("wait_ms", 1000))
            finally:
                context.close()  # finalises the .webm
                browser.close()

        # Find the auto-named webm and rename to the audit path.
        produced = sorted(raw_path.glob("*.webm"))
        if not produced:
            print(
                f"error: playwright did not emit a .webm under {raw_path}",
                file=sys.stderr,
            )
            sys.exit(2)
        if len(produced) > 1:
            print(
                f"warning: more than one .webm under {raw_path}, "
                f"picking {produced[0].name}",
                file=sys.stderr,
            )
        # ``shutil.move`` handles cross-drive moves on Windows
        # (temp dir on C:, repo on D:); ``Path.replace`` is
        # ``os.replace`` which raises WinError 17 across volumes.
        shutil.move(str(produced[0]), str(final_path))

    size_kb = final_path.stat().st_size / 1024
    print(f"wrote {final_path} ({size_kb:.1f} KB)")
    if size_kb > 500:
        print(
            f"warning: {final_path.name} exceeds the 500 KB audit "
            "budget; transcode with ffmpeg before commit (libvpx-vp9, "
            "low CRF). See docs/ui/screenshots/UI-5-crow/README.md.",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "slug",
        help="chunk slug (e.g. UI-2-tokens). Becomes the screenshot dir name.",
    )
    parser.add_argument(
        "--record-video",
        action="store_true",
        help=(
            "Record a .webm walking through the slug's RECORDINGS "
            "frame plan instead of taking screenshots. Output goes "
            "to docs/ui/recordings/<slug>.webm."
        ),
    )
    args = parser.parse_args(argv)

    out_dir = SCREENSHOTS_ROOT / args.slug
    port = _free_port()
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        # Seed once up front so the server boots against a real
        # bus path; per-capture reseeding inside ``_capture`` /
        # ``_record_video`` picks the right state for each shot
        # or frame.
        _seed_workdir(workdir, populate=True)
        srv = _start_server(workdir, port)
        try:
            if args.record_video:
                _record_video(args.slug, port, workdir)
            else:
                _capture(args.slug, port, out_dir, workdir)
        finally:
            srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
