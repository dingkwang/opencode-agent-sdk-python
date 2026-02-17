"""MCP tool decorator and server creation, matching claude_agent_sdk API."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class SdkMcpTool:
    """A tool registered via the @tool decorator."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]


def tool(
    name: str,
    description: str,
    input_schema: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], SdkMcpTool]:
    """Decorator to create an MCP tool from a function.

    Usage::

        @tool(name="greet", description="Say hello", input_schema={"type": "object", "properties": {"name": {"type": "string"}}})
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    """

    def decorator(fn: Callable[..., Any]) -> SdkMcpTool:
        return SdkMcpTool(
            name=name,
            description=description,
            input_schema=input_schema or {"type": "object", "properties": {}},
            handler=fn,
        )

    return decorator


def create_sdk_mcp_server(
    name: str,
    version: str | None = None,
    tools: list[SdkMcpTool] | None = None,
) -> dict[str, Any]:
    """Create an MCP server configuration for use with AgentOptions.mcp_servers.

    For ACP, tools run in-process via a local stdio MCP server.
    This returns a config dict that SDKClient uses to spawn a Python
    MCP server subprocess hosting the given tools.

    Returns a dict suitable for ``AgentOptions.mcp_servers``::

        server = create_sdk_mcp_server("my-tools", tools=[my_tool])
        options = AgentOptions(mcp_servers={"my-tools": server})
    """
    tool_list = tools or []
    tool_defs = []
    for t in tool_list:
        tool_defs.append({
            "name": t.name,
            "description": t.description,
            "inputSchema": t.input_schema,
        })

    # Store tools for the in-process MCP server runner
    _TOOL_REGISTRY[name] = tool_list

    return {
        "command": sys.executable,
        "args": ["-m", "opencode_agent_sdk._mcp_runner", name],
        "_tools": tool_defs,
        "_version": version or "1.0.0",
    }


# Global registry for in-process tool serving
_TOOL_REGISTRY: dict[str, list[SdkMcpTool]] = {}
