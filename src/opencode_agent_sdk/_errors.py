from __future__ import annotations


class ProcessError(Exception):
    """Raised when the opencode subprocess exits with an error."""

    def __init__(self, message: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
