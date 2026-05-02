"""Tests for the A2A AgentCard primitives — Phase 3+ chunk 4b.

Failure-mode coverage per ``docs/phase-3-plus-pre-mortem.md`` § 4b:

- F-A2A-1   information disclosure (card carries no PII / config /
            scars / external CLI versions; only published-skill
            metadata + agent identity)
- F-A2A-2   spec drift (camelCase keys on the wire match the A2A
            spec snapshot recorded in card.py)
- F-A2A-3   capability false positives — chunk 4b uses a static
            skill list per the audit decision; this test pins the
            current set so future drift is a visible diff
"""

from __future__ import annotations

import json

from karasu import __version__
from karasu.a2a import (
    AgentCapabilities,
    AgentCard,
    Skill,
    build_karasu_card,
)


# ---------------------------------------------------------------------------
# AgentCapabilities — wire shape
# ---------------------------------------------------------------------------


def test_capabilities_default_is_off() -> None:
    """Chunk 4b is discovery-only; both capability flags default off."""
    caps = AgentCapabilities()
    assert caps.streaming is False
    assert caps.push_notifications is False


def test_capabilities_to_dict_uses_camelcase_wire_keys() -> None:
    """F-A2A-2: A2A spec uses camelCase on the wire even though our
    Python attributes are snake_case."""
    caps = AgentCapabilities(streaming=True, push_notifications=True)
    payload = caps.to_dict()
    assert payload == {"streaming": True, "pushNotifications": True}


# ---------------------------------------------------------------------------
# Skill — wire shape
# ---------------------------------------------------------------------------


def test_skill_to_dict_round_trips_fields() -> None:
    skill = Skill(id="x", name="X", description="x desc")
    assert skill.to_dict() == {"id": "x", "name": "X", "description": "x desc"}


# ---------------------------------------------------------------------------
# AgentCard — wire shape
# ---------------------------------------------------------------------------


def test_card_to_dict_includes_all_required_fields() -> None:
    card = AgentCard(
        name="t",
        description="d",
        version="0.0.1",
        url="http://example",
        capabilities=AgentCapabilities(),
        skills=(Skill("a", "A", "a desc"),),
    )
    payload = card.to_dict()
    assert payload["name"] == "t"
    assert payload["description"] == "d"
    assert payload["version"] == "0.0.1"
    assert payload["url"] == "http://example"
    assert payload["capabilities"] == {
        "streaming": False,
        "pushNotifications": False,
    }
    assert payload["skills"] == [
        {"id": "a", "name": "A", "description": "a desc"}
    ]


def test_card_to_dict_serialises_to_valid_json() -> None:
    """The card has to be JSON-encodable; if a future field breaks
    that, this catches it before the HTTP layer does."""
    card = build_karasu_card(base_url="http://127.0.0.1:8080")
    body = json.dumps(card.to_dict())
    parsed = json.loads(body)
    assert parsed["name"] == "karasu"


# ---------------------------------------------------------------------------
# build_karasu_card — baseline contract
# ---------------------------------------------------------------------------


def test_build_karasu_card_uses_package_version() -> None:
    card = build_karasu_card()
    assert card.version == __version__


def test_build_karasu_card_url_optional() -> None:
    card = build_karasu_card()
    assert card.url is None
    card = build_karasu_card(base_url="http://x:1")
    assert card.url == "http://x:1"


def test_build_karasu_card_publishes_four_baseline_skills() -> None:
    """F-A2A-3: pin the current static skill list so future changes
    are a visible diff. The audit accepted static publication for
    chunk 4b; adapter-conditional filtering is deferred."""
    card = build_karasu_card()
    skill_ids = [s.id for s in card.skills]
    assert skill_ids == [
        "watch-filesystem",
        "route-events",
        "receive-github-webhooks",
        "record-corrections",
    ]


def test_build_karasu_card_skills_have_names_and_descriptions() -> None:
    card = build_karasu_card()
    for skill in card.skills:
        assert skill.name, f"skill {skill.id} missing name"
        assert skill.description, f"skill {skill.id} missing description"


# ---------------------------------------------------------------------------
# F-A2A-1 — information disclosure
# ---------------------------------------------------------------------------


def test_card_does_not_leak_internal_state() -> None:
    """F-A2A-1: the card MUST NOT carry runtime config, secrets,
    paths, or scar contents. Pin the field set so a future
    contributor adding "agent.config_path" or similar trips this."""
    card = build_karasu_card(base_url="http://127.0.0.1:8080")
    payload = card.to_dict()
    allowed_top_level = {
        "name",
        "description",
        "version",
        "url",
        "capabilities",
        "skills",
    }
    assert set(payload.keys()) == allowed_top_level

    # Each skill carries only id / name / description — no
    # "config", "trust_level", "command", "secret", etc.
    allowed_skill_keys = {"id", "name", "description"}
    for skill_payload in payload["skills"]:
        assert set(skill_payload.keys()) == allowed_skill_keys


def test_card_capability_keys_are_exactly_two() -> None:
    """F-A2A-2 contract: capabilities object has streaming +
    pushNotifications, nothing else. Expansion goes through a
    spec-snapshot bump, not an ad-hoc field."""
    payload = AgentCapabilities().to_dict()
    assert set(payload.keys()) == {"streaming", "pushNotifications"}
