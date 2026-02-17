from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any, AsyncIterator

import anyio
import anyio.abc

from .._errors import ProcessError

logger = logging.getLogger(__name__)


def _find_opencode_binary() -> str:
    """Find the opencode binary on the system."""
    # Check PATH first
    found = shutil.which("opencode")
    if found:
        return found

    # Check common locations
    candidates = [
        os.path.expanduser("~/.local/bin/opencode"),
        os.path.expanduser("~/.bun/bin/opencode"),
        "/usr/local/bin/opencode",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    raise ProcessError(
        "Could not find 'opencode' binary. "
        "Install it with: bun install -g opencode-ai",
        exit_code=127,
    )


class SubprocessTransport:
    """Manages the opencode acp subprocess and NDJSON communication."""

    def __init__(self, cwd: str = ".") -> None:
        self._cwd = os.path.abspath(cwd)
        self._process: anyio.abc.Process | None = None
        self._read_lock = anyio.Lock()

    async def connect(self) -> None:
        """Spawn the opencode acp subprocess."""
        binary = _find_opencode_binary()
        logger.debug("Spawning: %s acp --cwd %s", binary, self._cwd)

        self._process = await anyio.open_process(
            [binary, "acp", "--cwd", self._cwd],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    async def write(self, data: dict[str, Any]) -> None:
        """Write a JSON-RPC message (NDJSON line) to the subprocess stdin."""
        if self._process is None or self._process.stdin is None:
            raise ProcessError("Transport not connected", exit_code=1)

        line = json.dumps(data, separators=(",", ":")) + "\n"
        logger.debug(">>> %s", line.rstrip())
        await self._process.stdin.send(line.encode("utf-8"))

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        """Async generator reading NDJSON lines from subprocess stdout."""
        if self._process is None or self._process.stdout is None:
            raise ProcessError("Transport not connected", exit_code=1)

        buffer = b""
        async for chunk in self._process.stdout:
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    logger.debug("<<< %s", msg)
                    yield msg
                except json.JSONDecodeError:
                    logger.warning("Non-JSON line from subprocess: %s", line[:200])

    async def close(self) -> None:
        """Shut down the subprocess."""
        if self._process is None:
            return

        try:
            if self._process.stdin is not None:
                await self._process.stdin.aclose()
        except Exception:
            pass

        try:
            self._process.terminate()
        except ProcessLookupError:
            pass

        try:
            await self._process.wait()
        except Exception:
            pass

        self._process = None
