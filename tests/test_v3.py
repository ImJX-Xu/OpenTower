"""Tests for V3.1 — High-Frequency Skills, MCP, + V3.0 regression."""

import json
import csv
import pytest
import pytest_asyncio
import aiosqlite
from pathlib import Path

from opentower.config import load_config, _interpolate_env
from opentower.agent import Agent
from opentower.skills import SkillRegistry, SkillInfo, skill
from opentower.scheduler import Scheduler
from opentower.channels import Message
from opentower.llm.client import LLMClient, LLMUsage
from opentower.memory.node_memory import NodeMemory


# ── Config ─────────────────────────────────────────────────────

def test_load_config():
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    assert config.agent.version == "3.1"
    assert len(config.skills) >= 6  # shell, fs, python, browser, data, http


def test_env_interpolation():
    import os
    os.environ["TEST_KEY"] = "42"
    assert _interpolate_env("${TEST_KEY:-0}") == "42"
    del os.environ["TEST_KEY"]
    assert _interpolate_env("${TEST_KEY:-fallback}") == "fallback"


# ── Skills Discovery ──────────────────────────────────────────

def test_skill_decorator():
    @skill("test", description="test skill")
    async def my_skill(x: int = 0):
        return {"result": x}
    assert my_skill._skill_info.name == "test"


def test_registry_load_all():
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    available = reg.available
    assert "shell" in available
    assert "read_file" in available
    assert "list_dir" in available
    assert "browse" in available
    assert "web_search" in available
    assert "query_csv" in available
    assert "http_request" in available
    assert "webhook_send" in available


# ── Filesystem Skill ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_filesystem_list_dir():
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    result = await reg.call("list_dir", path=".")
    assert "entries" in result
    assert len(result["entries"]) > 0


@pytest.mark.asyncio
async def test_filesystem_read_write(tmp_path):
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)

    f = str(tmp_path / "test.txt")
    await reg.call("write_file", path=f, content="hello world")
    result = await reg.call("read_file", path=f)
    assert result["content"] == "hello world"


# ── Data Query Skill ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_csv_query(tmp_path):
    # Create test CSV
    csv_path = str(tmp_path / "sales.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "amount", "region"])
        writer.writerow(["Alice", "100", "East"])
        writer.writerow(["Bob", "200", "West"])
        writer.writerow(["Charlie", "150", "East"])

    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)

    result = await reg.call("query_csv", path=csv_path, sql="SELECT region, SUM(amount) as total FROM data GROUP BY region")
    assert result["row_count"] == 2
    assert len(result["rows"]) == 2


@pytest.mark.asyncio
async def test_csv_summary(tmp_path):
    csv_path = str(tmp_path / "data.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "value"])
        writer.writerow(["1", "a"])
        writer.writerow(["2", "b"])

    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)

    result = await reg.call("csv_summary", path=csv_path)
    assert result["row_count"] == 2
    assert result["columns"] == ["id", "value"]


# ── HTTP API Skill ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_http_request_error():
    """HTTP request to non-existent host fails gracefully."""
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)

    result = await reg.call("http_request", url="http://localhost:19999/nonexistent")
    assert "error" in result


# ── Browser Skill ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_browse_invalid_url():
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)

    result = await reg.call("browse", url="http://localhost:19999/nope")
    assert "error" in result


# ── Agent Loop ────────────────────────────────────────────────

@pytest_asyncio.fixture
async def agent_env(monkeypatch):
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    llm = LLMClient()
    mem_db = await aiosqlite.connect(":memory:")
    memory = NodeMemory("agent", mem_db)
    await memory.init()

    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)

    agent = Agent(config, llm, memory=memory, skills=reg.all_skills)
    yield agent, llm, mem_db, monkeypatch
    await mem_db.close()


@pytest.mark.asyncio
async def test_agent_respond(agent_env):
    agent, llm, _, mp = agent_env
    async def mock(messages, **kw):
        return json.dumps({"action": "respond", "content": "Hi!"}), LLMUsage(prompt_tokens=5, completion_tokens=5)
    mp.setattr(llm, "chat", mock)
    assert "Hi" in await agent.run("hello")


@pytest.mark.asyncio
async def test_agent_uses_skill(agent_env):
    agent, llm, _, mp = agent_env
    n = 0
    async def mock(messages, **kw):
        nonlocal n; n += 1
        if n == 1:
            return json.dumps({"action": "call_skill", "skill": "list_dir", "args": {"path": "."}}), LLMUsage(prompt_tokens=5, completion_tokens=5)
        return json.dumps({"action": "respond", "content": "Done."}), LLMUsage(prompt_tokens=5, completion_tokens=5)
    mp.setattr(llm, "chat", mock)
    resp = await agent.run("list files")
    assert "Done" in resp


@pytest.mark.asyncio
async def test_agent_plain_text(agent_env):
    agent, llm, _, mp = agent_env
    async def mock(messages, **kw):
        return "Just a plain response.", LLMUsage(prompt_tokens=5, completion_tokens=5)
    mp.setattr(llm, "chat", mock)
    resp = await agent.run("test")
    assert "plain response" in resp


@pytest.mark.asyncio
async def test_agent_memory(agent_env):
    agent, llm, _, mp = agent_env
    async def mock(messages, **kw):
        return json.dumps({"action": "respond", "content": "OK"}), LLMUsage(prompt_tokens=5, completion_tokens=5)
    mp.setattr(llm, "chat", mock)
    await agent.run("remember xyz")
    ctx = await agent.memory.get_context(n=5)
    assert "remember xyz" in ctx


# ── Scheduler ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_lifecycle():
    woke = False
    async def on_wake():
        nonlocal woke; woke = True
    s = Scheduler(interval=1, on_wake=on_wake)
    await s.start()
    await asyncio.sleep(1.5)
    await s.stop()
    assert woke


# ── MCP Server Unit ───────────────────────────────────────────

def test_mcp_server_handles_tools_list():
    """MCP Server correctly lists tools."""
    from opentower.mcp.server import MCPServer
    reg = SkillRegistry()
    async def noop(**kw): return {"ok": True}
    reg.register(SkillInfo(name="test_tool", description="A test", parameters="", execute=noop))

    server = MCPServer(reg)
    import asyncio
    resp = asyncio.get_event_loop().run_until_complete(
        server._handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    )
    assert resp["result"]["tools"][0]["name"] == "test_tool"


def test_message():
    msg = Message(text="hi", sender="user", channel="cli")
    assert msg.text == "hi"


import asyncio
