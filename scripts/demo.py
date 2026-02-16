import asyncio
import argparse
import sys
import os

# 将 src 目录加入路径以便本地测试运行
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from seamless_switch.runner import run_agent

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
