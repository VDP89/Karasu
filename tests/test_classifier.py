from karasu.classifier import ClassificationRule, RuleClassifier
from karasu.eventbus import Event


def _file_event(path: str) -> Event:
    return Event(type="file_change", source="watcher", data={"path": path})


def test_first_matching_rule_wins() -> None:
    classifier = RuleClassifier(
        [
            ClassificationRule(match="*.py", type="code_change", priority="normal"),
            ClassificationRule(match="*.md", type="doc_change", priority="low"),
        ]
    )
    event = classifier.classify(_file_event("src/foo.py"))
    assert event.data["classification"] == "code_change"
    assert event.data["priority"] == "normal"


def test_recursive_pattern_matches_subtree() -> None:
    classifier = RuleClassifier(
        [ClassificationRule(match="scars/**", type="scar_change", priority="high")]
    )
    event = classifier.classify(_file_event("scars/rules/abc.jsonl"))
    assert event.data["classification"] == "scar_change"


def test_unknown_path_falls_back_to_default() -> None:
    classifier = RuleClassifier()
    event = classifier.classify(_file_event("README"))
    assert event.data["classification"] == "unknown"
    assert event.data["priority"] == "normal"
