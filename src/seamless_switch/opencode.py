from __future__ import annotations

from typing import Any

from .common import DEFAULT_BASE_URL, DEFAULT_MODEL, HookSet, Policy, RunResult, extract_text, run_sync

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency
    httpx = None  # type: ignore


class Agent:
    def __init__(
        self,
        policy: Policy | None = None,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        hooks: HookSet | None = None,
        transport: Any | None = None,
    ):
        self.policy = policy or Policy()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.hooks = hooks or HookSet()
        self._client = transport
        self._owns_client = transport is None
        self._session_id: str | None = None

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if httpx is None:
            raise RuntimeError("httpx is required for OpenCode agent. Install with `pip install httpx`.")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._client

    async def _request_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        client = await self._ensure_client()
        response = await client.post(path, json=payload)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return {"text": response.text}

    async def _ensure_session(self) -> str:
        if self._session_id:
            return self._session_id
        try:
            created = await self._request_json("/sessions", {"model": self.model})
        except Exception:
            created = {}
        session_id = str(created.get("id") or created.get("session_id") or "")
        self._session_id = session_id or "default"
        return self._session_id

    async def arun(self, prompt: str) -> RunResult:
        if self.hooks.before_run:
            self.hooks.before_run(prompt)

        session_id = await self._ensure_session()
        payload = {
            "prompt": prompt,
            "input": prompt,
            "model": self.model,
            "session_id": session_id,
            "permissions": self.policy.opencode_permission,
        }
        self.policy.check_tool_call("bash", {"command": prompt})
        if self.hooks.before_tool:
            self.hooks.before_tool("remote_run", payload)

        last_error: Exception | None = None
        routes = [f"/sessions/{session_id}/runs", f"/sessions/{session_id}/messages", "/run"]
        raw: dict[str, Any] | None = None
        for route in routes:
            try:
                raw = await self._request_json(route, payload)
                break
            except Exception as exc:  # pragma: no cover - route probing
                last_error = exc
        if raw is None:
            if self.hooks.on_error and last_error:
                self.hooks.on_error(last_error)
            if last_error:
                raise last_error
            raise RuntimeError("OpenCode request failed for unknown reasons.")

        result = RunResult(text=extract_text(raw), raw=raw, backend="opencode", model=self.model)
        if self.hooks.after_run:
            self.hooks.after_run(result)
        return result

    def run(self, prompt: str) -> RunResult:
        return run_sync(self.arun(prompt))

    async def aclose(self) -> None:
        if self._client is None:
            return
        close_fn = getattr(self._client, "aclose", None)
        if callable(close_fn):
            await close_fn()
        elif callable(getattr(self._client, "close", None)):
            self._client.close()
        if self._owns_client:
            self._client = None

    def close(self) -> None:
        run_sync(self.aclose())

    async def __aenter__(self) -> "Agent":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    def __enter__(self) -> "Agent":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
