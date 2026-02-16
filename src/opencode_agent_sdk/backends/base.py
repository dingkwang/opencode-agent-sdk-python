from dataclasses import dataclass
from typing import Protocol, Any, Iterable

@dataclass(frozen=True)
class RunResult:
    text: str
    raw: Any = None

class AgentBackend(Protocol):
    async def astart(self) -> None: ...
    async def arun(self, prompt: str) -> RunResult: ...
    async def aclose(self) -> None: ...

@dataclass(frozen=True)
class ModelTarget:
    provider_id: str
    model_id: str

@dataclass
class Policy:
    deny_file_substrings: list[str] = None
    deny_bash_substrings: list[str] = None
    opencode_permission: dict[str, str] = None

    def __post_init__(self):
        if self.deny_file_substrings is None:
            self.deny_file_substrings = ["/.env", ".env"]
        if self.deny_bash_substrings is None:
            self.deny_bash_substrings = ["rm -rf", "sudo ", "curl | sh"]
        if self.opencode_permission is None:
            self.opencode_permission = {
                "bash": "ask",
                "edit": "ask",
                "read": "allow",
                "webfetch": "allow",
            }

    def match_any(self, s: str, needles: Iterable[str]) -> bool:
        return any(n in s for n in needles)
