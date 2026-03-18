"""Debug script: capture raw LLM output to inspect think-tag format."""
import asyncio
import re
from opentower.llm.client import LLMClient

async def test():
    llm = LLMClient()
    msgs = [
        {"role": "system", "content": "Return only JSON: {\"verdict\": \"APPROVE\", \"reason\": \"ok\", \"suggestion\": null}"},
        {"role": "user", "content": "Is 2+2=4? Answer in the JSON format above."}
    ]
    text, usage = await llm.chat(msgs, max_tokens=512)
    print("=== RAW ===")
    print(repr(text[:500]))
    print("=== STRIPPED ===")
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    print(repr(stripped[:500]))
    print("=== HAS THINK ===")
    print("<think>" in text)
    print("</think>" in text)

asyncio.run(test())
