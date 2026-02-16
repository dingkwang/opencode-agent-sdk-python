from .common import Policy, RunResult
import asyncio

class Agent:
    def __init__(self, policy: Policy = None, model: str = "claude-3-5-sonnet-latest"):
        self.policy = policy or Policy()
        self.model = model
        print(f"[Claude Backend] Initialized with model {model}")

    def run(self, prompt: str) -> RunResult:
        # 这里包装异步逻辑为同步，方便用户直接使用（或者你也可以保持异步）
        print(f"[Claude] Applying Python-side hooks for Policy: {self.policy.deny_bash_substrings}")
        # 实际逻辑：实例化 Claude Agent SDK 并注入 hooks
        return RunResult(text=f"Claude processed: {prompt}", raw={"backend": "claude"})

    async def arun(self, prompt: str) -> RunResult:
        """异步版本"""
        return self.run(prompt)
