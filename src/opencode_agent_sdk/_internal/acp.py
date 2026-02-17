"""ACP (Agent Client Protocol) JSON-RPC handler.

Maps JSON-RPC 2.0 messages to/from opencode_agent_sdk types.
Handles requestPermission (PreToolUse hooks) and sessionUpdate notifications.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncIterator

from ..types import (
    AssistantMessage,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)
from .transport import SubprocessTransport

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = "2025-01-01"


class ACPSession:
    """Manages ACP JSON-RPC protocol over a SubprocessTransport."""

    def __init__(
        self,
        transport: SubprocessTransport,
        hooks: dict[str, list[HookMatcher]] | None = None,
    ) -> None:
        self._transport = transport
        self._hooks = hooks or {}
        self._session_id: str = ""
        self._request_id: int = 0

        # Message queues for routing
        self._response_futures: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._update_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None

        # State for accumulating streamed content
        self._text_buffer: str = ""
        self._tool_calls: dict[str, dict[str, Any]] = {}
        self._prompt_done: bool = False
        self._usage: dict[str, Any] = {}
        self._cost: dict[str, Any] = {}

    @property
    def session_id(self) -> str:
        return self._session_id

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response."""
        req_id = self._next_id()
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._response_futures[req_id] = future
        await self._transport.write(msg)
        return await future

    async def _send_response(self, req_id: Any, result: dict[str, Any]) -> None:
        """Send a JSON-RPC response (for server->client requests like requestPermission)."""
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }
        await self._transport.write(msg)

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._transport.write(msg)

    async def start_reader(self) -> None:
        """Start the background reader task that routes incoming messages."""
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """Read messages from transport and route them."""
        try:
            async for msg in self._transport.read_messages():
                await self._handle_message(msg)
        except Exception as exc:
            logger.debug("Reader loop ended: %s", exc)
        finally:
            # Signal end of stream
            await self._update_queue.put({"_eof": True})

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        """Route an incoming JSON-RPC message."""
        # Response to one of our requests
        if "id" in msg and ("result" in msg or "error" in msg):
            req_id = msg["id"]
            future = self._response_futures.pop(req_id, None)
            if future and not future.done():
                if "error" in msg:
                    future.set_exception(
                        RuntimeError(f"ACP error: {msg['error']}")
                    )
                else:
                    future.set_result(msg.get("result", {}))
            return

        method = msg.get("method", "")

        # Server->Client request: requestPermission
        if method == "requestPermission" and "id" in msg:
            await self._handle_permission_request(msg)
            return

        # Notification: sessionUpdate
        if method == "sessionUpdate":
            params = msg.get("params", {})
            await self._update_queue.put(params)
            return

        logger.debug("Unhandled message: %s", msg)

    async def _handle_permission_request(self, msg: dict[str, Any]) -> None:
        """Handle requestPermission from the server, run PreToolUse hooks."""
        req_id = msg["id"]
        params = msg.get("params", {})
        tool_call = params.get("toolCall", {})
        tool_name = tool_call.get("title", "")
        tool_input = tool_call.get("rawInput", {})
        tool_call_id = tool_call.get("toolCallId", str(uuid.uuid4()))
        options = params.get("options", [])

        # Default: allow once
        decision_option_id = "once"
        for opt in options:
            if opt.get("kind") == "allow_once":
                decision_option_id = opt.get("optionId", "once")
                break

        # Run PreToolUse hooks if any
        pre_tool_hooks = self._hooks.get("PreToolUse", [])
        for hook_matcher in pre_tool_hooks:
            # Check if matcher matches tool name (None matches all)
            if hook_matcher.matcher is not None and hook_matcher.matcher != tool_name:
                continue

            hook_input = {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "session_id": self._session_id,
                "cwd": "",
            }
            hook_context = {
                "session_id": self._session_id,
                "tool_call_id": tool_call_id,
            }

            for hook_fn in hook_matcher.hooks:
                try:
                    result = hook_fn(hook_input, tool_call_id, hook_context)
                    if asyncio.iscoroutine(result):
                        result = await result

                    if isinstance(result, dict):
                        decision = result.get("permissionDecision", "")
                        if decision == "deny":
                            # Find reject option
                            for opt in options:
                                if opt.get("kind") == "reject_once":
                                    decision_option_id = opt.get("optionId", "reject")
                                    break
                            else:
                                decision_option_id = "reject"
                            break
                except Exception:
                    logger.exception("Hook error for tool %s", tool_name)

        await self._send_response(req_id, {
            "outcome": {
                "outcome": "selected",
                "optionId": decision_option_id,
            },
        })

    async def initialize(self) -> dict[str, Any]:
        """Send the initialize request."""
        result = await self._send_request("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "clientCapabilities": {},
        })
        logger.debug("Initialized: %s", result)
        return result

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> str:
        """Create a new ACP session. Returns the session ID."""
        params: dict[str, Any] = {
            "cwd": cwd,
            "mcpServers": mcp_servers or [],
        }
        result = await self._send_request("newSession", params)
        self._session_id = result.get("sessionId", "")
        logger.debug("New session: %s", self._session_id)
        return self._session_id

    async def load_session(self, session_id: str, cwd: str) -> str:
        """Resume an existing ACP session."""
        params: dict[str, Any] = {
            "sessionId": session_id,
            "cwd": cwd,
            "mcpServers": [],
        }
        result = await self._send_request("loadSession", params)
        self._session_id = result.get("sessionId", session_id)
        return self._session_id

    async def prompt(self, parts: list[dict[str, Any]]) -> None:
        """Send a prompt to the session. Response comes via sessionUpdate notifications."""
        self._text_buffer = ""
        self._tool_calls.clear()
        self._prompt_done = False
        self._usage = {}
        self._cost = {}

        result = await self._send_request("prompt", {
            "sessionId": self._session_id,
            "prompt": parts,
        })

        # prompt response indicates the turn is done
        self._prompt_done = True
        if "usage" in result:
            self._usage = result["usage"]
        if "stopReason" in result:
            self._usage["stop_reason"] = result["stopReason"]

        # Signal that prompt is done
        await self._update_queue.put({"_prompt_done": True, "_result": result})

    async def cancel(self) -> None:
        """Cancel the current operation."""
        await self._send_notification("cancel", {
            "sessionId": self._session_id,
        })

    async def receive_messages(self) -> AsyncIterator[SystemMessage | AssistantMessage | ResultMessage]:
        """Async generator yielding translated messages from sessionUpdate notifications."""
        while True:
            update = await self._update_queue.get()

            if update.get("_eof"):
                return

            if update.get("_prompt_done"):
                # Flush any accumulated text
                if self._text_buffer:
                    yield AssistantMessage(
                        content=[TextBlock(text=self._text_buffer)]
                    )
                    self._text_buffer = ""

                # Yield final result message
                result_data = update.get("_result", {})
                usage = result_data.get("usage", {})
                cost_amount = self._cost.get("amount", 0.0)

                yield ResultMessage(
                    usage=usage,
                    total_cost_usd=cost_amount,
                    session_id=self._session_id,
                    duration_ms=0.0,
                    num_turns=1,
                    is_error=False,
                )
                return

            session_update = update.get("update", update)
            update_type = session_update.get("sessionUpdate", "")

            if update_type == "agent_message_chunk":
                content = session_update.get("content", {})
                text = content.get("text", "")
                if text:
                    self._text_buffer += text

            elif update_type == "tool_call":
                tool_call_id = session_update.get("toolCallId", "")
                self._tool_calls[tool_call_id] = {
                    "id": tool_call_id,
                    "name": session_update.get("title", ""),
                    "input": session_update.get("rawInput", {}),
                    "status": session_update.get("status", "pending"),
                }

            elif update_type == "tool_call_update":
                tool_call_id = session_update.get("toolCallId", "")
                status = session_update.get("status", "")

                if tool_call_id in self._tool_calls:
                    self._tool_calls[tool_call_id]["status"] = status
                    self._tool_calls[tool_call_id]["input"] = session_update.get(
                        "rawInput", self._tool_calls[tool_call_id].get("input", {})
                    )

                if status in ("completed", "failed"):
                    # Flush text buffer before yielding tool use
                    if self._text_buffer:
                        yield AssistantMessage(
                            content=[TextBlock(text=self._text_buffer)]
                        )
                        self._text_buffer = ""

                    tc = self._tool_calls.get(tool_call_id, {})
                    yield AssistantMessage(
                        content=[
                            ToolUseBlock(
                                id=tool_call_id,
                                name=tc.get("name", session_update.get("title", "")),
                                input=tc.get("input", {}),
                            )
                        ]
                    )

            elif update_type == "usage_update":
                self._usage = {
                    "used": session_update.get("used", 0),
                    "size": session_update.get("size", 0),
                }
                cost = session_update.get("cost", {})
                if cost:
                    self._cost = cost

            elif update_type == "plan":
                yield SystemMessage(
                    subtype="plan",
                    data={"entries": session_update.get("entries", [])},
                )

            elif update_type == "agent_thought_chunk":
                content = session_update.get("content", {})
                text = content.get("text", "")
                if text:
                    yield SystemMessage(
                        subtype="thought",
                        data={"text": text},
                    )
