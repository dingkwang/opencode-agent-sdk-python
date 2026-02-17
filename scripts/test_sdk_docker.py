"""
Docker SDK Integration Test

Tests the opencode_agent_sdk end-to-end inside Docker:
  1. Connects to a running opencode serve instance via HTTP
  2. Asks the LLM to list files in /workspace
  3. Prints every message the SDK yields

The Docker entrypoint starts `opencode serve` in the background,
then runs this script against it.

Usage:
  docker compose up test
"""

from __future__ import annotations

import asyncio
import os
import sys

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
    print("opencode_agent_sdk  -  Docker integration test")
    print("=" * 60)
    print(f"Server: {SERVER_URL}")

    options = AgentOptions(
        cwd="/workspace",
        model="claude-haiku-4-5",
        provider_id="anthropic",
        server_url=SERVER_URL,
        max_turns=5,
    )

    client = SDKClient(options=options)

    # -- Connect ------------------------------------------------
    print("\n[*] Connecting ...")
    try:
        await client.connect()
    except Exception as exc:
        print(f"[!] connect() failed: {exc}")
        sys.exit(1)
    print("[*] Connected.\n")

    # -- Query --------------------------------------------------
    prompt = (
        "List all files and directories in the current working directory. "
        "Just show the filenames, one per line."
    )
    print(f"[>] Prompt: {prompt}\n")

    try:
        await client.query(prompt)
    except Exception as exc:
        print(f"[!] query() failed: {exc}")
        await client.disconnect()
        sys.exit(1)

    # -- Receive response ---------------------------------------
    try:
        async for msg in client.receive_response():
            if isinstance(msg, SystemMessage):
                print(f"  [system:{msg.subtype}]")

            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(f"  [assistant] {block.text}")
                    elif isinstance(block, ToolUseBlock):
                        print(f"  [tool_use]  {block.name}({block.input})")

            elif isinstance(msg, ResultMessage):
                print(f"\n  [result] session={msg.session_id}")
                print(f"           cost=${msg.total_cost_usd:.6f}")
                print(f"           turns={msg.num_turns}")
                print(f"           error={msg.is_error}")
    except Exception as exc:
        print(f"[!] receive_response() error: {exc}")

    # -- Disconnect ---------------------------------------------
    await client.disconnect()
    print("\n[*] Disconnected. Test complete.")


if __name__ == "__main__":
    asyncio.run(main())
