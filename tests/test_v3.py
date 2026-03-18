"""Tests for V3.1 — Full test suite: Config, Skills, Agent (simple + planner), Memory + Lessons, MCP."""

import json
import csv
import asyncio
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
    assert len(config.skills) >= 6


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
    avail = reg.available
    for expected in ["shell", "read_file", "list_dir", "browse", "web_search", "query_csv", "http_request"]:
        assert expected in avail, f"Missing skill: {expected}"


# ── Filesystem ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_list_dir():
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    result = await reg.call("list_dir", path=".")
    assert "entries" in result


@pytest.mark.asyncio
async def test_fs_read_write(tmp_path):
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    f = str(tmp_path / "test.txt")
    await reg.call("write_file", path=f, content="hello")
    result = await reg.call("read_file", path=f)
    assert result["content"] == "hello"


# ── Data Query ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_csv_query(tmp_path):
    csv_path = str(tmp_path / "sales.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "amount", "region"])
        w.writerow(["Alice", "100", "East"])
        w.writerow(["Bob", "200", "West"])
        w.writerow(["Charlie", "150", "East"])
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    result = await reg.call("query_csv", path=csv_path, sql="SELECT region, SUM(amount) as total FROM data GROUP BY region")
    assert result["row_count"] == 2


@pytest.mark.asyncio
async def test_csv_summary(tmp_path):
    csv_path = str(tmp_path / "data.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "val"])
        w.writerow(["1", "a"])
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    result = await reg.call("csv_summary", path=csv_path)
    assert result["row_count"] == 1


# ── HTTP / Browser (error paths) ─────────────────────────────

@pytest.mark.asyncio
async def test_http_error():
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    result = await reg.call("http_request", url="http://localhost:19999/nope")
    assert "error" in result


@pytest.mark.asyncio
async def test_browse_error():
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    result = await reg.call("browse", url="http://localhost:19999/nope")
    assert "error" in result


# ── Agent Setup ───────────────────────────────────────────────

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


# ── Agent Simple Mode ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_respond(agent_env):
    agent, llm, _, mp = agent_env
    async def mock(messages, **kw):
        return json.dumps({"action": "respond", "content": "Hi!"}), LLMUsage(prompt_tokens=5, completion_tokens=5)
    mp.setattr(llm, "chat", mock)
    assert "Hi" in await agent.run("hello")


@pytest.mark.asyncio
async def test_agent_skill_call(agent_env):
    agent, llm, _, mp = agent_env
    n = 0
    async def mock(messages, **kw):
        nonlocal n; n += 1
        if n == 1:
            return json.dumps({"action": "call_skill", "skill": "list_dir", "args": {"path": "."}}), LLMUsage(prompt_tokens=5, completion_tokens=5)
        return json.dumps({"action": "respond", "content": "Done."}), LLMUsage(prompt_tokens=5, completion_tokens=5)
    mp.setattr(llm, "chat", mock)
    assert "Done" in await agent.run("list files")


@pytest.mark.asyncio
async def test_agent_plain_text(agent_env):
    agent, llm, _, mp = agent_env
    async def mock(messages, **kw):
        return "Just text.", LLMUsage(prompt_tokens=5, completion_tokens=5)
    mp.setattr(llm, "chat", mock)
    assert "Just text" in await agent.run("test")


# ── Agent Planner Mode ────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_planner(agent_env):
    """Planner mode: LLM returns plan → agent executes steps → review."""
    agent, llm, _, mp = agent_env
    n = 0
    async def mock(messages, **kw):
        nonlocal n; n += 1
        if n == 1:  # Plan
            return json.dumps({
                "action": "plan",
                "steps": [
                    {"description": "List files", "skill": "list_dir", "args": {"path": "."}},
                    {"description": "Read config", "skill": "read_file", "args": {"path": "config.yaml"}},
                ]
            }), LLMUsage(prompt_tokens=10, completion_tokens=10)
        else:  # Review
            return json.dumps({"action": "respond", "content": "Found 2 results."}), LLMUsage(prompt_tokens=10, completion_tokens=10)
    mp.setattr(llm, "chat", mock)
    resp = await agent.run("首先列出文件，然后读取配置文件", mode="plan")
    assert "Found 2 results" in resp


@pytest.mark.asyncio
async def test_agent_auto_detect_complex(agent_env):
    """Auto mode detects complex requests."""
    agent, llm, _, mp = agent_env
    n = 0
    async def mock(messages, **kw):
        nonlocal n; n += 1
        if n == 1:  # Plan call
            return json.dumps({
                "action": "plan",
                "steps": [{"description": "step1", "skill": "list_dir", "args": {"path": "."}}]
            }), LLMUsage(prompt_tokens=5, completion_tokens=5)
        else:  # Review call
            return json.dumps({"action": "respond", "content": "Plan executed."}), LLMUsage(prompt_tokens=5, completion_tokens=5)
    mp.setattr(llm, "chat", mock)
    # This input has sequence words + is long enough → planner mode
    resp = await agent.run("首先搜索竞品信息，然后对比分析，最后生成报告发给团队。请用中文写一份详细的市场分析报告。")
    assert "Plan executed" in resp


# ── Memory + Lessons ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_record():
    db = await aiosqlite.connect(":memory:")
    mem = NodeMemory("test", db)
    await mem.init()
    await mem.record("user", "hello")
    ctx = await mem.get_context(n=5)
    assert "hello" in ctx
    await db.close()


@pytest.mark.asyncio
async def test_lesson_learning():
    db = await aiosqlite.connect(":memory:")
    mem = NodeMemory("test", db)
    await mem.init()

    await mem.record_lesson("shell", "rm -rf /", "Permission denied")
    await mem.record_lesson("http_request", "POST /api", "Connection refused", fix="Check URL")

    lessons = await mem.get_lessons()
    assert "Permission denied" in lessons
    assert "Connection refused" in lessons
    assert "Check URL" in lessons

    # Filter by skill
    shell_lessons = await mem.get_lessons(skill="shell")
    assert "Permission denied" in shell_lessons
    assert "Connection refused" not in shell_lessons

    await db.close()


@pytest.mark.asyncio
async def test_lesson_clearing():
    db = await aiosqlite.connect(":memory:")
    mem = NodeMemory("test", db)
    await mem.init()
    await mem.record_lesson("shell", "test", "fail")
    await mem.clear_lessons()
    lessons = await mem.get_lessons()
    assert lessons == ""
    await db.close()


# ── Scheduler ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler():
    woke = False
    async def on_wake():
        nonlocal woke; woke = True
    s = Scheduler(interval=1, on_wake=on_wake)
    await s.start()
    await asyncio.sleep(1.5)
    await s.stop()
    assert woke


# ── MCP Server ────────────────────────────────────────────────

def test_mcp_server_tools_list():
    from opentower.mcp.server import MCPServer
    reg = SkillRegistry()
    async def noop(**kw): return {"ok": True}
    reg.register(SkillInfo(name="test_tool", description="A test", parameters="", execute=noop))
    server = MCPServer(reg)
    resp = asyncio.get_event_loop().run_until_complete(
        server._handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    )
    assert resp["result"]["tools"][0]["name"] == "test_tool"


# ── Message ───────────────────────────────────────────────────

def test_message():
    msg = Message(text="hi", sender="user", channel="cli")
    assert msg.text == "hi"
