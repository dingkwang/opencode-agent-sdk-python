"""HTTP transport for opencode serve / opencode acp REST API.

Manages session lifecycle and chat communication over HTTP,
translating opencode REST responses into SDK message types.

Supports two modes:
- Blocking: POST /session/{id}/message → full JSON response
- Streaming: GET /event (SSE) + background POST → real-time parts
"""

from __future__ import annotations

import asyncio
import json
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

    # ------------------------------------------------------------------
    # Streaming via SSE
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        parts: list[dict[str, Any]],
        model_id: str = "",
        provider_id: str = "anthropic",
    ) -> AsyncIterator[SystemMessage | AssistantMessage | ResultMessage]:
        """Send a chat message and stream response events via SSE.

        Opens ``GET /event`` (SSE), fires ``POST /session/{id}/message``
        in the background, and yields SDK messages as parts arrive.
        """
        if not self._session_id:
            raise ProcessError("No session. Call connect() first.", exit_code=1)

        body: dict[str, Any] = {"parts": parts}
        if model_id:
            body["modelID"] = model_id
        if provider_id:
            body["providerID"] = provider_id

        seen_text: dict[str, str] = {}      # part_id → full text seen
        tool_states: dict[str, str] = {}    # part_id → last processed status
        session_id = self._session_id

        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(None, connect=10.0),
        ) as sse_client:
            async with sse_client.stream(
                "GET", "/event",
                headers={"Accept": "text/event-stream"},
            ) as sse_response:
                # Fire chat POST in the background
                send_task = asyncio.create_task(
                    self._client.post(
                        f"/session/{self._session_id}/message",
                        json=body,
                    )
                )

                try:
                    async for event in self._parse_sse(sse_response):
                        event_type = event.get("type", "")
                        props = event.get("properties", {})

                        if event_type == "message.part.updated":
                            part = props.get("part", {})
                            if part.get("sessionID") != session_id:
                                continue
                            msg = self._translate_sse_part(
                                part, seen_text, tool_states,
                            )
                            if msg is not None:
                                yield msg

                        elif event_type == "session.idle":
                            if props.get("sessionID") == session_id:
                                break

                        elif event_type == "session.error":
                            if props.get("sessionID") == session_id:
                                error = props.get("error")
                                name = "UnknownError"
                                if isinstance(error, dict):
                                    name = error.get("name", name)
                                raise ProcessError(
                                    f"Session error: {name}",
                                    exit_code=1,
                                )
                finally:
                    if not send_task.done():
                        send_task.cancel()
                    try:
                        await send_task
                    except (asyncio.CancelledError, Exception):
                        pass

    @staticmethod
    async def _parse_sse(
        response: httpx.Response,
    ) -> AsyncIterator[dict[str, Any]]:
        """Parse Server-Sent Events from an httpx streaming response."""
        data_lines: list[str] = []

        async for line in response.aiter_lines():
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif line == "":
                if data_lines:
                    raw = "\n".join(data_lines)
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        pass
                data_lines = []

    def _translate_sse_part(
        self,
        part: dict[str, Any],
        seen_text: dict[str, str],
        tool_states: dict[str, str],
    ) -> SystemMessage | AssistantMessage | ResultMessage | None:
        """Translate a single SSE part update into an SDK message."""
        part_type = part.get("type", "")
        part_id = part.get("id", "")

        if part_type == "text":
            full = part.get("text", "")
            prev = seen_text.get(part_id, "")
            delta = full[len(prev):]
            seen_text[part_id] = full
            if delta:
                return AssistantMessage(content=[TextBlock(text=delta)])

        elif part_type == "tool":
            state = part.get("state", {})
            status = state.get("status", "")
            prev_status = tool_states.get(part_id, "")
            tool_name = part.get("tool", "")

            if status == "running" and prev_status != "running":
                tool_states[part_id] = "running"
                tool_input = state.get("input")
                return AssistantMessage(
                    content=[
                        ToolUseBlock(
                            id=part.get("callID", part_id),
                            name=tool_name,
                            input=tool_input if isinstance(tool_input, dict) else {},
                        )
                    ]
                )

            if status == "completed" and prev_status != "completed":
                tool_states[part_id] = "completed"
                return SystemMessage(
                    subtype="tool_result",
                    data={
                        "tool_name": tool_name,
                        "tool_id": part.get("callID", part_id),
                        "output": state.get("output", ""),
                        "title": state.get("title", ""),
                        "input": state.get("input", {}),
                    },
                )

            if status == "error" and prev_status != "error":
                tool_states[part_id] = "error"
                return SystemMessage(
                    subtype="tool_error",
                    data={
                        "tool_name": tool_name,
                        "tool_id": part.get("callID", part_id),
                        "error": str(state),
                    },
                )

        elif part_type == "step-start":
            return SystemMessage(subtype="step_start", data=part)

        elif part_type == "step-finish":
            tokens = part.get("tokens", {})
            return ResultMessage(
                usage={
                    "input_tokens": int(tokens.get("input", 0)),
                    "output_tokens": int(tokens.get("output", 0)),
                },
                total_cost_usd=part.get("cost", 0.0),
                session_id=part.get("sessionID", self._session_id),
                duration_ms=0.0,
                num_turns=1,
                is_error=False,
            )

        return None

    # ------------------------------------------------------------------
    # Non-streaming (legacy)
    # ------------------------------------------------------------------

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
