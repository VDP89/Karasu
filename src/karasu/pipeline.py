"""Wire watcher → classifier → router → reporter into a single callable.

The pipeline is the bridge between the watcher (which only knows how
to emit ``file_change`` events) and the rest of Karasu. It is built
once from config and then handed to ``FilesystemWatcher`` as the
``on_event`` callback.
"""

from __future__ import annotations

from typing import Callable

from karasu.classifier import RuleClassifier
from karasu.eventbus import Event
from karasu.reporter import HumanReporter, Report
from karasu.router import Dispatcher
from karasu.scars import ScarEngine

ReportSink = Callable[[Report], None]


class Pipeline:
    """Run a single ``file_change`` event through the full chain."""

    # Phase 1 scar contract: a correction may only override the keys
    # the Dispatcher / AgentRequest actually read. Anything else (e.g.
    # ``agent``) would silently be ignored by routing, which would
    # confuse operators who recorded the override expecting it to
    # change agent selection. See docs/scar-engine.md.
    SUPPORTED_SCAR_KEYS = frozenset({"classification", "priority", "path"})

    # F7 — atomic-write semantics. Editors that save through a
    # write-then-rename sequence (VS Code, the Claude Code Write tool,
    # most "atomic save" implementations) emit a ``deleted`` on the
    # original path before the new content is in place. Dispatching a
    # code-review adapter against that transient delete sends the
    # adapter at a path that may not exist yet. ``code_change`` is
    # therefore restricted to file states where reviewable content
    # exists. Per-rule ``dispatch_on`` overrides this default.
    _DEFAULT_DISPATCH_ON: dict[str, tuple[str, ...]] = {
        "code_change": ("created", "modified"),
    }

    def __init__(
        self,
        classifier: RuleClassifier,
        dispatcher: Dispatcher,
        reporter: HumanReporter,
        sink: ReportSink,
        scars: ScarEngine | None = None,
    ) -> None:
        self.classifier = classifier
        self.dispatcher = dispatcher
        self.reporter = reporter
        self.sink = sink
        self.scars = scars

    def __call__(self, event: Event) -> None:
        if event.type != "file_change":
            return
        classified = self.classifier.classify(event)
        if self.scars is not None:
            override = self.scars.apply(
                classified.data.get("classification", ""),
                classified.data.get("path", ""),
            )
            if override:
                self._apply_scar_override(classified, override)
        if not self._should_dispatch(classified):
            return
        response_event = self.dispatcher.dispatch(classified)
        if response_event is None:
            return
        report = self.reporter.report(response_event)
        if report is not None:
            self.sink(report)

    def _should_dispatch(self, event: Event) -> bool:
        """Apply the per-rule or classification-default dispatch_on filter.

        - When the rule supplied an explicit ``dispatch_on`` list (carried
          on ``event.data``), only those change types pass through.
        - When the rule was silent, look up the classification-level
          default in ``_DEFAULT_DISPATCH_ON`` (e.g. ``code_change``
          excludes ``deleted``).
        - Classifications without an explicit rule and without a
          documented default are not filtered — the dispatcher remains
          the single source of "no adapter handles this".
        """
        change_type = event.data.get("change_type")
        if change_type is None:
            return True
        rule_dispatch_on = event.data.get("dispatch_on")
        if rule_dispatch_on is not None:
            return change_type in rule_dispatch_on
        classification = event.data.get("classification", "")
        default_dispatch_on = self._DEFAULT_DISPATCH_ON.get(classification)
        if default_dispatch_on is None:
            return True
        return change_type in default_dispatch_on

    def _apply_scar_override(self, event: Event, override: dict) -> None:
        unknown = set(override) - self.SUPPORTED_SCAR_KEYS
        if unknown:
            raise ValueError(
                f"scar correction has unsupported keys {sorted(unknown)}; "
                f"Phase 1 supports only {sorted(self.SUPPORTED_SCAR_KEYS)}. "
                "See docs/scar-engine.md for the contract."
            )
        event.data.update(override)
