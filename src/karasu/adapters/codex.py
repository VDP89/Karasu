"""Adapter for Codex acting as a GitHub PR reviewer."""

from __future__ import annotations

from typing import Iterable

import httpx

from karasu.adapters.base import AgentAdapter, AgentRequest, AgentResponse


class CodexAdapter(AgentAdapter):
    """Drive Codex through the GitHub API.

    The Phase 1 implementation is intentionally thin: it asks the
    GitHub API for the latest review on the configured repo and
    treats it as the agent response. The full review-request flow is
    Phase 2 work.
    """

    name = "codex"

    def __init__(
        self,
        repo: str,
        token: str | None = None,
        handles: Iterable[str] = ("code_review", "audit"),
        trust_level: int = 0,
        base_url: str = "https://api.github.com",
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(handles=handles, trust_level=trust_level)
        self.repo = repo
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._client = client

    def _http(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=30.0)

    def dispatch(self, request: AgentRequest) -> AgentResponse:
        if not self.repo:
            return AgentResponse(
                content="codex adapter has no repo configured",
                success=False,
                requires_human=True,
            )
        client = self._http()
        try:
            response = client.get(f"/repos/{self.repo}/pulls", params={"state": "open"})
            response.raise_for_status()
            pulls = response.json()
        except httpx.HTTPError as exc:
            return AgentResponse(
                content=f"GitHub request failed: {exc}",
                success=False,
                requires_human=True,
            )
        finally:
            if self._client is None:
                client.close()
        if not pulls:
            return AgentResponse(
                content="no open pull requests to review",
                success=True,
                requires_human=False,
            )
        summary = ", ".join(f"#{pr['number']} {pr['title']}" for pr in pulls[:5])
        return AgentResponse(
            content=f"open PRs awaiting review: {summary}",
            success=True,
            requires_human=True,
            metadata={"count": len(pulls)},
        )
