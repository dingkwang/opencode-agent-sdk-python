from __future__ import annotations


class SDKError(Exception):
    """Base exception for all OpenCode Agent SDK errors."""
    pass


class ProcessError(SDKError):
    """Raised when the opencode subprocess exits with an error or fails to start."""
    def __init__(self, message: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class TransportError(SDKError):
    """Raised when there is a communication error with the OpenCode server."""
    pass


class SessionError(SDKError):
    """Raised when a session-related error occurs (e.g., missing session, expiration)."""
    pass


class ToolError(SDKError):
    """Raised when a tool execution hook fails or returns an error."""
    pass

