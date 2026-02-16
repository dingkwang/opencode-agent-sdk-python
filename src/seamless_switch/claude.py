from __future__ import annotations

import inspect
from typing import Any, Callable, Mapping

from .common import DEFAULT_BASE_URL, DEFAULT_MODEL, HookSet, Policy, RunResult, extract_text, run_sync


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
        self.base_url = base_url
        self.timeout = timeout
        self.hooks = hooks or HookSet()
        self._client = transport
        self._owns_client = transport is None
        self._client_factory = self._resolve_client_factory()

    @staticmethod
    def _resolve_client_factory() -> Callable[..., Any] | None:
        try:
            from claude_agent_sdk.client import ClaudeAgentClient  # type: ignore

            return ClaudeAgentClient
        except ImportError:
            return None

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._client_factory:
            raise RuntimeError(
                "claude-agent-sdk is not installed. Install it with "
                "`pip install claude-agent-sdk` or inject a transport client."
            )
        init_attempts = (
            {"model": self.model, "timeout": self.timeout},
            {"model": self.model},
            {},
        )
        for kwargs in init_attempts:
            try:
                self._client = self._client_factory(**kwargs)
                break
            except TypeError:
                continue
        if self._client is None:
            raise RuntimeError("Unable to initialize Claude SDK client with supported constructor arguments.")
        return self._client

    def _before_tool(self, tool_name: str, payload: Mapping[str, Any] | None) -> None:
        payload = payload or {}
        self.policy.check_tool_call(tool_name, payload)
        if self.hooks.before_tool:
            self.hooks.before_tool(tool_name, payload)

    async def _invoke(self, fn: Callable[..., Any], **kwargs: Any) -> Any:
        signature = inspect.signature(fn)
        accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        call_kwargs = kwargs if accepts_kwargs else {k: v for k, v in kwargs.items() if k in signature.parameters}
        result = fn(**call_kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def arun(self, prompt: str) -> RunResult:
        if self.hooks.before_run:
            self.hooks.before_run(prompt)

        client = await self._ensure_client()
        sdk_hooks = {"before_tool_use": self._before_tool, "before_tool": self._before_tool}
        try:
            if hasattr(client, "arun"):
                raw = await self._invoke(client.arun, prompt=prompt, model=self.model, hooks=sdk_hooks)
            elif hasattr(client, "run"):
                raw = await self._invoke(client.run, prompt=prompt, model=self.model, hooks=sdk_hooks)
            else:
                raise RuntimeError("Claude client does not expose `run` or `arun`.")
            result = RunResult(text=extract_text(raw), raw=raw, backend="claude", model=self.model)
            if self.hooks.after_run:
                self.hooks.after_run(result)
            return result
        except Exception as exc:
            if self.hooks.on_error:
                self.hooks.on_error(exc)
            raise

    def run(self, prompt: str) -> RunResult:
        return run_sync(self.arun(prompt))

    async def aclose(self) -> None:
        if self._client is None:
            return
        close_fn = getattr(self._client, "aclose", None)
        if callable(close_fn):
            close_result = close_fn()
            if inspect.isawaitable(close_result):
                await close_result
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
