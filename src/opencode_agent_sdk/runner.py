from typing import AsyncGenerator
from contextlib import asynccontextmanager
from .backends.base import AgentBackend, Policy
from .backends.claude_backend import ClaudeBackend
from .backends.opencode_backend import OpenCodeBackend

class SeamlessAgent:
    def __init__(self, backend_type: str, policy: Policy = None):
        self.policy = policy or Policy()
        if backend_type == "claude":
            self.backend = ClaudeBackend(self.policy)
        elif backend_type == "opencode":
            self.backend = OpenCodeBackend(self.policy)
        else:
            raise ValueError(f"Unknown backend: {backend_type}")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AgentBackend, None]:
        await self.backend.astart()
        try:
            yield self.backend
        finally:
            await self.backend.aclose()

async def run_agent(backend_name: str, prompt: str):
    agent = SeamlessAgent(backend_name)
    async with agent.session() as backend:
        result = await backend.arun(prompt)
        return result
