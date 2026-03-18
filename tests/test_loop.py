"""Integration test — multi-tier agent loop (V2.0).

Tests the full Chairman → CEO → VP → TechLead → Worker → QA cascade
with mocked LLM responses.
"""

import asyncio
import json
import pytest
import aiosqlite

from opentower.actions.registry import ActionRegistry
from opentower.agents.manager import ManagerAgent
from opentower.agents.worker import WorkerAgent
from opentower.agents.qa import QAAgent
from opentower.bus.event_bus import EMPBus
from opentower.llm.client import LLMClient
from opentower.memory.node_memory import NodeMemory
from opentower.memory.state_wall import StateWall
from opentower.schema.company import NodeConfig
from opentower.schema.emp import (
    EMPPacket,
    INTENT_USER_REQUEST,
    INTENT_TASK_ASSIGN,
    INTENT_QA_VERDICT,
)


# ── Fixtures ────────────────────────────────────────────────────

def _make_config(level="worker", budget=4096):
    return NodeConfig(role="Test", prompt="You are a test agent.", token_budget=budget, level=level)


@pytest.fixture
def registry():
    reg = ActionRegistry()

    @reg.register("shell_execute")
    async def shell_execute(payload):
        return {"stdout": "mock output", "exit_code": 0}

    return reg


# ── Test: Multi-tier cascade ────────────────────────────────────

@pytest.mark.asyncio
async def test_two_tier_cascade(registry, monkeypatch):
    """Boss → Worker → QA with mocked LLM."""
    bus = EMPBus()
    state = StateWall(":memory:")
    await state.open()

    mem_db = await aiosqlite.connect(":memory:")

    # Mock LLM
    call_count = 0

    async def mock_chat(messages, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Boss decomposes → single task
            from opentower.llm.client import LLMUsage
            return json.dumps([{
                "action_type": "shell_execute",
                "description": "list files",
                "payload": {"command": "dir"},
                "target_subordinate": "worker_a",
            }]), LLMUsage(prompt=50, completion=50, total=100)
        else:
            # QA approves
            from opentower.llm.client import LLMUsage
            return json.dumps({
                "verdict": "APPROVE",
                "reason": "looks good",
                "suggestion": None,
            }), LLMUsage(prompt=50, completion=50, total=100)

    llm = LLMClient()
    monkeypatch.setattr(llm, "chat", mock_chat)

    # Build agents
    boss_mem = NodeMemory("boss", mem_db)
    await boss_mem.init()
    boss = ManagerAgent(
        "boss", _make_config("executive"), bus, llm, state,
        memory=boss_mem, subordinates=["worker_a"],
    )
    boss.register(listen_intents=[INTENT_USER_REQUEST, INTENT_TASK_ASSIGN])

    worker_mem = NodeMemory("worker_a", mem_db)
    await worker_mem.init()
    worker = WorkerAgent(
        "worker_a", _make_config("worker"), bus, llm, state,
        memory=worker_mem, registry=registry,
    )
    worker.register()

    qa_mem = NodeMemory("qa", mem_db)
    await qa_mem.init()
    qa = QAAgent("qa", _make_config("qa"), bus, llm, state, memory=qa_mem)
    qa.register()

    # Collect verdicts
    verdicts = []
    async def collect(pkt):
        verdicts.append(pkt)
    bus.subscribe(INTENT_QA_VERDICT, collect)

    await bus.start()

    # Send user intent
    pkt = EMPPacket(
        source="user", target="boss",
        intent_type=INTENT_USER_REQUEST,
        action="list files",
        payload={"intent": "list files", "original_intent": "list files"},
        token_budget=4096,
    )
    await bus.publish(pkt)
    await asyncio.sleep(0.5)

    await bus.stop()
    await state.close()
    await mem_db.close()

    assert len(verdicts) == 1
    assert verdicts[0].payload["verdict"] == "APPROVE"


@pytest.mark.asyncio
async def test_three_tier_cascade(registry, monkeypatch):
    """Chairman → Manager → Worker → QA with mocked LLM."""
    bus = EMPBus()
    state = StateWall(":memory:")
    await state.open()
    mem_db = await aiosqlite.connect(":memory:")

    call_count = 0

    async def mock_chat(messages, **kw):
        nonlocal call_count
        call_count += 1
        from opentower.llm.client import LLMUsage
        if call_count <= 2:
            # Managers decompose
            return json.dumps([{
                "action_type": "shell_execute" if call_count == 2 else "delegate",
                "description": "sub-task",
                "payload": {"command": "echo hello"} if call_count == 2 else {"intent": "do stuff"},
                "target_subordinate": "worker_x" if call_count == 2 else "mgr",
            }]), LLMUsage(prompt=50, completion=50, total=100)
        else:
            return json.dumps({
                "verdict": "APPROVE",
                "reason": "all good",
                "suggestion": None,
            }), LLMUsage(prompt=50, completion=50, total=100)

    llm = LLMClient()
    monkeypatch.setattr(llm, "chat", mock_chat)

    # Chairman → Manager → Worker
    for nid in ["chairman", "mgr", "worker_x", "qa"]:
        m = NodeMemory(nid, mem_db)
        await m.init()

    chairman_mem = NodeMemory("chairman", mem_db)
    chairman = ManagerAgent(
        "chairman", _make_config("executive"), bus, llm, state,
        memory=chairman_mem, subordinates=["mgr"],
    )
    chairman.register(listen_intents=[INTENT_USER_REQUEST, INTENT_TASK_ASSIGN])

    mgr_mem = NodeMemory("mgr", mem_db)
    mgr = ManagerAgent(
        "mgr", _make_config("middle"), bus, llm, state,
        memory=mgr_mem, subordinates=["worker_x"],
    )
    mgr.register(listen_intents=[INTENT_TASK_ASSIGN])

    worker_mem = NodeMemory("worker_x", mem_db)
    worker = WorkerAgent(
        "worker_x", _make_config("worker"), bus, llm, state,
        memory=worker_mem, registry=registry,
    )
    worker.register()

    qa_mem = NodeMemory("qa", mem_db)
    qa = QAAgent("qa", _make_config("qa"), bus, llm, state, memory=qa_mem)
    qa.register()

    verdicts = []
    bus.subscribe(INTENT_QA_VERDICT, lambda pkt: verdicts.append(pkt))

    await bus.start()

    pkt = EMPPacket(
        source="user", target="chairman",
        intent_type=INTENT_USER_REQUEST,
        action="strategic goal",
        payload={"intent": "strategic goal", "original_intent": "strategic goal"},
        token_budget=8192,
    )
    await bus.publish(pkt)
    await asyncio.sleep(1.0)

    await bus.stop()
    await state.close()
    await mem_db.close()

    assert len(verdicts) >= 1
    assert verdicts[0].payload["verdict"] == "APPROVE"


@pytest.mark.asyncio
async def test_node_memory_isolation(monkeypatch):
    """Verify nodes only see their own memory."""
    mem_db = await aiosqlite.connect(":memory:")

    mem_a = NodeMemory("agent_a", mem_db)
    mem_b = NodeMemory("agent_b", mem_db)
    await mem_a.init()
    await mem_b.init()

    await mem_a.record("input", "secret-A")
    await mem_b.record("input", "secret-B")

    ctx_a = await mem_a.get_context(n=10)
    ctx_b = await mem_b.get_context(n=10)

    assert "secret-A" in ctx_a
    assert "secret-B" not in ctx_a
    assert "secret-B" in ctx_b
    assert "secret-A" not in ctx_b

    await mem_db.close()
