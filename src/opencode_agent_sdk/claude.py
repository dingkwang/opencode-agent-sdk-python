from __future__ import annotations
from typing import AsyncIterator
from .types import AgentBackend, AssistantMessage, TextBlock, Policy

class Agent:
    def __init__(self, policy: Policy | None = None, model: str = "claude-3-5-sonnet-20241022"):
        self.policy = policy or Policy()
        self.model = model
        # 实际实现会导入 claude_agent_sdk.client.ClaudeSDKClient
        print(f"Initialized Claude Agent with model {model}")

    async def query(self, prompt: str) -> AsyncIterator[AssistantMessage]:
        # 模拟流式输出
        print(f"Claude executing: {prompt}")
        yield AssistantMessage(content=[TextBlock(text=f"Claude response to: {prompt}")])
