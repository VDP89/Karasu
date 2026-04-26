"""Agent adapters.

Adapters are thin wrappers around the external agents Karasu
coordinates. ``base.AgentAdapter`` defines the abstract contract;
concrete adapters live alongside it in this package.
"""

from karasu.adapters.base import AgentAdapter, AgentRequest, AgentResponse
from karasu.adapters.claude_code import ClaudeCodeAdapter
from karasu.adapters.codex import CodexAdapter

__all__ = [
    "AgentAdapter",
    "AgentRequest",
    "AgentResponse",
    "ClaudeCodeAdapter",
    "CodexAdapter",
]
