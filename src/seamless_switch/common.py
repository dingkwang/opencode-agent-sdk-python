from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Mapping, Protocol, TypeVar, runtime_checkable

DEFAULT_MODEL = "claude-3-5-sonnet-latest"
DEFAULT_BASE_URL = "http://127.0.0.1:4096"


class PolicyViolation(RuntimeError):
    """Raised when a tool call violates local safety policy."""


@dataclass(frozen=True)
class RunResult:
    text: str
    raw: Any = None
    backend: str = ""
    model: str = ""


BeforeRunHook = Callable[[str], None]
BeforeToolHook = Callable[[str, Mapping[str, Any]], None]
AfterRunHook = Callable[[RunResult], None]
OnErrorHook = Callable[[Exception], None]


@dataclass
class HookSet:
    before_run: BeforeRunHook | None = None
    before_tool: BeforeToolHook | None = None
    after_run: AfterRunHook | None = None
    on_error: OnErrorHook | None = None


@dataclass
class Policy:
    deny_file_substrings: list[str] = field(default_factory=lambda: ["/.env", ".env"])
    deny_bash_substrings: list[str] = field(default_factory=lambda: ["rm -rf", "sudo ", "curl | sh"])
    opencode_permission: dict[str, str] = field(
        default_factory=lambda: {
            "bash": "ask",
            "edit": "ask",
            "read": "allow",
            "webfetch": "allow",
        }
    )

    @staticmethod
    def _match_any(value: str, needles: Iterable[str]) -> bool:
        return any(needle in value for needle in needles)

    def assert_file_allowed(self, path: str) -> None:
        if self._match_any(path, self.deny_file_substrings):
            raise PolicyViolation(f"Denied file access by policy: {path}")

    def assert_bash_allowed(self, command: str) -> None:
        if self._match_any(command, self.deny_bash_substrings):
            raise PolicyViolation(f"Denied shell command by policy: {command}")

    def check_tool_call(self, tool_name: str, payload: Mapping[str, Any] | None) -> None:
        payload = payload or {}
        normalized = tool_name.lower()
        if normalized in {"bash", "shell", "terminal"}:
            command = first_string(payload, ("command", "cmd", "input"))
            if command:
                self.assert_bash_allowed(command)
        if normalized in {"read", "write", "edit", "open", "file"}:
            target_path = first_string(payload, ("path", "file", "filepath", "filename"))
            if target_path:
                self.assert_file_allowed(target_path)


@runtime_checkable
class AgentLike(Protocol):
    def run(self, prompt: str) -> RunResult: ...
    async def arun(self, prompt: str) -> RunResult: ...
    def close(self) -> None: ...
    async def aclose(self) -> None: ...


T = TypeVar("T")


def run_sync(coro: Awaitable[T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("run() cannot be called inside an active event loop. Use arun() instead.")


def first_string(payload: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def extract_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, Mapping):
        for key in ("text", "output_text", "output", "message", "result", "content"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                chunks = [part for part in value if isinstance(part, str)]
                if chunks:
                    return "\n".join(chunks)
        return str(raw)
    return str(raw)
