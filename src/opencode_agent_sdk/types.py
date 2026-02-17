from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class AssistantMessage:
    content: list[TextBlock | ToolUseBlock]
    role: str = "assistant"


@dataclass
class ResultMessage:
    usage: dict[str, Any] = field(default_factory=dict)
    total_cost_usd: float = 0.0
    session_id: str = ""
    duration_ms: float = 0.0
    num_turns: int = 0
    is_error: bool = False


@dataclass
class SystemMessage:
    subtype: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookMatcher:
    matcher: str | None
    hooks: list[Callable[..., Any]]
    timeout: float = 30.0


# Type aliases matching claude_agent_sdk
HookInput = dict[str, Any]
HookContext = dict[str, Any]
HookJSONOutput = dict[str, Any]
