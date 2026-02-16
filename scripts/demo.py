import asyncio
import argparse
import sys
import os

# Add src directory to path for local script execution.
sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from opencode_agent_sdk.runner import run_agent

async def main():
    parser = argparse.ArgumentParser(description="Seamless Switch Demo")
    parser.add_argument("--backend", choices=["claude", "opencode"], default="claude")
    parser.add_argument("--prompt", type=str, default="Check the git status of this repo")
    args = parser.parse_args()

    print(f"--- Running with {args.backend.upper()} backend ---")
    result = await run_agent(args.backend, args.prompt)
    print(f"\nFinal Result:\n{result.text}")

if __name__ == "__main__":
    asyncio.run(main())
