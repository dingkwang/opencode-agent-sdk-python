from __future__ import annotations
from typing import AsyncIterator
import httpx
from .types import AgentBackend, AssistantMessage, TextBlock, Policy

class Agent:
    def __init__(self, policy: Policy | None = None, base_url: str = "http://127.0.0.1:4096"):
        self.policy = policy or Policy()
        self.base_url = base_url
        print(f"Initialized OpenCode Agent connected to {base_url}")

    async def query(self, prompt: str) -> AsyncIterator[AssistantMessage]:
        # 模拟通过 HTTP 通讯
        print(f"OpenCode executing: {prompt}")
        yield AssistantMessage(content=[TextBlock(text=f"OpenCode response to: {prompt}")])
