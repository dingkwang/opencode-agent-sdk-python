from dataclasses import dataclass, field
from typing import Any, Iterable

@dataclass(frozen=True)
class RunResult:
    text: str
    raw: Any = None

@dataclass
class Policy:
    deny_file_substrings: list[str] = field(default_factory=lambda: ["/.env", ".env"])
    deny_bash_substrings: list[str] = field(default_factory=lambda: ["rm -rf", "sudo ", "curl | sh"])
    opencode_permission: dict[str, str] = field(default_factory=lambda: {
        "bash": "ask",
        "edit": "ask",
        "read": "allow",
    })
