"""Quick smoke test: send a single intent through the full pipeline."""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)-28s | %(message)s", datefmt="%H:%M:%S")

from opentower.actions.registry import ActionRegistry
from opentower.actions.shell import register_shell_actions
from opentower.actions.github import register_github_actions
from opentower.agents.ceo import CEOAgent
from opentower.agents.worker import WorkerAgent
from opentower.agents.qa import QAAgent
from opentower.bus.event_bus import EMPBus
from opentower.llm.client import LLMClient
from opentower.memory.state_wall import StateWall
from opentower.schema.company import load_company
from opentower.schema.emp import EMPPacket, INTENT_USER_REQUEST, INTENT_QA_VERDICT


async def main():
    config = load_company(Path(__file__).parent / "company.yaml")
    bus = EMPBus()
    llm = LLMClient()
    state = StateWall(":memory:")
    await state.open()

    registry = ActionRegistry()
    register_shell_actions(registry)
    register_github_actions(registry)

    ceo = CEOAgent("ceo", config.nodes["ceo"], bus, llm, state)
    worker = WorkerAgent("worker", config.nodes["worker"], bus, llm, state, registry=registry)
    qa = QAAgent("qa", config.nodes["qa"], bus, llm, state)

    ceo.register()
    worker.register()
    qa.register()

    verdicts = []
    async def collect(pkt):
        verdicts.append(pkt)
    bus.subscribe(INTENT_QA_VERDICT, collect)

    await bus.start()

    # Send a simple intent
    pkt = EMPPacket(
        source="user",
        intent_type=INTENT_USER_REQUEST,
        action="列出当前目录的文件",
        token_budget=4096,
    )
    await bus.publish(pkt)

    # Wait for pipeline
    await asyncio.sleep(30)

    await bus.stop()
    await state.close()

    print("\n" + "=" * 60)
    print(f"VERDICTS RECEIVED: {len(verdicts)}")
    for v in verdicts:
        print(f"  [{v.payload.get('verdict')}] {v.payload.get('reason', '')[:100]}")
        result = v.payload.get("inspected_result", {})
        if "stdout" in result:
            print(f"  OUTPUT: {result['stdout'][:200]}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
