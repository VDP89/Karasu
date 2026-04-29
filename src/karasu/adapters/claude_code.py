"""Adapter for the Claude Code CLI."""

from __future__ import annotations

import shlex
import subprocess
from typing import Iterable

from karasu.adapters.base import AgentAdapter, AgentRequest, AgentResponse


class ClaudeCodeAdapter(AgentAdapter):
    """Invoke the local ``claude`` CLI as a subprocess."""

    name = "claude_code"

    def __init__(
        self,
        command: str = "claude",
        handles: Iterable[str] = ("code_change", "bug_fix", "implementation"),
        trust_level: int = 1,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(handles=handles, trust_level=trust_level)
        self.command = command
        self.timeout = timeout

    def _build_argv(self, request: AgentRequest) -> list[str]:
        prompt = (
            f"Karasu dispatch: {request.classification} on {request.path} "
            f"(priority={request.priority})"
        )
        # -p / --print runs the CLI non-interactively. Without it the
        # subprocess opens an interactive session and blocks until the
        # adapter timeout. The flag is appended (not prepended) so a
        # user-supplied ``command`` can still override the executable
        # path without having to re-specify the print flag.
        return [*shlex.split(self.command), "-p", prompt]

    def dispatch(self, request: AgentRequest) -> AgentResponse:
        try:
            result = subprocess.run(
                self._build_argv(request),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            return AgentResponse(
                content=f"claude CLI not found: {exc}",
                success=False,
                requires_human=True,
            )
        except subprocess.TimeoutExpired:
            return AgentResponse(
                content="claude CLI timed out",
                success=False,
                requires_human=True,
            )
        return AgentResponse(
            content=result.stdout.strip(),
            success=result.returncode == 0,
            requires_human=result.returncode != 0,
            metadata={"stderr": result.stderr.strip(), "returncode": result.returncode},
        )
