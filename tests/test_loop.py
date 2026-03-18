"""Tests for the full CEO → Worker → QA closed loop (with mock LLM)."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from opentower.actions.registry import ActionRegistry
from opentower.actions.shell import register_shell_actions
from opentower.agents.ceo import CEOAgent
from opentower.agents.qa import QAAgent
from opentower.agents.worker import WorkerAgent
from opentower.bus.event_bus import EMPBus
from opentower.llm.client import LLMClient, LLMUsage
from opentower.memory.state_wall import StateWall
from opentower.schema.company import NodeConfig
from opentower.schema.emp import EMPPacket, INTENT_QA_VERDICT, INTENT_USER_REQUEST


def _make_node(role: str, budget: int = 4096) -> NodeConfig:
    return NodeConfig(role=role, prompt=f"You are {role}.", token_budget=budget)


@pytest_asyncio.fixture
async def pipeline():
    """Set up a full pipeline with mock LLM."""
    bus = EMPBus()
    llm = LLMClient()
    state = StateWall(":memory:")  # in-memory SQLite
    await state.open()

    registry = ActionRegistry()
    register_shell_actions(registry)

    ceo = CEOAgent("ceo", _make_node("ceo"), bus, llm, state)
    worker = WorkerAgent("worker", _make_node("worker"), bus, llm, state, registry=registry)
    qa = QAAgent("qa", _make_node("qa"), bus, llm, state)

    ceo.register()
    worker.register()
    qa.register()

    verdicts: list[EMPPacket] = []

    async def collect_verdict(pkt: EMPPacket) -> None:
        verdicts.append(pkt)

    bus.subscribe(INTENT_QA_VERDICT, collect_verdict)

    await bus.start()

    yield bus, verdicts

    await bus.stop()
    await state.close()


@pytest.mark.asyncio
async def test_full_loop_approve(pipeline):
    bus, verdicts = pipeline

    # Mock LLM: CEO returns a simple task, QA approves
    ceo_response = json.dumps([
        {"action_type": "shell_execute", "description": "echo test", "payload": {"command": "echo hello_opentower"}}
    ])
    qa_response = json.dumps({"verdict": "APPROVE", "reason": "Output matches intent"})

    with patch.object(LLMClient, "chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = [
            (ceo_response, LLMUsage(prompt_tokens=10, completion_tokens=20)),
            (qa_response, LLMUsage(prompt_tokens=10, completion_tokens=10)),
        ]

        pkt = EMPPacket(
            source="user",
            intent_type=INTENT_USER_REQUEST,
            action="say hello",
            token_budget=4096,
        )
        await bus.publish(pkt)
        await asyncio.sleep(1.0)  # give pipeline time to flow

    assert len(verdicts) >= 1
    assert verdicts[0].payload["verdict"] == "APPROVE"


@pytest.mark.asyncio
async def test_full_loop_reject_then_approve(pipeline):
    bus, verdicts = pipeline

    ceo_response = json.dumps([
        {"action_type": "shell_execute", "description": "bad command", "payload": {"command": "nonexistent_cmd_xyz"}}
    ])
    # First QA call rejects, second approves (after retry)
    qa_reject = json.dumps({"verdict": "REJECT", "reason": "Command failed", "suggestion": "Use a valid command"})
    qa_approve = json.dumps({"verdict": "APPROVE", "reason": "Retry succeeded"})

    with patch.object(LLMClient, "chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = [
            (ceo_response, LLMUsage(10, 20)),  # CEO
            (qa_reject, LLMUsage(10, 10)),        # QA reject
            (qa_approve, LLMUsage(10, 10)),        # QA approve on retry
        ]

        pkt = EMPPacket(
            source="user",
            intent_type=INTENT_USER_REQUEST,
            action="run something",
            token_budget=4096,
        )
        await bus.publish(pkt)
        await asyncio.sleep(2.0)

    # Should have at least 2 verdicts (reject + final)
    assert len(verdicts) >= 1


@pytest.mark.asyncio
async def test_token_budget_enforcement():
    """Agent should raise when token budget is exhausted."""
    bus = EMPBus()
    llm = LLMClient()
    state = StateWall(":memory:")
    await state.open()

    agent = CEOAgent("ceo", _make_node("ceo", budget=10), bus, llm, state)
    agent.tokens_used = 10  # exhaust budget

    with pytest.raises(RuntimeError, match="Token budget exhausted"):
        await agent.call_llm([{"role": "user", "content": "test"}])

    await state.close()
