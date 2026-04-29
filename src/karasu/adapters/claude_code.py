"""Adapter for the Claude Code CLI."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from typing import Iterable

from karasu.adapters.base import AgentAdapter, AgentRequest, AgentResponse


_PRINT_FLAGS = ("-p", "--print")


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
        # shlex.split's POSIX mode (default) treats backslashes as
        # escape characters. Windows paths embedded in ``command``
        # (e.g. ``C:\\Users\\me\\claude.CMD``) get corrupted unless the
        # caller quotes them. Switch to non-POSIX parsing on Windows
        # so backslashes survive.
        parts = shlex.split(self.command, posix=(os.name != "nt"))
        if not parts:
            raise ValueError("ClaudeCodeAdapter command cannot be empty")
        # subprocess.run with shell=False does not search PATH for
        # ``.cmd``/``.bat`` shims — npm installs ``claude`` as a CMD
        # shim on Windows, so the bare token ``claude`` raises
        # FileNotFoundError there. shutil.which performs the lookup
        # cross-platform and returns the absolute path of the resolved
        # executable (or None if the command is not on PATH). We swap
        # only the first token; if which() returns None the original
        # token is kept so the FileNotFoundError branch in dispatch()
        # still produces a clean failure response.
        resolved = shutil.which(parts[0])
        if resolved is not None:
            parts[0] = resolved
        # -p / --print runs the CLI non-interactively. Without it the
        # subprocess opens an interactive session and blocks until the
        # adapter timeout. If the user already supplied either form in
        # ``command`` we do not append a duplicate.
        if not any(token in _PRINT_FLAGS for token in parts):
            parts.append("-p")
        return [*parts, prompt]

    def dispatch(self, request: AgentRequest) -> AgentResponse:
        try:
            argv = self._build_argv(request)
        except ValueError as exc:
            return AgentResponse(
                content=str(exc),
                success=False,
                requires_human=True,
                metadata={"error": "config"},
            )
        try:
            result = subprocess.run(
                argv,
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
