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
        self._mcp_bridge: Any = None  # McpHttpBridge for SDK MCP servers

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

        # Start HTTP bridges for SDK-defined MCP servers (those with _tools).
        # SDK tools have Python function handlers that must run in-process.
        # We host them as HTTP MCP servers and tell opencode about them as
        # remote servers.
        effective_servers = dict(self._options.mcp_servers)
        sdk_servers = {
            name: cfg for name, cfg in effective_servers.items()
            if isinstance(cfg, dict) and "_tools" in cfg
        }
        if sdk_servers:
            from ._mcp_bridge import McpHttpBridge

            self._mcp_bridge = McpHttpBridge()
            for name in sdk_servers:
                port = await self._mcp_bridge.start_server(name)
                # Replace subprocess config with remote HTTP config
                effective_servers[name] = {
                    "url": f"http://127.0.0.1:{port}/mcp",
                }

        acp_mcp_servers = _build_mcp_servers(effective_servers)

        if self._options.resume:
            await self._session.load_session(
                session_id=self._options.resume,
                cwd=self._options.cwd,
                mcp_servers=acp_mcp_servers,
            )
        else:
            await self._session.new_session(
                cwd=self._options.cwd,
                mcp_servers=acp_mcp_servers,
                model=self._options.model or None,
                provider_id=self._options.provider_id or None,
                permission_mode=self._options.permission_mode,
                system_prompt=self._options.system_prompt,
            )

    def _build_init_data(self, session_id: str) -> dict[str, Any]:
        """Build the init SystemMessage data dict from options."""
        data: dict[str, Any] = {
            "session_id": session_id,
            "model": self._options.model,
            "cwd": self._options.cwd,
        }
        if self._options.plugins:
            data["plugins"] = self._options.plugins
        if self._options.mcp_servers:
            data["mcp_servers"] = list(self._options.mcp_servers.keys())
        return data

    async def disconnect(self) -> None:
        """Shut down the transport and clean up."""
        if self._mcp_bridge:
            await self._mcp_bridge.stop_all()
            self._mcp_bridge = None
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
                data=self._build_init_data(
                    session_id=self._transport.session_id,
                ),
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
                data=self._build_init_data(
                    session_id=self._session.session_id,
                ),
            )

            async for msg in self._session.receive_messages():
                yield msg


def _build_mcp_servers(servers: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert the mcp_servers dict to ACP mcpServers wire format.

    ACP distinguishes server types by the presence of a ``type`` field:
    - Local/stdio (no ``type``): ``{name, command, args, env}``
    - Remote (``type: "remote"``): ``{name, type, url, headers}``

    ``env`` and ``headers`` use ``[{name, value}]`` array format on the wire,
    not dict format.
    """
    result = []
    for name, config in servers.items():
        if not isinstance(config, dict):
            continue
        entry: dict[str, Any] = {"name": name}
        if "command" in config:
            # Local/stdio server — NO "type" field
            entry["command"] = config["command"]
            entry["args"] = config.get("args", [])
            # Convert env dict to [{name, value}] array
            raw_env = config.get("env", {})
            if isinstance(raw_env, dict):
                entry["env"] = [{"name": k, "value": v} for k, v in raw_env.items()]
            elif isinstance(raw_env, list):
                entry["env"] = raw_env
            else:
                entry["env"] = []
        elif "url" in config:
            # Remote server — has "type" field
            entry["type"] = "remote"
            entry["url"] = config["url"]
            raw_headers = config.get("headers", {})
            if isinstance(raw_headers, dict):
                entry["headers"] = [{"name": k, "value": v} for k, v in raw_headers.items()]
            elif isinstance(raw_headers, list):
                entry["headers"] = raw_headers
            else:
                entry["headers"] = []
        result.append(entry)
    return result
