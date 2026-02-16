import anyio
# 通过手动切换这一行来实现 Seamless Switch
from opencode_agent_sdk.claude import Agent
# from opencode_agent_sdk.opencode import Agent

async def main():
    agent = Agent()
    async for message in agent.query("Hello!"):
        print(message.content[0].text)

if __name__ == "__main__":
    anyio.run(main)
