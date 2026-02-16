from .base import AgentBackend, RunResult, Policy

class ClaudeBackend(AgentBackend):
    def __init__(self, policy: Policy, model_id: str = "claude-3-5-sonnet-latest"):
        self.policy = policy
        self.model_id = model_id
        self._client = None
        # 注意：这里需要导入官方 SDK，如果环境未安装会报错
        try:
            from claude_agent_sdk.client import ClaudeAgentClient
            self.ClaudeAgentClient = ClaudeAgentClient
        except ImportError:
            self.ClaudeAgentClient = None

    async def astart(self) -> None:
        if not self.ClaudeAgentClient:
            print("Warning: claude-agent-sdk not installed.")
            return
        
        # 初始化的伪代码实现逻辑：设置钩子
        # 在实际 SDK 中，我们会在这里通过 hooks 注入 policy 检查
        print(f"Starting Claude Backend with model {self.model_id}...")

    async def arun(self, prompt: str) -> RunResult:
        # 这里模拟 SDK 的运行流程并应用 Policy 钩子
        # 逻辑：在执行 Tool 前，检查 args 是否命中 policy.deny_file/bash_substrings
        print(f"Claude agent thinking: {prompt}")
        # 示例输出
        return RunResult(text="Claude finished execution safely.", raw={"backend": "claude"})

    async def aclose(self) -> None:
        print("Closing Claude Backend.")
