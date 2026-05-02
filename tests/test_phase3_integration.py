"""Phase 3 integration tests.

End-to-end exercises of the chunk-3b reaction loop with a fake
adapter standing in for the real Claude CLI. Production wiring
(watcher → controller → pipeline → adapter → bus → controller bus
subscription → resubmit) is exercised in a single test so we have
automated evidence the loop closes without requiring the real
``claude`` binary.

The manual dogfood (``docs/phase-3-dogfood.md``) is the production
counterpart that exercises the same path against a real Claude CLI
+ Telegram bot. These tests cover what's automatable; the runbook
covers what isn't.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from karasu.adapters import AgentAdapter, AgentRequest, AgentResponse
from karasu.classifier import ClassificationRule, RuleClassifier
from karasu.controller import LoopController
from karasu.eventbus import Event, JsonlEventBus
from karasu.interface.commands import capture_correct, capture_scar
from karasu.pipeline import Pipeline
from karasu.reporter import HumanReporter
from karasu.router import Dispatcher
from karasu.scars import ScarEngine
from karasu.trust import TrustGradient


class _FakeAdapter(AgentAdapter):
    """Fake adapter that records every dispatch and replies success."""

    def __init__(self) -> None:
        super().__init__(
            name="fake_claude",
            handles=("code_change",),
            trust_level=2,
        )
        self.dispatched: list[AgentRequest] = []

    def dispatch(self, request: AgentRequest) -> AgentResponse:
        self.dispatched.append(request)
        return AgentResponse(
            content=f"fake reply for {request.path}",
            success=True,
            requires_human=False,
        )


def _build_stack(tmp_path: Path):
    """Build the production wiring with a fake adapter.

    Returns ``(controller, bus, scars, classifier, adapter, sink_calls)``.
    Caller owns ``controller.start()`` / ``controller.stop()``.
    """
    bus_path = tmp_path / ".karasu" / "events.jsonl"
    bus_path.parent.mkdir(parents=True, exist_ok=True)
    bus = JsonlEventBus(bus_path)

    scars = ScarEngine(tmp_path / "scars")
    classifier = RuleClassifier(
        [ClassificationRule(match="*.py", type="code_change", priority="normal")]
    )
    adapter = _FakeAdapter()
    dispatcher = Dispatcher(bus=bus, adapters=[adapter])
    trust = TrustGradient({"fake_claude": 2})
    reporter = HumanReporter(trust)

    sink_calls: list[str] = []

    def sink(report) -> None:
        sink_calls.append(report.text)

    pipeline = Pipeline(
        classifier=classifier,
        dispatcher=dispatcher,
        reporter=reporter,
        sink=sink,
        scars=scars,
    )

    controller = LoopController(pipeline, bus=bus)
    # Speed up — default is 0.5 s; tests want sub-second reactions.
    controller._BUS_POLL_INTERVAL = 0.05  # type: ignore[misc]
    return controller, bus, scars, classifier, adapter, sink_calls


def _record_correction(
    bus: JsonlEventBus,
    scars: ScarEngine,
    classifier: RuleClassifier,
    target_id: str,
    correction_args: str,
    user_id: int = 1,
) -> None:
    """Mirror what TelegramInterface.handle_write_command does for
    an authorized /correct: write the Scar AND the human_decision.

    The surface in production records both (Scar via ``capture_correct``,
    human_decision via ``handle_write_command``). The integration
    test simulates that pair.
    """
    args = f"{target_id[:8]} {correction_args}"
    reply = capture_correct(bus, scars, classifier, args)
    assert reply.startswith("recorded scar"), reply
    bus.append(
        Event(
            type="human_decision",
            source="interface",
            data={"user": user_id, "text": f"/correct {args}"},
        )
    )


def _wait_for(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Full chunk-3b loop — /correct path
# ---------------------------------------------------------------------------


def test_correct_resubmit_applies_scar_on_second_dispatch(tmp_path: Path) -> None:
    """The chunk-3b headline path.

    1. Watcher submits a file_change.
    2. Pipeline dispatches; fake adapter sees priority=normal.
    3. Operator records /correct priority=high (Scar + human_decision).
    4. Controller picks up human_decision via JsonlTailReader.
    5. Controller resubmits the originating file_change with
       ``controller_resubmit=True``.
    6. Pipeline runs again, ``_apply_scar_override`` rewrites priority
       to ``high``, fake adapter now sees priority=high.

    If any link in this chain breaks, this test fails.
    """
    controller, bus, scars, classifier, adapter, _ = _build_stack(tmp_path)
    controller.start()
    try:
        # 1. Initial file_change (simulating watcher output).
        original = bus.append(
            Event(
                type="file_change",
                source="watcher",
                data={"path": "x.py", "change_type": "modified"},
            )
        )
        controller.submit(original)

        # 2. Wait for first dispatch.
        assert _wait_for(lambda: len(adapter.dispatched) >= 1), (
            "first dispatch never fired"
        )
        assert adapter.dispatched[0].priority == "normal"

        # Find the agent_response on the bus.
        responses = [e for e in bus.read() if e.type == "agent_response"]
        assert len(responses) == 1
        original_response = responses[0]

        # 3. Operator records /correct priority=high.
        _record_correction(
            bus,
            scars,
            classifier,
            target_id=original_response.id,
            correction_args="priority=high",
        )

        # 4-6. Wait for the controller's reaction → resubmit → second dispatch.
        assert _wait_for(lambda: len(adapter.dispatched) >= 2, timeout=5.0), (
            "controller never resubmitted"
        )

        # The second dispatch saw the corrected priority — the scar
        # actually changed the dispatch payload.
        assert adapter.dispatched[1].priority == "high"

        # The bus shows the resubmit explicitly.
        file_changes = [e for e in bus.read() if e.type == "file_change"]
        assert len(file_changes) == 2
        assert file_changes[1].data.get("controller_resubmit") is True
        assert file_changes[1].data.get("resubmit_origin") == original.id
        assert file_changes[1].source == "controller"
    finally:
        controller.stop()


# ---------------------------------------------------------------------------
# /scar variant — uses latest agent_response
# ---------------------------------------------------------------------------


def test_scar_resubmit_uses_latest_agent_response(tmp_path: Path) -> None:
    controller, bus, scars, classifier, adapter, _ = _build_stack(tmp_path)
    controller.start()
    try:
        # Two dispatches — controller should target the latest.
        first_fc = bus.append(
            Event(
                type="file_change",
                source="watcher",
                data={"path": "old.py", "change_type": "modified"},
            )
        )
        controller.submit(first_fc)
        assert _wait_for(lambda: len(adapter.dispatched) >= 1)

        second_fc = bus.append(
            Event(
                type="file_change",
                source="watcher",
                data={"path": "new.py", "change_type": "modified"},
            )
        )
        controller.submit(second_fc)
        assert _wait_for(lambda: len(adapter.dispatched) >= 2)

        # /scar — apply correction to the latest agent_response.
        reply = capture_scar(bus, scars, classifier, "priority=high")
        assert reply.startswith("recorded scar"), reply
        bus.append(
            Event(
                type="human_decision",
                source="interface",
                data={"user": 1, "text": "/scar priority=high"},
            )
        )

        assert _wait_for(lambda: len(adapter.dispatched) >= 3, timeout=5.0)

        # Third dispatch is the resubmit of the LATEST file_change (new.py).
        assert adapter.dispatched[2].path == "new.py"
        assert adapter.dispatched[2].priority == "high"
    finally:
        controller.stop()


# ---------------------------------------------------------------------------
# Cap enforcement under repeated /correct
# ---------------------------------------------------------------------------


def test_resubmit_cap_holds_under_spammed_corrections(tmp_path: Path) -> None:
    """A spam-/correct script must not drive the dispatcher in an
    unbounded loop. The chain cap (``CHAIN_CAP=3``, issue #47)
    bounds the total resubmits in the chain rooted at the
    originating ``file_change.id``. Spam at depth 1 (same
    agent_response /scar'd N times) increments the same counter
    as a progressing chain, preserving the pre-issue-#47 dogfood
    behaviour.
    """
    controller, bus, scars, classifier, adapter, _ = _build_stack(tmp_path)
    controller.start()
    try:
        original = bus.append(
            Event(
                type="file_change",
                source="watcher",
                data={"path": "spam.py", "change_type": "modified"},
            )
        )
        controller.submit(original)
        assert _wait_for(lambda: len(adapter.dispatched) >= 1)

        responses = [e for e in bus.read() if e.type == "agent_response"]
        original_response = responses[0]

        # Fire CHAIN_CAP + 2 corrections.
        for _ in range(LoopController.CHAIN_CAP + 2):
            _record_correction(
                bus,
                scars,
                classifier,
                target_id=original_response.id,
                correction_args="priority=high",
            )

        # Wait for the cap to be reached. Total dispatches = 1 original
        # + CHAIN_CAP resubmits.
        expected = 1 + LoopController.CHAIN_CAP
        assert _wait_for(
            lambda: len(adapter.dispatched) >= expected, timeout=5.0
        )

        # Give the bus poll a couple more cycles to catch any cap
        # violation. ``_BUS_POLL_INTERVAL`` is 0.05 s in tests.
        time.sleep(0.4)

        assert len(adapter.dispatched) == expected, (
            f"expected {expected} dispatches (1 original + cap={LoopController.CHAIN_CAP}), "
            f"got {len(adapter.dispatched)}"
        )

        # The bus shows exactly CHAIN_CAP resubmits, all at depth 1
        # of the same chain (spam against the same response).
        resubmits = [
            e
            for e in bus.read()
            if e.type == "file_change"
            and e.data.get("controller_resubmit") is True
        ]
        assert len(resubmits) == LoopController.CHAIN_CAP
        for r in resubmits:
            assert r.data["controller_chain_depth"] == 1
    finally:
        controller.stop()


# ---------------------------------------------------------------------------
# No reaction on unrelated bus events
# ---------------------------------------------------------------------------


def test_unrelated_human_decision_does_not_trigger_resubmit(
    tmp_path: Path,
) -> None:
    """Every Telegram inbound writes a human_decision; only /correct
    and /scar should react. /status and /agents reads do NOT write
    human_decision (chunk 2 contract), but a free-form text reply
    that gets routed to record_decision shouldn't either."""
    controller, bus, scars, classifier, adapter, _ = _build_stack(tmp_path)
    controller.start()
    try:
        original = bus.append(
            Event(
                type="file_change",
                source="watcher",
                data={"path": "x.py", "change_type": "modified"},
            )
        )
        controller.submit(original)
        assert _wait_for(lambda: len(adapter.dispatched) >= 1)

        # Various non-actionable human_decision texts.
        for text in (
            "thanks",
            "/status",  # wrong shape — chunk 2 commands don't write human_decision in production
            "/correct (unauthorized)",
            "/scar (unauthorized)",
            "/teleport now",
        ):
            bus.append(
                Event(
                    type="human_decision",
                    source="interface",
                    data={"user": 1, "text": text},
                )
            )

        # Give the bus poll a few cycles.
        time.sleep(0.4)
        assert len(adapter.dispatched) == 1, (
            f"expected no resubmit, got {len(adapter.dispatched)} dispatches"
        )
    finally:
        controller.stop()
