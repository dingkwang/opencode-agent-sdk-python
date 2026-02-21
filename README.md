# OpenCode Agent SDK for Python

Python SDK for building agents backed by [OpenCode](https://github.com/nichochar/opencode). Drop-in replacement for `claude_agent_sdk` with support for any LLM provider (Anthropic, OpenAI, xAI, etc.).

<video src="https://github.com/user-attachments/assets/061fb862-3253-46aa-92a7-71dc9258960a"
       autoplay
       muted
       loop
       playsinline
       controls>
</video>

## Installation

```bash
pip install opencode-agent-sdk
```

**Prerequisites:**

- Python 3.10+
- An OpenCode server (`opencode serve`) **or** the `opencode` CLI installed locally

## Quick Start

```python
import asyncio
from opencode_agent_sdk import SDKClient, AgentOptions, AssistantMessage, TextBlock

async def main():
    client = SDKClient(options=AgentOptions(
        model="claude-haiku-4-5",
        server_url="http://localhost:54321",
    ))

    await client.connect()
    await client.query("What is 2 + 2?")

    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)

    await client.disconnect()

asyncio.run(main())
```

## SDKClient

`SDKClient` supports bidirectional conversations with an LLM via OpenCode. It works in two transport modes:

- **HTTP mode** — communicates with a running `opencode serve` instance over REST
- **Subprocess mode** — spawns `opencode acp` locally over stdio JSON-RPC

### HTTP Mode (recommended)

Start the server, then connect:

```bash
docker compose up -d   # starts opencode serve on port 54321
```

```python
from opencode_agent_sdk import SDKClient, AgentOptions

client = SDKClient(options=AgentOptions(
    model="claude-haiku-4-5",
    server_url="http://localhost:54321",
    system_prompt="You are a helpful assistant",
))

await client.connect()
await client.query("Hello!")

async for msg in client.receive_response():
    print(msg)

await client.disconnect()
```

### Subprocess Mode

When `server_url` is not set, the SDK spawns `opencode acp` as a child process:

```python
client = SDKClient(options=AgentOptions(
    cwd="/path/to/project",
    model="claude-haiku-4-5",
))
```

### Resuming Sessions

```python
options = AgentOptions(
    resume="session-id-from-previous-run",
    server_url="http://localhost:54321",
)
```

## AgentOptions

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cwd` | `str` | `"."` | Working directory |
| `model` | `str` | `""` | Model identifier (e.g. `"claude-haiku-4-5"`) |
| `provider_id` | `str` | `"anthropic"` | Provider identifier |
| `system_prompt` | `str` | `""` | System prompt for the LLM |
| `server_url` | `str` | `""` | OpenCode server URL; enables HTTP mode when set |
| `mcp_servers` | `dict` | `{}` | MCP server configurations |
| `allowed_tools` | `list[str]` | `[]` | Tools the agent is allowed to use |
| `permission_mode` | `str` | `""` | Permission mode for tool execution |
| `hooks` | `dict` | `{}` | Hook matchers keyed by event type |
| `max_turns` | `int` | `100` | Maximum conversation turns |
| `resume` | `str \| None` | `None` | Session ID to resume |

## Custom Tools (MCP Servers)

Define tools as Python functions and expose them as in-process MCP servers:

```python
from opencode_agent_sdk import tool, create_sdk_mcp_server, SDKClient, AgentOptions

@tool("greet", "Greet a user", {"type": "object", "properties": {"name": {"type": "string"}}})
def greet_user(args):
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}

server = create_sdk_mcp_server("my-tools", tools=[greet_user])

client = SDKClient(options=AgentOptions(
    mcp_servers={"my-tools": server},
    allowed_tools=["mcp__my-tools__greet"],
    server_url="http://localhost:54321",
))
```

You can mix in-process SDK servers with external MCP servers:

```python
options = AgentOptions(
    mcp_servers={
        "internal": sdk_server,          # In-process SDK server
        "external": {                    # External stdio server
            "command": "external-server",
            "args": ["--port", "8080"],
        },
    }
)
```

## Hooks

Hooks let you intercept and control tool execution. They run deterministically at specific points in the agent loop.

```python
from opencode_agent_sdk import SDKClient, AgentOptions, HookMatcher

async def check_bash_command(input_data, tool_use_id, context):
    tool_input = input_data["tool_input"]
    command = tool_input.get("command", "")

    if "rm -rf" in command:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Destructive command blocked",
            }
        }
    return {}

options = AgentOptions(
    allowed_tools=["Bash"],
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[check_bash_command]),
        ],
    },
    server_url="http://localhost:54321",
)

client = SDKClient(options=options)
await client.connect()
await client.query("Run: echo hello")

async for msg in client.receive_response():
    print(msg)

await client.disconnect()
```

Hook event types: `"PreToolUse"`, `"Stop"`

## Types

See [src/opencode_agent_sdk/types.py](src/opencode_agent_sdk/types.py) for complete type definitions:

- `AssistantMessage` — LLM response containing `TextBlock` and/or `ToolUseBlock`
- `ResultMessage` — Final message with usage stats, cost, and session info
- `SystemMessage` — Internal events (init, tool results, thoughts)
- `TextBlock` — Text content from the LLM
- `ToolUseBlock` — Tool invocation with name and input
- `HookMatcher` — Matches tool names to hook functions

## Error Handling

```python
from opencode_agent_sdk._errors import ProcessError

try:
    await client.connect()
except ProcessError as e:
    print(f"Failed with exit code: {e.exit_code}")
```

## Migrating from claude_agent_sdk

This SDK mirrors the `claude_agent_sdk` API. Migration requires renaming imports:

```python
# Before (claude_agent_sdk)
from claude_agent_sdk import (
    ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage,
    ResultMessage, SystemMessage, TextBlock, ToolUseBlock, HookMatcher,
)
from claude_agent_sdk._errors import ProcessError

# After (opencode_agent_sdk)
from opencode_agent_sdk import (
    AgentOptions, SDKClient, AssistantMessage,
    ResultMessage, SystemMessage, TextBlock, ToolUseBlock, HookMatcher,
)
from opencode_agent_sdk._errors import ProcessError
```

All method calls, message types, hooks, and tool decorators stay the same. Only the class names change:

| claude_agent_sdk | opencode_agent_sdk |
|------------------|-------------------|
| `ClaudeSDKClient` | `SDKClient` |
| `ClaudeAgentOptions` | `AgentOptions` |

## Demo: End-to-End Walkthrough

A full working demo that connects to `opencode serve`, sends a prompt to clone a GitHub repo, and streams the LLM response back through the SDK.

### 1. Configure API keys

Create a `.env` file in the project root with your provider key:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Start the server

```bash
docker compose up -d opencode
```

This builds and starts the `opencode serve` container on port 54321.

### 3. Install dependencies

```bash
uv sync
```

### 4. Run the E2E demo

```bash
uv run python scripts/e2e_test.py
```

### Expected output

```
============================================================
E2E Test: Clone repo & explain project
============================================================
Server: http://127.0.0.1:54321

[*] Connecting ...
[*] Connected.

[>] Prompt:
Clone the repo https://github.com/dingkwang/opencode-agent-sdk-python and then
explain what the project does. Give a concise summary of its purpose,
architecture, and key components.

------------------------------------------------------------

  [system:init]
  [system:step_start]

  [assistant]
  ## opencode-agent-sdk-python
  ### Purpose
  An open-source Python SDK that serves as a drop-in replacement for Anthropic's
  proprietary `claude_agent_sdk`. It delegates all LLM work to OpenCode — an
  open-source headless server that supports any provider ...
  ...

============================================================
  [result] session  = ses_...
           cost     = $0.024723
           turns    = 1
           is_error = False
============================================================

[*] Message counts: {'system': 2, 'assistant': 1, 'result': 1}
[*] E2E test complete.
```

### What's happening

1. `SDKClient` creates an HTTP session against `opencode serve`
2. `query()` sends the user prompt via `POST /session/{id}/message`
3. `receive_response()` yields typed messages: `SystemMessage` (init, step events), `AssistantMessage` (LLM text/tool calls), and `ResultMessage` (cost, session ID, turn count)
4. `disconnect()` cleans up the session

### Customizing the demo

Set a custom server URL via environment variable:

```bash
OPENCODE_SERVER_URL=http://your-host:54321 uv run python scripts/e2e_test.py
```

## Running with Docker

```bash
# Start opencode serve
docker compose up -d

# Run the integration test
docker compose run --rm test
```

The Docker setup uses `opencode-ai` v1.2.6 and exposes the REST API on port 54321. Pass provider API keys via `.env` (e.g. `ANTHROPIC_API_KEY`).

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run demo against a running opencode serve
uv run python scripts/opencode_ai_demo.py

# Interactive multi-turn chat
uv run python scripts/chat.py
```

## License

MIT
