"""
Interactive terminal chat using opencode_agent_sdk.

Prerequisites:
  1. docker compose up -d opencode
  2. .env file with your provider API key (e.g. ANTHROPIC_API_KEY)

Usage:
  uv run python scripts/chat.py
  uv run python scripts/chat.py --model gpt-4o --server-url http://localhost:54321
"""

from __future__ import annotations

import argparse
import asyncio
import json
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Chat with an LLM via opencode serve")
    p.add_argument("--model", default="claude-haiku-4-5")
    p.add_argument(
        "--server-url",
        default=os.environ.get("OPENCODE_SERVER_URL", "http://127.0.0.1:54321"),
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    client = SDKClient(options=AgentOptions(
        model=args.model,
        server_url=args.server_url,
    ))

    print(f"Connecting to {args.server_url} (model: {args.model}) ...")
    await client.connect()
    print("Connected. Type 'exit' or 'quit' to end the session.\n")

    try:
        while True:
            try:
                user_input = input("You> ")
            except EOFError:
                break

            if user_input.strip().lower() in ("exit", "quit"):
                break
            if not user_input.strip():
                continue

            await client.query(user_input)

            in_text = False
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(block.text, end="", flush=True)
                            in_text = True
                        elif isinstance(block, ToolUseBlock):
                            if in_text:
                                print()
                                in_text = False
                            print(
                                f"\x1b[2m[tool: {block.name}"
                                f"({json.dumps(block.input)})]\x1b[0m"
                            )

                elif isinstance(msg, SystemMessage):
                    if msg.subtype == "tool_result":
                        if in_text:
                            print()
                            in_text = False
                        output = msg.data.get("output", "")
                        tool = msg.data.get("tool_name", "unknown")
                        if len(output) > 300:
                            output = output[:300] + "..."
                        print(f"\x1b[2m[{tool}] {output}\x1b[0m")

                elif isinstance(msg, ResultMessage):
                    if in_text:
                        print()
                        in_text = False
                    cost = (
                        f"${msg.total_cost_usd:.4f}"
                        if msg.total_cost_usd
                        else "n/a"
                    )
                    print(f"\x1b[2m({cost} | {msg.num_turns} turns)\x1b[0m")

            if in_text:
                print()
            print()

    except KeyboardInterrupt:
        print()

    print("Disconnecting ...")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
