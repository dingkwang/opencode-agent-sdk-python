"""
OpenCode AI SDK Demo

Prerequisites:
  1. docker compose up -d  (starts opencode serve on localhost:54321)
  2. .env file with ANTHROPIC_API_KEY set

Usage:
  uv run python scripts/opencode_ai_demo.py
"""

import asyncio
from opencode_ai import AsyncOpencode


BASE_URL = "http://localhost:54321"


async def main():
    client = AsyncOpencode(base_url=BASE_URL)

    # 1. 查看可用 providers 和默认模型
    providers = await client.app.providers()
    print("=== Providers ===")
    for p in providers.providers:
        print(f"  {p.id}: models={list(p.models.keys())}...")
    print(f"  Defaults: {providers.default}")

    # 2. 创建 session
    r = await client._client.post("/session")
    session = r.json()
    sid = session["id"]
    print(f"\n=== Session created: {sid} ===")

    # 3. 发消息 (chat 可能因 opencode DecimalError bug 报错，但 LLM 调用已完成)
    print("\n=== Chat ===")
    try:
        response = await client.session.chat(
            id=sid,
            model_id="claude-haiku-4-5",
            provider_id="anthropic",
            parts=[{"type": "text", "text": "What is 2+2? Reply in one word only."}],
        )
        info = response.info if response.info and isinstance(response.info, dict) else {}
    except Exception as e:
        print(f"  Chat exception (may be non-fatal): {e}")
        info = {}

    # 4. 提取回复 (回复在 response.parts，元信息在 response.info)
    for part in response.parts:
        if part.get("type") == "text":
            print(f"  Claude: {part['text']}")

    print(f"  Model: {info.get('modelID')}")
    print(f"  Provider: {info.get('providerID')}")

    error = info.get("error")
    if error:
        print(f"  (non-fatal server error: {error.get('name', '')})")

    # 5. 获取消息历史
    print("\n=== Message History ===")
    messages = await client.session.messages(sid)
    for msg in messages:
        for part in msg.parts:
            if getattr(part, "type", None) == "text":
                msg_info = msg.info if isinstance(msg.info, dict) else {}
                role = msg_info.get("role", "unknown")
                print(f"  [{role}] {part.text}")

    # 6. 清理
    await client.session.delete(sid)
    print(f"\n=== Session {sid} deleted ===")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
