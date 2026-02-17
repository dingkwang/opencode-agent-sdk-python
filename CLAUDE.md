# opencode-agent-sdk-python

## Project Purpose

API-compatible replacement for `claude_agent_sdk` backed by OpenCode (`opencode serve`).

Mirrors the `claude_agent_sdk` API pattern with OpenCode-native naming. Migration in `ai-oncall-bots` requires renaming the import + class names:

```python
# Before (claude_agent_sdk)
from claude_agent_sdk import (
    ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage,
    ResultMessage, SystemMessage, TextBlock, ToolUseBlock, HookMatcher,
)
from claude_agent_sdk._errors import ProcessError

# After (opencode_agent_sdk) — same API pattern, OpenCode names
from opencode_agent_sdk import (
    AgentOptions, SDKClient, AssistantMessage,
    ResultMessage, SystemMessage, TextBlock, ToolUseBlock, HookMatcher,
)
from opencode_agent_sdk._errors import ProcessError
```

Migration in ai-oncall-bots: rename `ClaudeAgentOptions` → `AgentOptions`, `ClaudeSDKClient` → `SDKClient`. All method calls, message types, hooks, and tool decorators stay the same.

## Name Mapping

| claude_agent_sdk | opencode_agent_sdk | Notes |
|------------------|-------------------|-------|
| `ClaudeSDKClient` | `SDKClient` | Same methods: `connect()`, `disconnect()`, `query()`, `receive_response()` |
| `ClaudeAgentOptions` | `AgentOptions` | Same fields: `cwd`, `model`, `system_prompt`, `hooks`, etc. |
| `AssistantMessage` | `AssistantMessage` | Unchanged |
| `ResultMessage` | `ResultMessage` | Unchanged |
| `SystemMessage` | `SystemMessage` | Unchanged |
| `TextBlock` | `TextBlock` | Unchanged |
| `ToolUseBlock` | `ToolUseBlock` | Unchanged |
| `HookMatcher` | `HookMatcher` | Unchanged |
| `ProcessError` | `ProcessError` | Unchanged |
| `@tool` | `@tool` | Unchanged |
| `create_sdk_mcp_server` | `create_sdk_mcp_server` | Unchanged |

## Why

1. `claude_agent_sdk` is closed-source (Anthropic proprietary)
2. `claude_agent_sdk` has poor support for non-Claude LLMs
3. OpenCode is open-source and supports any LLM provider (Anthropic, OpenAI, xAI, etc.)
4. Seamless migration — same API pattern, different backend

## Architecture

```
ai-oncall-bots
  └── import opencode_agent_sdk  (this project, drop-in for claude_agent_sdk)
        └── opencode-ai           (REST client for opencode serve)
              └── opencode serve  (headless HTTP server, runs in Docker)
                    └── Any LLM provider (Anthropic, OpenAI, xAI, etc.)
```

## Backend: opencode serve

- Runs in Docker via `docker compose up -d` (see `Dockerfile.opencode`, `docker-compose.yml`)
- Uses `opencode-ai` npm package v1.2.6+
- Exposes REST API on port 54321
- Supports direct LLM provider API calls (no opencode.ai proxy needed)
- Pass provider API keys via `.env` (e.g., `ANTHROPIC_API_KEY`)

## Python Client: opencode-ai

- Package: `opencode-ai` (installed via `uv add opencode-ai`)
- Auto-generated REST client (by Stainless) for opencode serve
- Lives in `external/opencode-sdk-python/` for reference
- Key APIs: `client.session.create()`, `client.session.chat()`, `client.session.messages()`

## API Surface to Implement

The following `claude_agent_sdk` API pattern must be replicated with OpenCode-native names:

### Core Classes

| Class | Key Properties/Methods |
|-------|----------------------|
| `SDKClient` | `__init__(options)`, `connect()`, `disconnect()`, `query(msg)`, `receive_response()` |
| `AgentOptions` | `cwd`, `model`, `max_buffer_size`, `system_prompt`, `mcp_servers`, `allowed_tools`, `plugins`, `permission_mode`, `hooks`, `max_turns`, `resume` |

### Message Types (yielded by `receive_response()`)

| Type | Properties |
|------|-----------|
| `SystemMessage` | `.subtype`, `.data` |
| `AssistantMessage` | `.content` → list of `TextBlock` / `ToolUseBlock` |
| `ResultMessage` | `.usage`, `.total_cost_usd`, `.session_id`, `.duration_ms`, `.num_turns`, `.is_error` |
| `TextBlock` | `.text` |
| `ToolUseBlock` | `.name`, `.input` |

### Hook System

| Type | Usage |
|------|-------|
| `HookMatcher` | `matcher` (str/None), `hooks` (list[callable]), `timeout` (float) |
| `HookInput` | dict-like, keys: `hook_event_name`, `tool_name`, `tool_input`, `session_id`, `transcript_path`, `cwd` |
| `HookContext` | dict-like context passed to hooks |
| `HookJSONOutput` | dict return with `hookSpecificOutput.hookEventName`, `permissionDecision`, `permissionDecisionReason`, `updatedInput` |

Hook event types: `"PreToolUse"`, `"Stop"`

### MCP Tools

| Function | Signature |
|----------|-----------|
| `@tool` | `@tool(name: str, description: str, input_schema: dict)` decorator |
| `create_sdk_mcp_server` | `create_sdk_mcp_server(name: str, version: str = None, tools: list = [])` |

### Errors

| Class | Module |
|-------|--------|
| `ProcessError` | `opencode_agent_sdk._errors` (has `.exit_code` attribute) |

## Development

```bash
# Install dependencies
uv sync

# Run opencode serve in Docker
docker compose up -d

# Run demo against opencode serve
uv run python scripts/opencode_ai_demo.py

# Use docker compose (not docker-compose)
```

## Working Demo

`scripts/opencode_ai_demo.py` — end-to-end demo using `opencode-ai` client directly against `opencode serve` in Docker. Verified working with Anthropic provider (claude-haiku-4-5) on opencode v1.2.6.
