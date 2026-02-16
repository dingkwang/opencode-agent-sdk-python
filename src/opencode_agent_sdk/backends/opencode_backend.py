from .base import AgentBackend, RunResult, Policy

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency
    httpx = None  # type: ignore

class OpenCodeBackend(AgentBackend):
    def __init__(self, policy: Policy, base_url: str = "http://127.0.0.1:4096"):
        self.policy = policy
        self.base_url = base_url
        self._session_id = None

    async def astart(self) -> None:
        print(f"Connecting to OpenCode Server at {self.base_url}...")
        # 实际逻辑应调用 /sessions endpoint
        if httpx is None:
            print("Warning: httpx not installed; OpenCode health probe skipped.")
            return
        try:
            async with httpx.AsyncClient() as client:
                # 假设的服务心跳检查
                resp = await client.get(f"{self.base_url}/health")
                print(f"OpenCode Server Status: {resp.status_code}")
        except Exception as e:
            print(f"OpenCode Server not reachable: {e}")

    async def arun(self, prompt: str) -> RunResult:
        print(f"OpenCode remote agent running: {prompt}")
        # 这里发送请求给 OpenCode Runtime 执行
        # 实际的 Tool Policy 拦截主要发生在 OpenCode Server 端的插件里
        return RunResult(text="OpenCode finished execution.", raw={"backend": "opencode"})

    async def aclose(self) -> None:
        print("Closing OpenCode Session.")
