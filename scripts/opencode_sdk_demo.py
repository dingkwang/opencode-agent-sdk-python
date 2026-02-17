import anyio
from opencode_agent_sdk.claude import Agent

async def main():
    agent = Agent()
    async for message in agent.query(prompt="What is 2 + 2?"):
        print(message)

anyio.run(main)
