"""A2A — Agent-to-Agent discovery primitives.

Phase 3+ chunk 4b. Karasu publishes a static A2A AgentCard at
``/.well-known/agent-card.json`` so peer agents can discover its
baseline capabilities.

The card describes Karasu's **agent-level capabilities**, not the
runtime state of the current process. A `karasu serve` instance
publishes the same card whether or not `karasu chat` is also
running — operators run those as separate processes, and the A2A
peer needs to know what the agent CAN do, not which subset of
processes happens to be live.

Discovery only — capability NEGOTIATION is Phase 3++ scope.
"""

from karasu.a2a.card import (
    AgentCapabilities,
    AgentCard,
    Skill,
    build_karasu_card,
)
from karasu.a2a.fetch import (
    AGENT_CARD_PATH,
    DEFAULT_FETCH_RETRIES,
    DEFAULT_FETCH_RETRY_HTTP_STATUSES,
    DEFAULT_FETCH_TIMEOUT,
    RECOMMENDED_RETRY_HTTP_STATUSES,
    AgentCardFetchError,
    fetch_card,
)

__all__ = [
    "AGENT_CARD_PATH",
    "DEFAULT_FETCH_RETRIES",
    "DEFAULT_FETCH_RETRY_HTTP_STATUSES",
    "DEFAULT_FETCH_TIMEOUT",
    "RECOMMENDED_RETRY_HTTP_STATUSES",
    "AgentCapabilities",
    "AgentCard",
    "AgentCardFetchError",
    "Skill",
    "build_karasu_card",
    "fetch_card",
]
