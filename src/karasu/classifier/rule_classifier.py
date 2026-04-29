"""Pattern-based classifier.

Each rule is a glob, a classification label and a priority. The
first matching rule wins; if no rule matches the event is classified
as ``unknown`` with ``normal`` priority.

Rules may also opt into a ``dispatch_on`` list — the set of
``change_type`` values for which the pipeline should actually fire
the adapter. When the list is omitted the pipeline applies a
classification-aware default (see ``Pipeline.__call__``).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Iterable

from karasu.eventbus import Event


@dataclass(frozen=True)
class ClassificationRule:
    match: str
    type: str
    priority: str = "normal"
    dispatch_on: tuple[str, ...] | None = field(default=None)

    def __post_init__(self) -> None:
        # YAML loaders hand back lists; freeze them so the rule stays
        # hashable and we don't surprise callers later by mutating
        # config-derived state.
        if self.dispatch_on is not None and not isinstance(self.dispatch_on, tuple):
            object.__setattr__(self, "dispatch_on", tuple(self.dispatch_on))


class RuleClassifier:
    """Apply a list of :class:`ClassificationRule` to incoming events."""

    DEFAULT_TYPE = "unknown"
    DEFAULT_PRIORITY = "normal"

    def __init__(self, rules: Iterable[ClassificationRule] = ()) -> None:
        self.rules = list(rules)

    def classify(self, event: Event) -> Event:
        path = event.data.get("path", "")
        for rule in self.rules:
            if self._matches(rule.match, path):
                event.data["classification"] = rule.type
                event.data["priority"] = rule.priority
                if rule.dispatch_on is not None:
                    event.data["dispatch_on"] = list(rule.dispatch_on)
                return event
        event.data.setdefault("classification", self.DEFAULT_TYPE)
        event.data.setdefault("priority", self.DEFAULT_PRIORITY)
        return event

    @staticmethod
    def _matches(pattern: str, path: str) -> bool:
        if "**" in pattern:
            prefix = pattern.split("**", 1)[0].rstrip("/")
            return path.startswith(prefix)
        return fnmatch.fnmatch(path, pattern)
