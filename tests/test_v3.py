"""Tests for V3.0 — Config, Agent, Skills, Scheduler."""

import json
import pytest
import pytest_asyncio
import aiosqlite
from pathlib import Path

from opentower.config import load_config, Config, _interpolate_env
from opentower.agent import Agent
from opentower.skills import SkillRegistry, SkillInfo, skill
from opentower.scheduler import Scheduler
from opentower.channels import Message
from opentower.llm.client import LLMClient
from opentower.memory.node_memory import NodeMemory


# ── Config Tests ───────────────────────────────────────────────

def test_load_config():
    """Real config.yaml loads."""
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    assert config.agent.name == "OpenTower"
    assert config.agent.version == "3.0"
    assert len(config.skills) >= 1


def test_env_interpolation():
    import os
    os.environ["TEST_VAR"] = "hello"
    result = _interpolate_env("${TEST_VAR:-default}")
    assert result == "hello"
    del os.environ["TEST_VAR"]


def test_env_default():
    result = _interpolate_env("${NONEXISTENT_VAR:-fallback}")
    assert result == "fallback"


def test_config_enabled_skills():
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    enabled = config.enabled_skills
    assert all(s.enabled for s in enabled)


# ── Skills Tests ───────────────────────────────────────────────

def test_skill_decorator():
    @skill("test_skill", description="A test skill")
    async def my_skill(x: int = 0):
        return {"result": x * 2}

    assert hasattr(my_skill, "_skill_info")
    assert my_skill._skill_info.name == "test_skill"


@pytest.mark.asyncio
async def test_skill_execution():
    @skill("double", description="Double a number")
    async def double(x: int = 1):
        return {"result": x * 2}

    result = await double(x=5)
    assert result == {"result": 10}


def test_registry_register():
    reg = SkillRegistry()
    async def noop(**kw):
        return {"ok": True}
    reg.register(SkillInfo(name="test", description="test", parameters="", execute=noop))
    assert "test" in reg
    assert "test" in reg.available


def test_registry_load_from_config():
    """Load skills from real config."""
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    # Shell, filesystem, python_exec should be loaded
    assert "shell" in reg.available
    assert "read_file" in reg.available
    assert "list_dir" in reg.available


@pytest.mark.asyncio
async def test_filesystem_list_dir():
    """Filesystem skill actually works."""
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    result = await reg.call("list_dir", path=".")
    assert "entries" in result
    assert len(result["entries"]) > 0


# ── Agent Tests ────────────────────────────────────────────────

@pytest_asyncio.fixture
async def agent_setup(monkeypatch):
    """Setup agent with mocked LLM."""
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    llm = LLMClient()
    mem_db = await aiosqlite.connect(":memory:")
    memory = NodeMemory("agent", mem_db)
    await memory.init()

    # Load real skills
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)

    agent = Agent(config, llm, memory=memory, skills=reg.all_skills)
    yield agent, llm, mem_db, monkeypatch
    await mem_db.close()


@pytest.mark.asyncio
async def test_agent_direct_response(agent_setup):
    """Agent responds directly when LLM says respond."""
    agent, llm, _, monkeypatch = agent_setup
    from opentower.llm.client import LLMUsage

    async def mock_chat(messages, **kw):
        return json.dumps({
            "action": "respond",
            "content": "Hello! How can I help?"
        }), LLMUsage(prompt_tokens=10, completion_tokens=10)

    monkeypatch.setattr(llm, "chat", mock_chat)
    response = await agent.run("hi")
    assert "Hello" in response


@pytest.mark.asyncio
async def test_agent_calls_skill(agent_setup):
    """Agent calls a skill when LLM requests it."""
    agent, llm, _, monkeypatch = agent_setup
    from opentower.llm.client import LLMUsage

    call_count = 0
    async def mock_chat(messages, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return json.dumps({
                "action": "call_skill",
                "skill": "list_dir",
                "args": {"path": "."}
            }), LLMUsage(prompt_tokens=10, completion_tokens=10)
        else:
            return json.dumps({
                "action": "respond",
                "content": "Found files in the directory."
            }), LLMUsage(prompt_tokens=10, completion_tokens=10)

    monkeypatch.setattr(llm, "chat", mock_chat)
    response = await agent.run("list files")
    assert "Found files" in response
    assert call_count == 2  # think + reflect


@pytest.mark.asyncio
async def test_agent_handles_plain_text(agent_setup):
    """Agent handles plain text LLM output (no JSON)."""
    agent, llm, _, monkeypatch = agent_setup
    from opentower.llm.client import LLMUsage

    async def mock_chat(messages, **kw):
        return "I cannot help with that.", LLMUsage(prompt_tokens=10, completion_tokens=10)

    monkeypatch.setattr(llm, "chat", mock_chat)
    response = await agent.run("something weird")
    assert "cannot help" in response


@pytest.mark.asyncio
async def test_agent_memory_recorded(agent_setup):
    """Agent records interactions to memory."""
    agent, llm, mem_db, monkeypatch = agent_setup
    from opentower.llm.client import LLMUsage

    async def mock_chat(messages, **kw):
        return json.dumps({
            "action": "respond",
            "content": "Noted."
        }), LLMUsage(prompt_tokens=10, completion_tokens=10)

    monkeypatch.setattr(llm, "chat", mock_chat)
    await agent.run("remember this")
    ctx = await agent.memory.get_context(n=5)
    assert "remember this" in ctx


# ── Scheduler Tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_start_stop():
    """Scheduler starts and stops cleanly."""
    woke = False
    async def on_wake():
        nonlocal woke
        woke = True

    sched = Scheduler(interval=1, on_wake=on_wake)
    await sched.start()
    await asyncio.sleep(1.5)
    await sched.stop()
    assert woke


@pytest.mark.asyncio
async def test_scheduler_cron_check():
    """Cron check returns True for matching minute."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    sched = {"cron": f"*/1 * * * *", "last_run": None}
    assert Scheduler._should_run(sched, now)


# ── Message Tests ──────────────────────────────────────────────

def test_message_creation():
    msg = Message(text="hello", sender="user", channel="cli")
    assert msg.text == "hello"
    assert msg.metadata == {}


import asyncio
