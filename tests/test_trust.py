from karasu.trust import TrustGradient, TrustLevel


def test_unknown_agent_defaults_to_confirm() -> None:
    trust = TrustGradient()
    assert trust.level("ghost") == TrustLevel.CONFIRM
    assert trust.requires_human("ghost") is True


def test_silent_agent_does_not_require_human() -> None:
    trust = TrustGradient({"watchdog": 3})
    assert trust.level("watchdog") == TrustLevel.SILENT
    assert trust.requires_human("watchdog") is False


def test_set_updates_level() -> None:
    trust = TrustGradient()
    trust.set("claude_code", 2)
    assert trust.level("claude_code") == TrustLevel.NOTIFY_ASYNC
    assert trust.requires_human("claude_code") is False
