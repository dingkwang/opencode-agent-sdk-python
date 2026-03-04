"""Bridge for running SDK MCP tools as HTTP servers.

Opencode expects MCP servers to be either subprocesses (stdio) or remote
HTTP/SSE servers.  SDK-defined tools (created via create_sdk_mcp_server)
have Python function handlers that must run in the same process.

This module bridges the gap by starting FastMCP HTTP servers in the SDK
process and returning remote URLs for opencode to connect to.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import socket
from typing import Any

logger = logging.getLogger(__name__)


def _find_free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class McpHttpBridge:
    """Hosts SDK MCP tools as HTTP servers for opencode consumption.

    For each SDK-defined MCP server (those with ``_tools`` in their config),
    starts a FastMCP HTTP server on a random port.  The config is then
    converted to a remote server pointing to ``http://127.0.0.1:<port>/mcp``
    so opencode can connect to it.
    """

    def __init__(self) -> None:
        self._servers: list[Any] = []  # uvicorn.Server instances
        self._tasks: list[asyncio.Task[None]] = []

    async def start_server(self, name: str) -> int:
        """Start an HTTP MCP server for the given tools.

        Args:
            name: MCP server name (must match a name registered via
                  create_sdk_mcp_server).

        Returns:
            The port the server is listening on.
        """
        from .tools import _TOOL_REGISTRY

        tool_handlers = _TOOL_REGISTRY.get(name, [])
        if not tool_handlers:
            raise ValueError(f"No tool handlers registered for MCP server '{name}'")

        from fastmcp import FastMCP
        from fastmcp.tools import Tool as FastMCPTool

        mcp_server = FastMCP(name)

        for sdk_tool in tool_handlers:
            wrapper = _make_wrapper(sdk_tool)
            mcp_server.add_tool(
                FastMCPTool.from_function(
                    wrapper,
                    name=sdk_tool.name,
                    description=sdk_tool.description,
                )
            )

        app = mcp_server.http_app(transport="streamable-http")
        port = _find_free_port()

        import uvicorn

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
        uv_server = uvicorn.Server(config)
        self._servers.append(uv_server)

        task = asyncio.create_task(uv_server.serve())
        self._tasks.append(task)

        # Wait briefly for the server to start accepting connections
        await asyncio.sleep(0.3)

        logger.info(
            "MCP HTTP bridge started: %s on port %d (%d tools)",
            name, port, len(tool_handlers),
        )
        return port

    async def stop_all(self) -> None:
        """Stop all running HTTP MCP servers."""
        for server in self._servers:
            server.should_exit = True
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._servers.clear()
        self._tasks.clear()
        logger.debug("All MCP HTTP bridges stopped")


def _make_wrapper(sdk_tool: Any) -> Any:
    """Create an async wrapper function that bridges SDK tool handler format.

    SDK tools accept ``args: dict[str, Any]`` and return
    ``{"content": [{"type": "text", "text": "..."}]}``.

    FastMCP expects typed keyword arguments and a return value that it
    serializes.  This function dynamically creates a wrapper with the
    correct signature derived from ``input_schema``.
    """
    schema = sdk_tool.input_schema or {}
    properties = schema.get("properties", {})
    handler = sdk_tool.handler

    # Build parameter list from input_schema properties
    params = []
    for prop_name, prop_def in properties.items():
        json_type = prop_def.get("type", "string")
        annotation = _json_type_to_python(json_type, prop_def)

        required = prop_name in schema.get("required", [])
        if required:
            params.append(
                inspect.Parameter(
                    prop_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=annotation,
                )
            )
        else:
            default = prop_def.get("default", None)
            params.append(
                inspect.Parameter(
                    prop_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=default,
                    annotation=annotation,
                )
            )

    async def wrapper(**kwargs: Any) -> str:
        result = await handler(kwargs)
        # Extract text from MCP content format
        if isinstance(result, dict) and "content" in result:
            texts = [
                c["text"]
                for c in result["content"]
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            return "\n".join(texts) if texts else str(result)
        return str(result)

    # Set signature AND annotations so FastMCP/Pydantic can introspect
    wrapper.__signature__ = inspect.Signature(params, return_annotation=str)
    wrapper.__name__ = sdk_tool.name
    wrapper.__doc__ = sdk_tool.description
    wrapper.__annotations__ = {p.name: p.annotation for p in params}
    wrapper.__annotations__["return"] = str

    return wrapper


def _json_type_to_python(json_type: str, prop_def: dict[str, Any]) -> type:
    """Map JSON Schema type to Python type annotation."""
    type_map: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }
    if json_type == "array":
        return list
    if json_type == "object":
        return dict
    return type_map.get(json_type, str)
