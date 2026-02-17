import asyncio
from opencode_agent_sdk import ClaudeAgent, Policy, HookSet, PolicyViolation


def on_before_run(prompt: str) -> None:
    print(f"[hook] before_run: {prompt!r}")


def on_before_tool(tool_name: str, args) -> None:
    print(f"[hook] before_tool: {tool_name} {args}")


def on_after_run(result) -> None:
    print(f"[hook] after_run: backend={result.backend}, model={result.model}")


def on_error(exc: Exception) -> None:
    print(f"[hook] on_error: {exc}")


async def main():
    # Policy replaces the hook-based permission logic from Claude Agent SDK.
    # deny_bash_substrings blocks any bash command containing these patterns.
    policy = Policy(
        deny_bash_substrings=["foo.sh"],
    )

    hooks = HookSet(
        before_run=on_before_run,
        before_tool=on_before_tool,
        after_run=on_after_run,
        on_error=on_error,
    )

    agent = ClaudeAgent(policy=policy)

    # Test 1: Command with forbidden pattern (will be blocked by Policy)
    print("--- Test 1: blocked command ---")
    try:
        async for message in agent.query("Run the bash command: ./foo.sh --help"):
            print(message.text)
    except PolicyViolation as e:
        print(f"Blocked: {e}")

    print("\n" + "=" * 50 + "\n")

    # Test 2: Safe command that should work
    print("--- Test 2: safe command ---")
    async for message in agent.query(
        "Run the bash command: echo 'Hello from hooks example!'"
    ):
        print(message.text)


if __name__ == "__main__":
    asyncio.run(main())
