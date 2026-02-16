from .common import Policy, RunResult

class Agent:
    def __init__(self, policy: Policy = None, base_url: str = "http://127.0.0.1:4096"):
        self.policy = policy or Policy()
        self.base_url = base_url
        print(f"[OpenCode Backend] Connected to {base_url}")

    def run(self, prompt: str) -> RunResult:
        print(f"[OpenCode] Using runtime-side plugins for Policy.")
        # 实际逻辑：通过 HTTP 调用 OpenCode Server
        return RunResult(text=f"OpenCode processed: {prompt}", raw={"backend": "opencode"})

    async def arun(self, prompt: str) -> RunResult:
        return self.run(prompt)
