"""Pattern-based classifier.

Each rule is a glob, a classification label and a priority. The
first matching rule wins; if no rule matches the event is classified
as ``unknown`` with ``normal`` priority.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Iterable

from karasu.eventbus import Event


@dataclass(frozen=True)
class ClassificationRule:
    match: str
    type: str
    priority: str = "normal"


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
