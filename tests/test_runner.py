from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from opencode_agent_sdk.backends.base import RunResult
from opencode_agent_sdk import runner


class FakeBackend:
    def __init__(self, policy):
        self.policy = policy

    async def astart(self) -> None:
        return None

    async def arun(self, prompt: str) -> RunResult:
        return RunResult(text=f"handled: {prompt}", raw={"backend": "fake"})

    async def aclose(self) -> None:
        return None


class RunnerTests(unittest.TestCase):
    def test_run_agent_uses_selected_backend(self) -> None:
        with patch.object(runner, "ClaudeBackend", FakeBackend):
            result = asyncio.run(runner.run_agent("claude", "ping"))
        self.assertEqual(result.text, "handled: ping")

    def test_run_agent_rejects_unknown_backend(self) -> None:
        with self.assertRaises(ValueError):
            asyncio.run(runner.run_agent("unknown", "ping"))


if __name__ == "__main__":
    unittest.main()
