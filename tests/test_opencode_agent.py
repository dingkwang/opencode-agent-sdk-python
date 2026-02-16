from __future__ import annotations

import asyncio
import unittest

from opencode_agent_sdk.opencode import Agent


class FakeResponse:
    def __init__(self, payload, *, content_type: str = "application/json"):
        self._payload = payload
        self.headers = {"content-type": content_type}
        self.text = str(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.calls = []

    async def post(self, path, json):
        self.calls.append((path, json))
        if path == "/sessions":
            return FakeResponse({"id": "session-123"})
        if path == "/sessions/session-123/runs":
            return FakeResponse({"text": "remote completed"})
        raise AssertionError(f"Unexpected path: {path}")

    async def aclose(self) -> None:
        return None


class OpenCodeAgentTests(unittest.TestCase):
    def test_opencode_agent_roundtrip_with_fake_transport(self) -> None:
        client = FakeClient()
        agent = Agent(transport=client)

        result = asyncio.run(agent.arun("hello"))

        self.assertEqual(result.backend, "opencode")
        self.assertEqual(result.text, "remote completed")
        self.assertEqual(client.calls[0][0], "/sessions")
        self.assertEqual(client.calls[1][0], "/sessions/session-123/runs")


if __name__ == "__main__":
    unittest.main()
