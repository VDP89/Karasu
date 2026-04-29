from pathlib import Path

import pytest

from karasu.adapters.base import AgentAdapter, AgentRequest, AgentResponse
from karasu.classifier import ClassificationRule, RuleClassifier
from karasu.eventbus import Event, JsonlEventBus
from karasu.pipeline import Pipeline
from karasu.reporter import HumanReporter, Report
from karasu.router import Dispatcher
from karasu.scars import Scar, ScarEngine
from karasu.trust import TrustGradient


class _StubAdapter(AgentAdapter):
    def __init__(self, name: str, handles=("code_change",)) -> None:
        super().__init__(handles=handles, trust_level=2)
        self.name = name
        self.calls: list[AgentRequest] = []

    def dispatch(self, request: AgentRequest) -> AgentResponse:
        self.calls.append(request)
        return AgentResponse(content=f"{self.name} handled {request.path}", success=True, requires_human=False)


def _file_change(path: str) -> Event:
    return Event(type="file_change", source="watcher", data={"path": path, "change_type": "modified"})


def _build(bus: JsonlEventBus, adapters: list[AgentAdapter], scars: ScarEngine | None = None) -> tuple[Pipeline, list[Report]]:
    classifier = RuleClassifier(
        [ClassificationRule(match="*.py", type="code_change", priority="normal")]
    )
    dispatcher = Dispatcher(bus=bus, adapters=adapters)
    reporter = HumanReporter(TrustGradient({a.name: a.trust_level for a in adapters}))
    sink: list[Report] = []
    pipeline = Pipeline(classifier, dispatcher, reporter, sink.append, scars=scars)
    return pipeline, sink


def test_pipeline_runs_full_chain(bus: JsonlEventBus) -> None:
    adapter = _StubAdapter("claude_code")
    pipeline, reports = _build(bus, [adapter])

    pipeline(_file_change("src/foo.py"))

    assert len(adapter.calls) == 1
    assert adapter.calls[0].classification == "code_change"
    assert reports and "claude_code handled src/foo.py" in reports[0].text


def test_pipeline_ignores_non_file_change_events(bus: JsonlEventBus) -> None:
    adapter = _StubAdapter("claude_code")
    pipeline, reports = _build(bus, [adapter])

    pipeline(Event(type="agent_response", source="adapter"))

    assert adapter.calls == []
    assert reports == []


def test_pipeline_applies_scar_override(tmp_path: Path, bus: JsonlEventBus) -> None:
    scars = ScarEngine(tmp_path / "scars")
    scars.record(
        Scar(
            trigger={"classification": "code_change", "path": "*.py"},
            correction={"classification": "audit"},
        )
    )
    claude = _StubAdapter("claude_code", handles=("code_change",))
    codex = _StubAdapter("codex", handles=("audit",))
    pipeline, _ = _build(bus, [claude, codex], scars=scars)

    pipeline(_file_change("src/foo.py"))

    assert claude.calls == []
    assert len(codex.calls) == 1


def test_pipeline_accepts_priority_and_path_in_scar_correction(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    scars = ScarEngine(tmp_path / "scars")
    scars.record(
        Scar(
            trigger={"classification": "code_change", "path": "*.py"},
            correction={"priority": "high", "path": "rewritten/foo.py"},
        )
    )
    claude = _StubAdapter("claude_code", handles=("code_change",))
    pipeline, _ = _build(bus, [claude], scars=scars)

    pipeline(_file_change("src/foo.py"))

    assert len(claude.calls) == 1
    assert claude.calls[0].priority == "high"
    assert claude.calls[0].path == "rewritten/foo.py"


def test_pipeline_rejects_unsupported_scar_correction_keys(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    scars = ScarEngine(tmp_path / "scars")
    # `agent` is documented as a Phase 2 capability; in Phase 1 the
    # Dispatcher would silently ignore it, so the pipeline must fail
    # fast rather than pretend the override applied.
    scars.record(
        Scar(
            trigger={"classification": "code_change", "path": "*.py"},
            correction={"agent": "codex"},
        )
    )
    claude = _StubAdapter("claude_code", handles=("code_change",))
    pipeline, _ = _build(bus, [claude], scars=scars)

    with pytest.raises(ValueError, match="unsupported keys.*agent"):
        pipeline(_file_change("src/foo.py"))


def test_pipeline_rejects_mixed_supported_and_unsupported_keys(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    scars = ScarEngine(tmp_path / "scars")
    scars.record(
        Scar(
            trigger={"classification": "code_change", "path": "*.py"},
            correction={"classification": "audit", "trust_level": 3},
        )
    )
    claude = _StubAdapter("claude_code", handles=("code_change",))
    pipeline, _ = _build(bus, [claude], scars=scars)

    with pytest.raises(ValueError, match="unsupported keys.*trust_level"):
        pipeline(_file_change("src/foo.py"))


# ---------------------------------------------------------------------------
# F7 — dispatch_on filter (atomic-write / per-rule override)
# ---------------------------------------------------------------------------


def _file_change_with(path: str, change_type: str) -> Event:
    return Event(
        type="file_change",
        source="watcher",
        data={"path": path, "change_type": change_type},
    )


def test_code_change_default_excludes_deleted(bus: JsonlEventBus) -> None:
    # The Write/atomic-rename pattern emits ``deleted`` on the original
    # path before the new content lands. Dispatching on that transient
    # state would send the adapter at a file that does not exist yet.
    adapter = _StubAdapter("claude_code")
    pipeline, reports = _build(bus, [adapter])

    pipeline(_file_change_with("src/foo.py", "deleted"))

    assert adapter.calls == []
    assert reports == []


def test_code_change_default_dispatches_on_modified(bus: JsonlEventBus) -> None:
    adapter = _StubAdapter("claude_code")
    pipeline, reports = _build(bus, [adapter])

    pipeline(_file_change_with("src/foo.py", "modified"))

    assert len(adapter.calls) == 1
    assert reports


def test_code_change_default_dispatches_on_created(bus: JsonlEventBus) -> None:
    adapter = _StubAdapter("claude_code")
    pipeline, reports = _build(bus, [adapter])

    pipeline(_file_change_with("src/foo.py", "created"))

    assert len(adapter.calls) == 1
    assert reports


def _build_with_dispatch_on(
    bus: JsonlEventBus, dispatch_on: tuple[str, ...]
) -> tuple[Pipeline, list[Report], _StubAdapter]:
    adapter = _StubAdapter("claude_code")
    classifier = RuleClassifier(
        [
            ClassificationRule(
                match="*.py",
                type="code_change",
                priority="normal",
                dispatch_on=dispatch_on,
            )
        ]
    )
    dispatcher = Dispatcher(bus=bus, adapters=[adapter])
    reporter = HumanReporter(TrustGradient({"claude_code": 2}))
    sink: list[Report] = []
    pipeline = Pipeline(classifier, dispatcher, reporter, sink.append)
    return pipeline, sink, adapter


def test_rule_dispatch_on_overrides_default_to_allow_deleted(bus: JsonlEventBus) -> None:
    # An operator who genuinely wants to react to deletions (security
    # audit, scar/index cleanup) opts in via per-rule ``dispatch_on``.
    pipeline, reports, adapter = _build_with_dispatch_on(
        bus, ("created", "modified", "deleted")
    )

    pipeline(_file_change_with("src/foo.py", "deleted"))

    assert len(adapter.calls) == 1
    assert reports


def test_rule_dispatch_on_overrides_default_to_restrict(bus: JsonlEventBus) -> None:
    pipeline, _, adapter = _build_with_dispatch_on(bus, ("created",))

    pipeline(_file_change_with("src/foo.py", "modified"))
    pipeline(_file_change_with("src/foo.py", "created"))

    assert len(adapter.calls) == 1
    assert adapter.calls[0].path == "src/foo.py"


def test_unknown_classification_is_not_filtered(bus: JsonlEventBus) -> None:
    # ``unknown`` (no rule matched) has no documented default and no
    # rule-level override. The pipeline should not silently swallow
    # those events; the dispatcher remains the single point that
    # decides "no adapter handles this".
    adapter = _StubAdapter("claude_code", handles=("code_change",))
    classifier = RuleClassifier()  # no rules → everything is unknown
    dispatcher = Dispatcher(bus=bus, adapters=[adapter])
    reporter = HumanReporter(TrustGradient({"claude_code": 2}))
    sink: list[Report] = []
    pipeline = Pipeline(classifier, dispatcher, reporter, sink.append)

    pipeline(_file_change_with("README.md", "deleted"))

    # Adapter does not handle ``unknown`` → no dispatch, but we passed
    # the change_type filter (no default to apply) and the dispatcher
    # is the one rejecting via Router F3.
    assert adapter.calls == []
