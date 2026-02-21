"""SDKClient and AgentOptions — public API matching claude_agent_sdk."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterable, AsyncIterator

from .types import (
    AssistantMessage,
    HookMatcher,
    ResultMessage,
    SystemMessage,
)
from ._errors import ProcessError

logger = logging.getLogger(__name__)


@dataclass
class AgentOptions:
    """Configuration for the SDK client, mirrors ClaudeAgentOptions."""

    cwd: str = "."
    model: str = ""
    provider_id: str = "anthropic"
    max_buffer_size: int = 10 * 1024 * 1024
    system_prompt: str = ""
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    plugins: list[dict[str, Any]] = field(default_factory=list)
    permission_mode: str = ""
    hooks: dict[str, list[HookMatcher]] = field(default_factory=dict)
    max_turns: int = 100
    resume: str | None = None
    # HTTP mode: set to opencode serve URL (e.g. "http://localhost:54321")
    # When set, uses HTTP transport instead of subprocess ACP.
    server_url: str = ""


class SDKClient:
    """Client matching the claude_agent_sdk.ClaudeSDKClient API.

    Supports two transport modes:
    - HTTP mode (server_url set): communicates with opencode serve via REST
    - Subprocess mode (default): spawns opencode acp via stdio JSON-RPC

    Usage::

        # HTTP mode
        client = SDKClient(options=AgentOptions(
            model="claude-haiku-4-5",
            server_url="http://localhost:54321",
        ))
        await client.connect()
        await client.query("Hello!")
        async for msg in client.receive_response():
            print(msg)
        await client.disconnect()
    """

    def __init__(self, options: AgentOptions) -> None:
        self._options = options
        self._transport: Any = None  # SubprocessTransport or HTTPTransport
        self._session: Any = None  # ACPSession (subprocess mode only)
        self._http_mode = bool(options.server_url)
        self._pending_parts: dict[str, Any] | None = None

    async def connect(self) -> None:
        """Connect to opencode — either via HTTP or subprocess ACP."""
        if self._http_mode:
            await self._connect_http()
        else:
            await self._connect_subprocess()

    async def _connect_http(self) -> None:
        """Connect via HTTP to a running opencode serve instance."""
        from ._internal.http_transport import HTTPTransport

        self._transport = HTTPTransport(base_url=self._options.server_url)
        await self._transport.connect(cwd=self._options.cwd)

    async def _connect_subprocess(self) -> None:
        """Spawn the opencode acp subprocess and initialize."""
        from ._internal.transport import SubprocessTransport
        from ._internal.acp import ACPSession

        self._transport = SubprocessTransport(cwd=self._options.cwd)
        await self._transport.connect()

        self._session = ACPSession(
            transport=self._transport,
            hooks=self._options.hooks,
        )

        # Start background reader before sending any requests
        await self._session.start_reader()

        # Protocol handshake
        await self._session.initialize()

        # Create or resume session
        mcp_servers = _build_mcp_servers(self._options.mcp_servers)

        if self._options.resume:
            await self._session.load_session(
                session_id=self._options.resume,
                cwd=self._options.cwd,
            )
        else:
            await self._session.new_session(
                cwd=self._options.cwd,
                mcp_servers=mcp_servers,
                model=self._options.model or None,
            )

    async def disconnect(self) -> None:
        """Shut down the transport and clean up."""
        if self._transport:
            await self._transport.close()
            self._transport = None
        self._session = None
        self._pending_parts = None

    async def query(self, prompt: str | AsyncIterable[Any]) -> None:
        """Send a user prompt.

        Args:
            prompt: Either a string or an async iterable yielding content blocks.
        """
        if self._transport is None:
            raise ProcessError("Not connected. Call connect() first.", exit_code=1)

        if isinstance(prompt, str):
            parts = [{"type": "text", "text": prompt}]
        else:
            parts = []
            async for item in prompt:
                if isinstance(item, str):
                    parts.append({"type": "text", "text": item})
                elif isinstance(item, dict):
                    parts.append(item)
                else:
                    parts.append({"type": "text", "text": str(item)})

        if self._http_mode:
            # HTTP mode: store parts; actual send happens in receive_response
            # via SSE streaming.
            self._pending_parts = {
                "parts": parts,
                "model_id": self._options.model,
                "provider_id": self._options.provider_id,
            }
        else:
            # Subprocess mode: send via ACP session
            if self._session is None:
                raise ProcessError("Not connected. Call connect() first.", exit_code=1)
            await self._session.prompt(parts)

    async def receive_response(
        self,
    ) -> AsyncIterator[SystemMessage | AssistantMessage | ResultMessage]:
        """Async generator yielding messages from the current response.

        Yields SystemMessage, AssistantMessage, and finally ResultMessage.
        """
        if self._transport is None:
            raise ProcessError("Not connected. Call connect() first.", exit_code=1)

        if self._http_mode:
            # Yield init system message
            yield SystemMessage(
                subtype="init",
                data={
                    "session_id": self._transport.session_id,
                    "model": self._options.model,
                    "cwd": self._options.cwd,
                },
            )

            # Stream response parts via SSE
            if self._pending_parts is not None:
                async for msg in self._transport.chat_stream(
                    **self._pending_parts,
                ):
                    yield msg
                self._pending_parts = None
        else:
            # Subprocess ACP mode
            if self._session is None:
                raise ProcessError("Not connected. Call connect() first.", exit_code=1)

            yield SystemMessage(
                subtype="init",
                data={
                    "session_id": self._session.session_id,
                    "model": self._options.model,
                    "cwd": self._options.cwd,
                },
            )

            async for msg in self._session.receive_messages():
                yield msg


def _build_mcp_servers(servers: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert the mcp_servers dict to ACP mcpServers format."""
    result = []
    for name, config in servers.items():
        if isinstance(config, dict):
            entry: dict[str, Any] = {"name": name}
            if "command" in config:
                entry["transport"] = "stdio"
                entry["command"] = config["command"]
                entry["args"] = config.get("args", [])
                entry["env"] = config.get("env", {})
            elif "url" in config:
                entry["transport"] = "sse"
                entry["url"] = config["url"]
            result.append(entry)
    return result
