"""
E2E test: connect to opencode serve, ask the LLM to clone a repo and explain it.

Usage:
  1. docker compose up -d opencode
  2. uv run python scripts/e2e_test.py
"""

from __future__ import annotations

import asyncio
import sys
import os

from opencode_agent_sdk import (
    AgentOptions,
    AssistantMessage,
    ResultMessage,
    SDKClient,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)

SERVER_URL = os.environ.get("OPENCODE_SERVER_URL", "http://127.0.0.1:54321")


async def main() -> None:
    print("=" * 60)
    print("E2E Test: Clone repo & explain project")
    print("=" * 60)
    print(f"Server: {SERVER_URL}\n")

    options = AgentOptions(
        cwd="/tmp",
        model="claude-haiku-4-5",
        provider_id="anthropic",
        server_url=SERVER_URL,
        max_turns=10,
    )

    client = SDKClient(options=options)

    # -- Connect --
    print("[*] Connecting ...")
    try:
        await client.connect()
    except Exception as exc:
        print(f"[!] connect() failed: {exc}")
        sys.exit(1)
    print("[*] Connected.\n")

    # -- Query --
    prompt = (
        "Clone the repo https://github.com/dingkwang/opencode-agent-sdk-python "
        "and then explain what the project does. "
        "Give a concise summary of its purpose, architecture, and key components."
    )
    print(f"[>] Prompt:\n{prompt}\n")
    print("-" * 60)

    try:
        await client.query(prompt)
    except Exception as exc:
        print(f"[!] query() failed: {exc}")
        await client.disconnect()
        sys.exit(1)

    # -- Receive response --
    msg_counts = {"system": 0, "assistant": 0, "result": 0}
    try:
        async for msg in client.receive_response():
            if isinstance(msg, SystemMessage):
                msg_counts["system"] += 1
                print(f"\n  [system:{msg.subtype}]", end="")
                if msg.subtype == "tool_result":
                    output = msg.data.get("output", "")
                    tool = msg.data.get("tool_name", "")
                    preview = output[:200] + "..." if len(output) > 200 else output
                    print(f" {tool} -> {preview}")
                else:
                    print()

            elif isinstance(msg, AssistantMessage):
                msg_counts["assistant"] += 1
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(f"\n  [assistant]\n{block.text}")
                    elif isinstance(block, ToolUseBlock):
                        print(f"\n  [tool_use] {block.name}({block.input})")

            elif isinstance(msg, ResultMessage):
                msg_counts["result"] += 1
                print(f"\n{'=' * 60}")
                print(f"  [result] session  = {msg.session_id}")
                print(f"           cost     = ${msg.total_cost_usd:.6f}")
                print(f"           turns    = {msg.num_turns}")
                print(f"           is_error = {msg.is_error}")
                print(f"{'=' * 60}")

    except Exception as exc:
        print(f"\n[!] receive_response() error: {exc}")
        import traceback
        traceback.print_exc()

    # -- Disconnect --
    await client.disconnect()

    # -- Summary --
    print(f"\n[*] Message counts: {msg_counts}")
    print("[*] E2E test complete.")

    if msg_counts["result"] == 0:
        print("[!] WARNING: No ResultMessage received — possible issue.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
