"""HTTP transport for opencode serve / opencode acp REST API.

Manages session lifecycle and chat communication over HTTP,
translating opencode REST responses into SDK message types.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import httpx

from .._errors import ProcessError
from ..types import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)

logger = logging.getLogger(__name__)


class HTTPTransport:
    """Communicates with opencode serve via its REST API."""

    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={"Accept": "application/json"},
        )
        self._session_id: str = ""

    @property
    def session_id(self) -> str:
        return self._session_id

    async def connect(self, cwd: str | None = None) -> None:
        """Create a new session on the opencode server."""
        resp = await self._client.post("/session")
        resp.raise_for_status()
        data = resp.json()
        self._session_id = data["id"]
        logger.debug("Created session: %s", self._session_id)

    async def chat(
        self,
        parts: list[dict[str, Any]],
        model_id: str = "",
        provider_id: str = "anthropic",
    ) -> list[dict[str, Any]]:
        """Send a chat message and return the response parts."""
        if not self._session_id:
            raise ProcessError("No session. Call connect() first.", exit_code=1)

        body: dict[str, Any] = {
            "parts": parts,
        }
        if model_id:
            body["modelID"] = model_id
        if provider_id:
            body["providerID"] = provider_id

        resp = await self._client.post(
            f"/session/{self._session_id}/message",
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("parts", [])

    async def get_messages(self) -> list[dict[str, Any]]:
        """Retrieve message history for the current session."""
        if not self._session_id:
            return []

        resp = await self._client.get(f"/session/{self._session_id}/messages")
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Delete the session and close the HTTP client."""
        if self._session_id:
            try:
                await self._client.delete(f"/session/{self._session_id}")
            except Exception:
                logger.debug("Failed to delete session %s", self._session_id)
        await self._client.aclose()

    def translate_parts(
        self, parts: list[dict[str, Any]]
    ) -> list[SystemMessage | AssistantMessage | ResultMessage]:
        """Translate opencode response parts into SDK message types."""
        messages: list[SystemMessage | AssistantMessage | ResultMessage] = []

        for part in parts:
            part_type = part.get("type", "")

            if part_type == "text":
                messages.append(
                    AssistantMessage(content=[TextBlock(text=part.get("text", ""))])
                )

            elif part_type == "tool-invocation":
                tool_id = part.get("toolInvocationId", part.get("id", ""))
                tool_name = part.get("toolName", "")
                tool_input = part.get("input", {})
                messages.append(
                    AssistantMessage(
                        content=[
                            ToolUseBlock(
                                id=tool_id,
                                name=tool_name,
                                input=tool_input if isinstance(tool_input, dict) else {},
                            )
                        ]
                    )
                )

            elif part_type == "tool-result":
                tool_id = part.get("toolInvocationId", part.get("id", ""))
                tool_name = part.get("toolName", "")
                result_parts = part.get("result", [])
                result_text = ""
                if isinstance(result_parts, list):
                    for rp in result_parts:
                        if isinstance(rp, dict) and rp.get("type") == "text":
                            result_text += rp.get("text", "")
                elif isinstance(result_parts, str):
                    result_text = result_parts
                messages.append(
                    SystemMessage(
                        subtype="tool_result",
                        data={
                            "tool_name": tool_name,
                            "tool_id": tool_id,
                            "output": result_text,
                        },
                    )
                )

            elif part_type == "step-start":
                messages.append(
                    SystemMessage(subtype="step_start", data=part)
                )

            elif part_type == "step-finish":
                tokens = part.get("tokens", {})
                cost = part.get("cost", 0.0)
                messages.append(
                    ResultMessage(
                        usage=tokens,
                        total_cost_usd=cost,
                        session_id=part.get("sessionID", ""),
                        duration_ms=0.0,
                        num_turns=1,
                        is_error=False,
                    )
                )

        return messages
