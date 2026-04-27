from pathlib import Path

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
