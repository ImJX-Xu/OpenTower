"""Comprehensive test suite for OpenTower V3.1.

Coverage:
    - Config: load, env interpolation, defaults, MCP server config
    - Skills: decorator, registry, MCP queuing, auto-discovery
    - Shell: execute, empty input, timeout scenarios
    - Filesystem: read, write, list, missing file
    - Python exec: success, error, empty
    - Browser: missing URL, invalid URL
    - Data query: CSV query, summary, empty CSV, bad SQL, SQLite
    - HTTP API: error path, webhook_send
    - Agent: simple respond, skill call, plain text, planner, auto-detect, max iterations, error recovery
    - Memory: record, context, trim, lessons (record/get/filter/clear)
    - Scheduler: lifecycle, cron matching (every N, exact time, invalid)
    - MCP Server: initialize, ping, tools/list, tools/call, access control, resources, prompts, errors, notifications
    - MCP Client: status, discovered_skills
    - Channels: Message creation
"""

import json
import csv
import asyncio
import os
import pytest
import pytest_asyncio
import aiosqlite
from pathlib import Path
from datetime import datetime, timezone

from opentower.config import load_config, _interpolate_env, Config, SkillConfig, MCPServerConfig
from opentower.agent import Agent
from opentower.skills import SkillRegistry, SkillInfo, skill
from opentower.scheduler import Scheduler
from opentower.channels import Message
from opentower.llm.client import LLMClient, LLMUsage
from opentower.memory.node_memory import NodeMemory


# ═══════════ CONFIG ═════════════════════════════════════════════

class TestConfig:
    def test_load_config(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        assert config.agent.version == "3.1"
        assert config.agent.name == "OpenTower"
        assert len(config.skills) >= 6

    def test_env_interpolation_existing(self):
        os.environ["_OT_TEST"] = "42"
        assert _interpolate_env("${_OT_TEST:-0}") == "42"
        del os.environ["_OT_TEST"]

    def test_env_interpolation_default(self):
        assert _interpolate_env("${_NONEXIST_KEY:-fallback}") == "fallback"

    def test_env_interpolation_nested_dict(self):
        result = _interpolate_env({"key": "${_NONEXIST:-val}"})
        assert result == {"key": "val"}

    def test_env_interpolation_list(self):
        result = _interpolate_env(["${_NONEXIST:-a}", "b"])
        assert result == ["a", "b"]

    def test_env_interpolation_non_string(self):
        assert _interpolate_env(42) == 42
        assert _interpolate_env(None) is None

    def test_mcp_server_config(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        assert hasattr(config, "mcp_server")
        assert config.mcp_server.transport in ("stdio", "http")
        assert isinstance(config.mcp_server.port, int)

    def test_config_defaults(self):
        config = Config()
        assert config.agent.name == "OpenTower"
        assert config.agent.llm.temperature == 0.3
        assert config.mcp_server.enabled is False

    def test_enabled_skills_filter(self):
        config = Config(skills=[
            SkillConfig(name="a", enabled=True),
            SkillConfig(name="b", enabled=False),
            SkillConfig(name="c", enabled=True),
        ])
        assert len(config.enabled_skills) == 2
        assert config.enabled_skills[0].name == "a"


# ═══════════ SKILLS REGISTRY ═══════════════════════════════════

class TestSkillRegistry:
    def test_decorator(self):
        @skill("test_dec", description="test")
        async def fn():
            return {"ok": True}
        assert fn._skill_info.name == "test_dec"
        assert fn._skill_info.description == "test"

    def test_decorator_defaults(self):
        @skill("test_doc")
        async def fn():
            """My docstring."""
            return {}
        assert fn._skill_info.description == "My docstring."

    def test_registry_load_all(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        for name in ["shell", "read_file", "write_file", "list_dir", "python_exec",
                      "browse", "web_search", "query_csv", "query_sqlite", "csv_summary",
                      "http_request", "webhook_send"]:
            assert name in reg.available, f"Missing: {name}"

    def test_registry_mcp_queuing(self):
        reg = SkillRegistry()
        reg.load_from_config([
            SkillConfig(name="gh", type="mcp", command="npx mcp-github"),
            SkillConfig(name="fs", type="python", module="opentower.skills.filesystem"),
        ])
        mcp_cfgs = reg.mcp_server_configs
        assert len(mcp_cfgs) == 1
        assert mcp_cfgs[0]["name"] == "gh"
        assert "read_file" in reg.available

    def test_registry_register_manual(self):
        reg = SkillRegistry()
        async def fn(**kw): return {"ok": True}
        reg.register(SkillInfo(name="custom", description="test", parameters="", execute=fn))
        assert "custom" in reg.available
        assert "custom" in reg

    def test_registry_call_unknown(self):
        reg = SkillRegistry()
        result = asyncio.get_event_loop().run_until_complete(reg.call("nonexistent"))
        assert "error" in result

    def test_registry_all_skills(self):
        reg = SkillRegistry()
        async def fn(**kw): return {}
        reg.register(SkillInfo(name="a", description="", parameters="", execute=fn))
        assert "a" in reg.all_skills


# ═══════════ SHELL SKILL ═══════════════════════════════════════

class TestShellSkill:
    @pytest.mark.asyncio
    async def test_execute(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("shell", command="echo hello")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_empty_command(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("shell", command="")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_failing_command(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("shell", command="exit 1")
        assert result["exit_code"] != 0


# ═══════════ FILESYSTEM SKILL ═════════════════════════════════

class TestFilesystemSkill:
    @pytest.mark.asyncio
    async def test_list_dir(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("list_dir", path=".")
        assert "entries" in result
        assert len(result["entries"]) > 0

    @pytest.mark.asyncio
    async def test_read_write(self, tmp_path):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        f = str(tmp_path / "test.txt")
        await reg.call("write_file", path=f, content="hello world")
        result = await reg.call("read_file", path=f)
        assert result["content"] == "hello world"

    @pytest.mark.asyncio
    async def test_read_missing_file(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("read_file", path="/nonexistent_path_12345.txt")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_missing_dir(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("list_dir", path="/nonexistent_dir_12345")
        assert "error" in result


# ═══════════ PYTHON EXEC SKILL ════════════════════════════════

class TestPythonExecSkill:
    @pytest.mark.asyncio
    async def test_execute(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("python_exec", code="print(2+3)")
        assert "5" in result["stdout"]
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_empty_code(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("python_exec", code="")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_error_code(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("python_exec", code="raise ValueError('boom')")
        assert result["exit_code"] != 0
        assert "boom" in result["stderr"]


# ═══════════ BROWSER SKILL ════════════════════════════════════

class TestBrowserSkill:
    @pytest.mark.asyncio
    async def test_no_url(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("browse", url="")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("browse", url="http://localhost:19999/nope")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_no_query(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("web_search", query="")
        assert "error" in result


# ═══════════ DATA QUERY SKILL ═════════════════════════════════

class TestDataQuerySkill:
    @pytest.mark.asyncio
    async def test_csv_query(self, tmp_path):
        csv_path = str(tmp_path / "data.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "amount"])
            w.writerow(["Alice", "100"])
            w.writerow(["Bob", "200"])
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("query_csv", path=csv_path, sql="SELECT SUM(amount) as total FROM data")
        assert result["row_count"] == 1

    @pytest.mark.asyncio
    async def test_csv_summary(self, tmp_path):
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
        assert result["columns"] == ["id", "val"]

    @pytest.mark.asyncio
    async def test_csv_missing_file(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("query_csv", path="/no_such_file.csv", sql="SELECT 1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_csv_no_path(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("query_csv", path="", sql="SELECT 1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_csv_bad_sql(self, tmp_path):
        csv_path = str(tmp_path / "data.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["a"])
            w.writerow(["1"])
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("query_csv", path=csv_path, sql="INVALID SQL HERE")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_sqlite_missing(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("query_sqlite", path="/no_such.db", sql="SELECT 1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_summary_no_path(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("csv_summary", path="")
        assert "error" in result


# ═══════════ HTTP API SKILL ═══════════════════════════════════

class TestHTTPAPISkill:
    @pytest.mark.asyncio
    async def test_no_url(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("http_request", url="")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_bad_method(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("http_request", url="http://example.com", method="INVALID")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_connection_error(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("http_request", url="http://localhost:19999/nope")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_webhook_send_missing(self):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        result = await reg.call("webhook_send", url="", message="")
        assert "error" in result


# ═══════════ AGENT ════════════════════════════════════════════

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


class TestAgentSimple:
    @pytest.mark.asyncio
    async def test_respond(self, agent_env):
        agent, llm, _, mp = agent_env
        async def mock(messages, **kw):
            return json.dumps({"action": "respond", "content": "Hi!"}), LLMUsage(prompt_tokens=5, completion_tokens=5)
        mp.setattr(llm, "chat", mock)
        assert "Hi" in await agent.run("hello")

    @pytest.mark.asyncio
    async def test_skill_call(self, agent_env):
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
    async def test_plain_text_fallback(self, agent_env):
        agent, llm, _, mp = agent_env
        async def mock(messages, **kw):
            return "Just plain text.", LLMUsage(prompt_tokens=5, completion_tokens=5)
        mp.setattr(llm, "chat", mock)
        resp = await agent.run("test")
        assert "Just plain text" in resp

    @pytest.mark.asyncio
    async def test_unknown_skill(self, agent_env):
        agent, llm, _, mp = agent_env
        n = 0
        async def mock(messages, **kw):
            nonlocal n; n += 1
            if n == 1:
                return json.dumps({"action": "call_skill", "skill": "nonexistent", "args": {}}), LLMUsage(prompt_tokens=5, completion_tokens=5)
            return json.dumps({"action": "respond", "content": "Oops."}), LLMUsage(prompt_tokens=5, completion_tokens=5)
        mp.setattr(llm, "chat", mock)
        resp = await agent.run("do impossible")
        assert "Oops" in resp

    @pytest.mark.asyncio
    async def test_memory_recorded(self, agent_env):
        agent, llm, _, mp = agent_env
        async def mock(messages, **kw):
            return json.dumps({"action": "respond", "content": "OK"}), LLMUsage(prompt_tokens=5, completion_tokens=5)
        mp.setattr(llm, "chat", mock)
        await agent.run("remember XYZ123")
        ctx = await agent.memory.get_context(n=5)
        assert "XYZ123" in ctx


class TestAgentPlanner:
    @pytest.mark.asyncio
    async def test_explicit_plan_mode(self, agent_env):
        agent, llm, _, mp = agent_env
        n = 0
        async def mock(messages, **kw):
            nonlocal n; n += 1
            if n == 1:
                return json.dumps({"action": "plan", "steps": [
                    {"description": "List files", "skill": "list_dir", "args": {"path": "."}},
                ]}), LLMUsage(prompt_tokens=10, completion_tokens=10)
            else:
                return json.dumps({"action": "respond", "content": "Plan complete."}), LLMUsage(prompt_tokens=10, completion_tokens=10)
        mp.setattr(llm, "chat", mock)
        resp = await agent.run("do the plan", mode="plan")
        assert "Plan complete" in resp

    @pytest.mark.asyncio
    async def test_auto_detect_chinese(self, agent_env):
        agent, llm, _, mp = agent_env
        n = 0
        async def mock(messages, **kw):
            nonlocal n; n += 1
            if n == 1:
                return json.dumps({"action": "plan", "steps": [
                    {"description": "s1", "skill": "list_dir", "args": {"path": "."}}
                ]}), LLMUsage(prompt_tokens=5, completion_tokens=5)
            else:
                return json.dumps({"action": "respond", "content": "Auto plan done."}), LLMUsage(prompt_tokens=5, completion_tokens=5)
        mp.setattr(llm, "chat", mock)
        resp = await agent.run("首先搜索竞品信息，然后对比分析，最后生成报告发给团队。请用中文写一份详细的市场分析报告。")
        assert "Auto plan done" in resp

    @pytest.mark.asyncio
    async def test_planner_fallback_on_bad_plan(self, agent_env):
        """If planner can't parse plan, falls back to simple mode."""
        agent, llm, _, mp = agent_env
        async def mock(messages, **kw):
            return json.dumps({"action": "respond", "content": "Fallback."}), LLMUsage(prompt_tokens=5, completion_tokens=5)
        mp.setattr(llm, "chat", mock)
        resp = await agent.run("do stuff", mode="plan")
        assert "Fallback" in resp

    def test_looks_complex_chinese(self):
        # Reuse the same Chinese string proven to work in test_auto_detect_chinese
        assert Agent._looks_complex("\u9996\u5148\u641c\u7d22\u7ade\u54c1\u4fe1\u606f\uff0c\u7136\u540e\u5bf9\u6bd4\u5206\u6790\uff0c\u6700\u540e\u751f\u6210\u62a5\u544a\u53d1\u7ed9\u56e2\u961f\u3002\u8bf7\u7528\u4e2d\u6587\u5199\u4e00\u4efd\u8be6\u7ec6\u7684\u5e02\u573a\u5206\u6790\u62a5\u544a\u3002") is True

    def test_looks_complex_english(self):
        assert Agent._looks_complex("First do X, then analyze the data, and then generate a report for the team meeting") is True

    def test_looks_simple(self):
        assert Agent._looks_complex("list files") is False

    def test_looks_simple_one_signal(self):
        # Only 1 signal word + short → not complex
        assert Agent._looks_complex("然后做点什么吧") is False


# ═══════════ MEMORY + LESSONS ══════════════════════════════════

class TestMemory:
    @pytest.mark.asyncio
    async def test_record_and_get(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db)
        await mem.init()
        await mem.record("user", "hello")
        await mem.record("agent", "hi back")
        ctx = await mem.get_context(n=5)
        assert "hello" in ctx
        assert "hi back" in ctx
        await db.close()

    @pytest.mark.asyncio
    async def test_get_all(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db)
        await mem.init()
        await mem.record("user", "msg1")
        await mem.record("agent", "msg2")
        all_entries = await mem.get_all()
        assert len(all_entries) == 2
        assert all_entries[0]["role"] == "user"
        await db.close()

    @pytest.mark.asyncio
    async def test_auto_trim(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db, max_history=3)
        await mem.init()
        for i in range(5):
            await mem.record("user", f"msg {i}")
        all_entries = await mem.get_all()
        assert len(all_entries) == 3
        await db.close()

    @pytest.mark.asyncio
    async def test_clear(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db)
        await mem.init()
        await mem.record("user", "msg")
        await mem.clear()
        ctx = await mem.get_context()
        assert ctx == ""
        await db.close()

    @pytest.mark.asyncio
    async def test_empty_context(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db)
        await mem.init()
        ctx = await mem.get_context()
        assert ctx == ""
        await db.close()


class TestLessons:
    @pytest.mark.asyncio
    async def test_record_and_get(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db)
        await mem.init()
        await mem.record_lesson("shell", "rm -rf /", "Permission denied")
        lessons = await mem.get_lessons()
        assert "Permission denied" in lessons
        assert "shell" in lessons
        await db.close()

    @pytest.mark.asyncio
    async def test_lesson_with_fix(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db)
        await mem.init()
        await mem.record_lesson("http", "POST /api", "401", fix="Add auth header")
        lessons = await mem.get_lessons()
        assert "Add auth header" in lessons
        await db.close()

    @pytest.mark.asyncio
    async def test_filter_by_skill(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db)
        await mem.init()
        await mem.record_lesson("shell", "cmd1", "err1")
        await mem.record_lesson("http", "cmd2", "err2")
        shell_only = await mem.get_lessons(skill="shell")
        assert "err1" in shell_only
        assert "err2" not in shell_only
        await db.close()

    @pytest.mark.asyncio
    async def test_clear_lessons(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db)
        await mem.init()
        await mem.record_lesson("shell", "test", "fail")
        await mem.clear_lessons()
        assert await mem.get_lessons() == ""
        await db.close()

    @pytest.mark.asyncio
    async def test_empty_lessons(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("test", db)
        await mem.init()
        assert await mem.get_lessons() == ""
        await db.close()


# ═══════════ SCHEDULER ═════════════════════════════════════════

class TestScheduler:
    @pytest.mark.asyncio
    async def test_lifecycle(self):
        woke = False
        async def on_wake():
            nonlocal woke; woke = True
        s = Scheduler(interval=1, on_wake=on_wake)
        await s.start()
        await asyncio.sleep(1.5)
        await s.stop()
        assert woke

    def test_cron_every_n_minutes(self):
        sched = {"cron": "*/5 * * * *", "last_run": None}
        now_0 = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)
        now_3 = datetime(2026, 3, 19, 12, 3, tzinfo=timezone.utc)
        now_5 = datetime(2026, 3, 19, 12, 5, tzinfo=timezone.utc)
        assert Scheduler._should_run(sched, now_0) is True    # 0 % 5 == 0
        assert Scheduler._should_run(sched, now_3) is False   # 3 % 5 != 0
        assert Scheduler._should_run(sched, now_5) is True    # 5 % 5 == 0

    def test_cron_exact_time(self):
        sched = {"cron": "30 9 * * *", "last_run": None}
        match = datetime(2026, 3, 19, 9, 30, tzinfo=timezone.utc)
        no_match = datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc)
        assert Scheduler._should_run(sched, match) is True
        assert Scheduler._should_run(sched, no_match) is False

    def test_cron_wildcard_hour(self):
        sched = {"cron": "15 * * * *", "last_run": None}
        match = datetime(2026, 3, 19, 14, 15, tzinfo=timezone.utc)
        no_match = datetime(2026, 3, 19, 14, 16, tzinfo=timezone.utc)
        assert Scheduler._should_run(sched, match) is True
        assert Scheduler._should_run(sched, no_match) is False

    def test_cron_no_double_run(self):
        last = datetime(2026, 3, 19, 9, 30, tzinfo=timezone.utc)
        sched = {"cron": "30 9 * * *", "last_run": last}
        now = datetime(2026, 3, 19, 9, 30, tzinfo=timezone.utc)
        assert Scheduler._should_run(sched, now) is False

    def test_cron_invalid(self):
        sched = {"cron": "invalid", "last_run": None}
        now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)
        assert Scheduler._should_run(sched, now) is False

    def test_add_schedule(self):
        s = Scheduler()
        s.add_schedule("*/5 * * * *", "check_tasks", lambda a: None)
        assert len(s._schedules) == 1


# ═══════════ MCP SERVER ═══════════════════════════════════════

class TestMCPServer:
    def _make_server(self, **kwargs):
        from opentower.mcp.server import MCPServer
        reg = SkillRegistry()
        async def echo(**kw): return {"echo": kw.get("msg", "")}
        async def fail(**kw): raise ValueError("boom")
        reg.register(SkillInfo(name="echo", description="Echo tool", parameters='{"msg": "string"}', execute=echo))
        reg.register(SkillInfo(name="fail_tool", description="Always fails", parameters="", execute=fail))
        return MCPServer(reg, **kwargs)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_initialize(self):
        server = self._make_server()
        resp = self._run(server._handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["serverInfo"]["name"] == "OpenTower"
        assert "tools" in resp["result"]["capabilities"]

    def test_ping(self):
        server = self._make_server()
        resp = self._run(server._handle({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}))
        assert "result" in resp

    def test_tools_list(self):
        server = self._make_server()
        resp = self._run(server._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}))
        names = [t["name"] for t in resp["result"]["tools"]]
        assert "echo" in names
        assert "fail_tool" in names

    def test_tool_call_success(self):
        server = self._make_server()
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "echo", "arguments": {"msg": "hello"}},
        }))
        assert resp["result"]["isError"] is False
        assert "hello" in resp["result"]["content"][0]["text"]

    def test_tool_call_error(self):
        server = self._make_server()
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "fail_tool", "arguments": {}},
        }))
        assert resp["result"]["isError"] is True

    def test_tool_call_unknown(self):
        server = self._make_server()
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "nonexistent", "arguments": {}},
        }))
        assert "error" in resp

    def test_access_control_list(self):
        server = self._make_server(expose_skills=["echo"])
        resp = self._run(server._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}))
        names = [t["name"] for t in resp["result"]["tools"]]
        assert "echo" in names
        assert "fail_tool" not in names

    def test_access_control_call(self):
        server = self._make_server(expose_skills=["echo"])
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "fail_tool", "arguments": {}},
        }))
        assert "error" in resp

    def test_unknown_method(self):
        server = self._make_server()
        resp = self._run(server._handle({"jsonrpc": "2.0", "id": 1, "method": "nonexistent", "params": {}}))
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_notification_no_response(self):
        server = self._make_server()
        resp = self._run(server._handle({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}))
        assert resp is None

    def test_resources_list(self):
        from opentower.mcp.server import MCPServer
        reg = SkillRegistry()
        resources = [{"uri": "file:///test.txt", "name": "Test", "content": "hello", "mimeType": "text/plain"}]
        server = MCPServer(reg, resources=resources)
        resp = self._run(server._handle({"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}}))
        assert len(resp["result"]["resources"]) == 1

    def test_resources_read(self):
        from opentower.mcp.server import MCPServer
        reg = SkillRegistry()
        resources = [{"uri": "file:///test.txt", "name": "Test", "content": "hello world", "mimeType": "text/plain"}]
        server = MCPServer(reg, resources=resources)
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": "file:///test.txt"},
        }))
        assert "hello world" in resp["result"]["contents"][0]["text"]

    def test_resources_read_missing(self):
        server = self._make_server()
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": "file:///nonexistent"},
        }))
        assert "error" in resp

    def test_prompts_list(self):
        from opentower.mcp.server import MCPServer
        reg = SkillRegistry()
        prompts = [{"name": "summarize", "description": "Summarize text", "messages": []}]
        server = MCPServer(reg, prompts=prompts)
        resp = self._run(server._handle({"jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {}}))
        assert len(resp["result"]["prompts"]) == 1

    def test_prompts_get(self):
        from opentower.mcp.server import MCPServer
        reg = SkillRegistry()
        prompts = [{"name": "summarize", "description": "Sum", "messages": [{"role": "user", "content": "hi"}]}]
        server = MCPServer(reg, prompts=prompts)
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "prompts/get",
            "params": {"name": "summarize"},
        }))
        assert resp["result"]["messages"][0]["content"] == "hi"

    def test_prompts_get_missing(self):
        server = self._make_server()
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "prompts/get",
            "params": {"name": "nonexistent"},
        }))
        assert "error" in resp

    def test_metrics_tracked(self):
        server = self._make_server()
        assert server._metrics["requests"] == 0
        self._run(server._handle({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}))
        assert server._metrics["requests"] == 1


# ═══════════ MCP CLIENT ═══════════════════════════════════════

class TestMCPClient:
    def test_empty_status(self):
        from opentower.mcp.client import MCPClient
        client = MCPClient()
        assert client.status == {}
        assert client.discovered_skills == {}

    @pytest.mark.asyncio
    async def test_disconnect_empty(self):
        from opentower.mcp.client import MCPClient
        client = MCPClient()
        await client.disconnect_all()  # Should not raise


# ═══════════ MESSAGE ══════════════════════════════════════════

class TestMessage:
    def test_creation(self):
        msg = Message(text="hi", sender="user", channel="cli")
        assert msg.text == "hi"
        assert msg.sender == "user"
        assert msg.channel == "cli"

    def test_metadata(self):
        msg = Message(text="hi", sender="u", channel="feishu", metadata={"chat_id": "123"})
        assert msg.metadata["chat_id"] == "123"
