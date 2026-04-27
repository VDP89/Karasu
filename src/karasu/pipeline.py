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
                classified.data.update(override)
        response_event = self.dispatcher.dispatch(classified)
        if response_event is None:
            return
        report = self.reporter.report(response_event)
        if report is not None:
            self.sink(report)
