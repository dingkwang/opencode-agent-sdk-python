from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, runtime_checkable

@dataclass(frozen=True)
class TextBlock:
    text: str
    type: str = "text"

@dataclass(frozen=True)
class AssistantMessage:
    content: list[TextBlock]
    role: str = "assistant"

@dataclass(frozen=True)
class RunResult:
    message: AssistantMessage
    raw: Any = None

    @property
    def text(self) -> str:
        return "".join(block.text for block in self.message.content if isinstance(block, TextBlock))

@runtime_checkable
class AgentBackend(Protocol):
    async def query(self, prompt: str) -> AsyncIterator[AssistantMessage]: ...

@dataclass
class Policy:
    deny_file_substrings: list[str] = field(default_factory=lambda: [".env"])
    deny_bash_substrings: list[str] = field(default_factory=lambda: ["rm -rf", "sudo"])
