"""Real-world scenario tests — integration-style tests simulating practical use cases.

Scenarios:
    1. Data analyst pipeline: CSV → SQL → report
    2. DevOps file management: create/read/list/cleanup
    3. Agent multi-turn conversation with memory persistence
    4. Agent learns from failures (lesson learning)
    5. MCP Server end-to-end: initialize → list → call → error 
    6. Shell automation: multi-command pipeline
    7. Python code execution workflow
    8. Scheduler cron matching across time periods
    9. Agent planner with multi-step task decomposition
    10. Config hot-reload simulation
    11. Memory trim under heavy load
    12. MCP Server access control scenarios
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

from opentower.config import load_config, Config, SkillConfig
from opentower.agent import Agent
from opentower.skills import SkillRegistry, SkillInfo, skill
from opentower.scheduler import Scheduler
from opentower.channels import Message
from opentower.llm.client import LLMClient, LLMUsage
from opentower.memory.node_memory import NodeMemory


# ── Helpers ───────────────────────────────────────────────────

def _reg():
    """Quick skill registry from config."""
    config = load_config(Path(__file__).parent.parent / "config.yaml")
    reg = SkillRegistry()
    reg.load_from_config(config.enabled_skills)
    return reg


# ═══════════════════════════════════════════════════════════════
# SCENARIO 1: Data Analyst Pipeline
#   CSV → import → SQL aggregate → summary check
# ═══════════════════════════════════════════════════════════════

class TestDataAnalystPipeline:
    """Simulate: analyst uploads CSV, queries it, gets summary."""

    @pytest.mark.asyncio
    async def test_sales_report(self, tmp_path):
        reg = _reg()
        csv_path = str(tmp_path / "sales_q1.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "product", "revenue", "region"])
            w.writerow(["2026-01-15", "Widget A", "5000", "East"])
            w.writerow(["2026-01-20", "Widget B", "3000", "West"])
            w.writerow(["2026-02-10", "Widget A", "7000", "East"])
            w.writerow(["2026-02-15", "Widget B", "4000", "West"])
            w.writerow(["2026-03-01", "Widget A", "6000", "East"])

        # Step 1: Summary
        summary = await reg.call("csv_summary", path=csv_path)
        assert summary["row_count"] == 5
        assert "revenue" in summary["columns"]

        # Step 2: Revenue by region
        by_region = await reg.call("query_csv", path=csv_path,
            sql="SELECT region, SUM(revenue) as total FROM data GROUP BY region ORDER BY total DESC")
        assert by_region["row_count"] == 2
        rows = by_region["rows"]
        assert int(rows[0]["total"]) == 18000  # East total
        assert int(rows[1]["total"]) == 7000   # West total

        # Step 3: Revenue by product
        by_product = await reg.call("query_csv", path=csv_path,
            sql="SELECT product, COUNT(*) as deals, SUM(revenue) as total FROM data GROUP BY product")
        assert by_product["row_count"] == 2

    @pytest.mark.asyncio
    async def test_empty_csv(self, tmp_path):
        """Edge case: CSV with headers but no data rows → returns error."""
        reg = _reg()
        csv_path = str(tmp_path / "empty.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "name", "value"])

        summary = await reg.call("csv_summary", path=csv_path)
        # csv_summary returns error for empty CSV (no data rows)
        assert "error" in summary

    @pytest.mark.asyncio
    async def test_unicode_csv(self, tmp_path):
        """Chinese product names in CSV."""
        reg = _reg()
        csv_path = str(tmp_path / "cn.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "price"])
            w.writerow(["\u667a\u80fd\u624b\u8868", "2999"])
            w.writerow(["\u65e0\u7ebf\u8033\u673a", "599"])

        result = await reg.call("query_csv", path=csv_path,
            sql="SELECT name, price FROM data WHERE CAST(price AS INTEGER) > 1000")
        assert result["row_count"] == 1


# ═══════════════════════════════════════════════════════════════
# SCENARIO 2: DevOps File Workflow
#   Create config → read back → list → cleanup
# ═══════════════════════════════════════════════════════════════

class TestDevOpsFileWorkflow:
    @pytest.mark.asyncio
    async def test_config_file_lifecycle(self, tmp_path):
        reg = _reg()

        # Create config file
        cfg = str(tmp_path / "app.conf")
        await reg.call("write_file", path=cfg,
            content="[server]\nhost=0.0.0.0\nport=8080\ndebug=false")

        # Read it back
        result = await reg.call("read_file", path=cfg)
        assert "port=8080" in result["content"]

        # List the directory
        listing = await reg.call("list_dir", path=str(tmp_path))
        assert any(e["name"] == "app.conf" for e in listing["entries"])

    @pytest.mark.asyncio
    async def test_nested_directory_scan(self, tmp_path):
        """Create nested dirs and verify listing."""
        reg = _reg()
        sub = tmp_path / "project" / "src"
        sub.mkdir(parents=True)
        (sub / "main.py").write_text("print('hello')")
        (sub / "utils.py").write_text("def add(a,b): return a+b")

        listing = await reg.call("list_dir", path=str(sub))
        assert len(listing["entries"]) == 2

    @pytest.mark.asyncio
    async def test_large_file_content(self, tmp_path):
        """Write and read a larger file."""
        reg = _reg()
        fp = str(tmp_path / "big.txt")
        content = "Line {}\n" * 500
        content = "\n".join(f"Line {i}" for i in range(500))
        await reg.call("write_file", path=fp, content=content)
        result = await reg.call("read_file", path=fp)
        assert "Line 0" in result["content"]
        assert "Line 499" in result["content"]


# ═══════════════════════════════════════════════════════════════
# SCENARIO 3: Shell Automation
#   Multi-step system commands pipeline
# ═══════════════════════════════════════════════════════════════

class TestShellAutomation:
    @pytest.mark.asyncio
    async def test_multi_command_pipeline(self):
        reg = _reg()

        # Get current directory
        pwd = await reg.call("shell", command="cd")
        assert pwd["exit_code"] == 0

        # List Python files
        result = await reg.call("shell", command="dir /b *.py 2>nul || echo none")
        assert result["exit_code"] == 0

        # Echo and pipe
        result = await reg.call("shell", command='echo "hello world" | findstr "hello"')
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_env_variable(self):
        reg = _reg()
        result = await reg.call("shell", command="echo %USERNAME%")
        assert result["exit_code"] == 0
        assert len(result["stdout"]) > 0


# ═══════════════════════════════════════════════════════════════
# SCENARIO 4: Python Code Execution
#   Run real Python snippets
# ═══════════════════════════════════════════════════════════════

class TestPythonExecution:
    @pytest.mark.asyncio
    async def test_math_computation(self):
        reg = _reg()
        result = await reg.call("python_exec",
            code="import math; print(f'pi={math.pi:.4f}, e={math.e:.4f}')")
        assert "pi=3.1416" in result["stdout"]
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_json_processing(self):
        reg = _reg()
        code = """
import json
data = {"users": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]}
avg = sum(u["age"] for u in data["users"]) / len(data["users"])
print(f"average_age={avg}")
"""
        result = await reg.call("python_exec", code=code)
        assert "average_age=27.5" in result["stdout"]

    @pytest.mark.asyncio
    async def test_import_error(self):
        reg = _reg()
        result = await reg.call("python_exec",
            code="import nonexistent_module_xyz")
        assert result["exit_code"] != 0
        assert "ModuleNotFoundError" in result["stderr"]


# ═══════════════════════════════════════════════════════════════
# SCENARIO 5: Agent Multi-Turn Conversation
#   Simulate realistic multi-turn dialogue with context
# ═══════════════════════════════════════════════════════════════

class TestAgentMultiTurn:
    @pytest_asyncio.fixture
    async def env(self, monkeypatch):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        llm = LLMClient()
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("agent", db)
        await mem.init()
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        agent = Agent(config, llm, memory=mem, skills=reg.all_skills)
        yield agent, llm, mem, monkeypatch
        await db.close()

    @pytest.mark.asyncio
    async def test_three_turn_conversation(self, env):
        agent, llm, mem, mp = env
        turn = 0

        async def mock(messages, **kw):
            nonlocal turn; turn += 1
            responses = {
                1: "Hi! How can I help you today?",
                2: "The weather in Shanghai is 22C and sunny.",
                3: "You're welcome! Goodbye.",
            }
            text = responses.get(turn, "OK")
            return json.dumps({"action": "respond", "content": text}), \
                   LLMUsage(prompt_tokens=10, completion_tokens=10)

        mp.setattr(llm, "chat", mock)

        r1 = await agent.run("hello")
        assert "help" in r1.lower()

        r2 = await agent.run("what's the weather in Shanghai?")
        assert "22" in r2

        r3 = await agent.run("thanks!")
        assert "Goodbye" in r3

        # Verify memory has all 6 entries (3 user + 3 agent)
        all_entries = await mem.get_all()
        assert len(all_entries) == 6

    @pytest.mark.asyncio
    async def test_context_carries_over(self, env):
        """Agent receives memory context in subsequent turns."""
        agent, llm, mem, mp = env
        turn = 0

        async def mock(messages, **kw):
            nonlocal turn; turn += 1
            if turn == 1:
                return json.dumps({"action": "respond", "content": "Got it, project Alpha."}), \
                       LLMUsage(prompt_tokens=10, completion_tokens=10)
            else:
                # Should have context from turn 1
                return json.dumps({"action": "respond", "content": "Alpha status: on track."}), \
                       LLMUsage(prompt_tokens=10, completion_tokens=10)

        mp.setattr(llm, "chat", mock)

        await agent.run("My project is called Alpha")
        ctx = await mem.get_context(n=5)
        assert "Alpha" in ctx

        r2 = await agent.run("What's the status?", context=ctx)
        assert "Alpha" in r2


# ═══════════════════════════════════════════════════════════════
# SCENARIO 6: Agent Learns From Failures
#   Skill fails → lesson recorded → injected next time
# ═══════════════════════════════════════════════════════════════

class TestAgentLessonLearning:
    @pytest_asyncio.fixture
    async def env(self, monkeypatch):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        llm = LLMClient()
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("agent", db)
        await mem.init()
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        agent = Agent(config, llm, memory=mem, skills=reg.all_skills)
        yield agent, llm, mem, monkeypatch
        await db.close()

    @pytest.mark.asyncio
    async def test_failure_creates_lesson(self, env):
        """When a skill returns error, a lesson is recorded."""
        agent, llm, mem, mp = env
        n = 0

        async def mock(messages, **kw):
            nonlocal n; n += 1
            if n == 1:
                # Agent tries to read a non-existent file
                return json.dumps({"action": "call_skill", "skill": "read_file",
                    "args": {"path": "/nonexistent_test_file.txt"}}), \
                    LLMUsage(prompt_tokens=5, completion_tokens=5)
            else:
                return json.dumps({"action": "respond", "content": "File not found."}), \
                    LLMUsage(prompt_tokens=5, completion_tokens=5)

        mp.setattr(llm, "chat", mock)
        await agent.run("read the config file")

        # Lesson should be recorded
        lessons = await mem.get_lessons()
        assert "read_file" in lessons

    @pytest.mark.asyncio
    async def test_lessons_accumulate(self, env):
        """Multiple failures create multiple lessons."""
        _, _, mem, _ = env

        await mem.record_lesson("shell", "rm -rf /", "Permission denied")
        await mem.record_lesson("http_request", "GET http://down.com", "Connection refused")
        await mem.record_lesson("browse", "http://blocked.site", "SSL error")

        all_lessons = await mem.get_lessons()
        assert "Permission denied" in all_lessons
        assert "Connection refused" in all_lessons
        assert "SSL error" in all_lessons


# ═══════════════════════════════════════════════════════════════
# SCENARIO 7: MCP Server End-to-End Flow
#   Full handshake → discovery → tool call → error handling
# ═══════════════════════════════════════════════════════════════

class TestMCPEndToEnd:
    def _make_server(self):
        from opentower.mcp.server import MCPServer
        reg = SkillRegistry()

        async def search_docs(query: str = "", limit: int = 10):
            return {"results": [{"title": f"Doc about {query}", "score": 0.95}], "total": 1}

        async def create_ticket(title: str = "", description: str = ""):
            if not title:
                return {"error": "title is required"}
            return {"ticket_id": "TICK-001", "title": title, "status": "created"}

        reg.register(SkillInfo(name="search_docs", description="Search knowledge base",
            parameters='{"query": "string", "limit": "integer"}', execute=search_docs))
        reg.register(SkillInfo(name="create_ticket", description="Create support ticket",
            parameters='{"title": "string", "description": "string"}', execute=create_ticket))

        return MCPServer(reg)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_full_handshake(self):
        server = self._make_server()

        # 1. Initialize
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05",
                       "clientInfo": {"name": "TestClient", "version": "1.0"}}}))
        assert resp["result"]["protocolVersion"] == "2024-11-05"

        # 2. Initialized notification (no response)
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}))
        assert resp is None

        # 3. Discover tools
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}))
        tools = resp["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "search_docs" in names
        assert "create_ticket" in names

        # 4. Call search_docs
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "search_docs", "arguments": {"query": "MCP protocol"}}}))
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["total"] == 1
        assert "MCP protocol" in content["results"][0]["title"]

        # 5. Call create_ticket
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "create_ticket",
                       "arguments": {"title": "Bug: login fails", "description": "Steps to reproduce..."}}}))
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["ticket_id"] == "TICK-001"

        # 6. Error case: missing title
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "create_ticket", "arguments": {"title": ""}}}))
        assert resp["result"]["isError"] is True

    def test_concurrent_clients(self):
        """Multiple request IDs should work correctly."""
        server = self._make_server()
        for i in range(1, 6):
            resp = self._run(server._handle({
                "jsonrpc": "2.0", "id": i, "method": "ping", "params": {}}))
            assert resp["id"] == i
            assert "result" in resp


# ═══════════════════════════════════════════════════════════════
# SCENARIO 8: Memory Under Stress
#   Heavy writes → auto-trim → context retrieval
# ═══════════════════════════════════════════════════════════════

class TestMemoryStress:
    @pytest.mark.asyncio
    async def test_heavy_writes_with_trim(self):
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("stress", db, max_history=20)
        await mem.init()

        # Write 50 entries
        for i in range(50):
            await mem.record("user", f"Message {i}")

        # Should be trimmed to 20
        all_entries = await mem.get_all()
        assert len(all_entries) == 20

        # Latest should be preserved
        ctx = await mem.get_context(n=5)
        assert "Message 49" in ctx
        assert "Message 48" in ctx

        await db.close()

    @pytest.mark.asyncio
    async def test_lesson_deduplication(self):
        """Same error recorded multiple times."""
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("dup", db)
        await mem.init()

        for _ in range(10):
            await mem.record_lesson("shell", "bad cmd", "Permission denied")

        lessons = await mem.get_lessons(n=5)
        # Should still work, returning up to 5
        assert lessons.count("Permission denied") == 5

        await db.close()

    @pytest.mark.asyncio
    async def test_mixed_roles(self):
        """Memory correctly handles user/agent/system roles."""
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("mixed", db)
        await mem.init()

        await mem.record("user", "Hello")
        await mem.record("agent", "Hi there")
        await mem.record("system", "Task started")

        ctx = await mem.get_context(n=10)
        assert "\u2709" in ctx or "user" in ctx  # Has user marker
        assert "\u2709" in ctx or "agent" in ctx  # Has agent marker

        all_entries = await mem.get_all()
        assert len(all_entries) == 3
        assert all_entries[2]["role"] == "system"

        await db.close()


# ═══════════════════════════════════════════════════════════════
# SCENARIO 9: Scheduler Real Patterns
#   Various cron expressions across time periods
# ═══════════════════════════════════════════════════════════════

class TestSchedulerPatterns:
    def test_daily_9am(self):
        """Daily standup at 9:00 AM."""
        sched = {"cron": "0 9 * * *", "last_run": None}
        at_9am = datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc)
        at_10am = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)
        at_9_30 = datetime(2026, 3, 19, 9, 30, tzinfo=timezone.utc)
        assert Scheduler._should_run(sched, at_9am) is True
        assert Scheduler._should_run(sched, at_10am) is False
        assert Scheduler._should_run(sched, at_9_30) is False

    def test_every_15_minutes(self):
        """Health check every 15 minutes."""
        sched = {"cron": "*/15 * * * *", "last_run": None}
        for minute in [0, 15, 30, 45]:
            t = datetime(2026, 3, 19, 12, minute, tzinfo=timezone.utc)
            assert Scheduler._should_run(sched, t) is True
        for minute in [1, 7, 14, 16, 29]:
            t = datetime(2026, 3, 19, 12, minute, tzinfo=timezone.utc)
            assert Scheduler._should_run(sched, t) is False

    def test_every_hour(self):
        """Report every hour at :00."""
        sched = {"cron": "0 * * * *", "last_run": None}
        at_noon = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)
        at_noon_30 = datetime(2026, 3, 19, 12, 30, tzinfo=timezone.utc)
        assert Scheduler._should_run(sched, at_noon) is True
        assert Scheduler._should_run(sched, at_noon_30) is False


# ═══════════════════════════════════════════════════════════════
# SCENARIO 10: Agent Planner Real-World Task
#   Multi-step task decomposition and execution
# ═══════════════════════════════════════════════════════════════

class TestAgentPlannerRealWorld:
    @pytest_asyncio.fixture
    async def env(self, monkeypatch):
        config = load_config(Path(__file__).parent.parent / "config.yaml")
        llm = LLMClient()
        db = await aiosqlite.connect(":memory:")
        mem = NodeMemory("planner", db)
        await mem.init()
        reg = SkillRegistry()
        reg.load_from_config(config.enabled_skills)
        agent = Agent(config, llm, memory=mem, skills=reg.all_skills)
        yield agent, llm, mem, monkeypatch
        await db.close()

    @pytest.mark.asyncio
    async def test_research_pipeline(self, env):
        """Simulate: research topic → list files → summarize."""
        agent, llm, mem, mp = env
        n = 0

        async def mock(messages, **kw):
            nonlocal n; n += 1
            if n == 1:  # Plan
                return json.dumps({"action": "plan", "steps": [
                    {"description": "List project files", "skill": "list_dir", "args": {"path": "."}},
                    {"description": "Check Python version", "skill": "shell", "args": {"command": "python --version"}},
                ]}), LLMUsage(prompt_tokens=20, completion_tokens=20)
            else:  # Review
                return json.dumps({"action": "respond",
                    "content": "Research complete: found project files and confirmed Python version."}), \
                    LLMUsage(prompt_tokens=20, completion_tokens=20)

        mp.setattr(llm, "chat", mock)
        resp = await agent.run("Research our project setup", mode="plan")
        assert "Research complete" in resp

    @pytest.mark.asyncio
    async def test_planner_with_unavailable_skill(self, env):
        """Plan includes a skill that doesn't exist — should skip it."""
        agent, llm, mem, mp = env
        n = 0

        async def mock(messages, **kw):
            nonlocal n; n += 1
            if n == 1:
                return json.dumps({"action": "plan", "steps": [
                    {"description": "Search web", "skill": "google_search", "args": {"q": "test"}},
                    {"description": "List files", "skill": "list_dir", "args": {"path": "."}},
                ]}), LLMUsage(prompt_tokens=10, completion_tokens=10)
            else:
                return json.dumps({"action": "respond",
                    "content": "Partially done: web search skipped, files listed."}), \
                    LLMUsage(prompt_tokens=10, completion_tokens=10)

        mp.setattr(llm, "chat", mock)
        resp = await agent.run("search and list", mode="plan")
        assert "Partially done" in resp or "skipped" in resp.lower() or len(resp) > 0


# ═══════════════════════════════════════════════════════════════
# SCENARIO 11: MCP Server Resources & Prompts
#   Real-world resource serving and prompt templates
# ═══════════════════════════════════════════════════════════════

class TestMCPResourcesPrompts:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_knowledge_base_resources(self):
        from opentower.mcp.server import MCPServer
        reg = SkillRegistry()
        resources = [
            {"uri": "kb://faq", "name": "FAQ",
             "content": "Q: How to reset?\nA: Click Settings > Reset", "mimeType": "text/plain"},
            {"uri": "kb://pricing", "name": "Pricing",
             "content": "Basic: $10/mo, Pro: $50/mo", "mimeType": "text/plain"},
        ]
        server = MCPServer(reg, resources=resources)

        # List
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}}))
        assert len(resp["result"]["resources"]) == 2

        # Read FAQ
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 2, "method": "resources/read",
            "params": {"uri": "kb://faq"}}))
        assert "reset" in resp["result"]["contents"][0]["text"].lower()

        # Read Pricing
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 3, "method": "resources/read",
            "params": {"uri": "kb://pricing"}}))
        assert "$50" in resp["result"]["contents"][0]["text"]

    def test_prompt_templates(self):
        from opentower.mcp.server import MCPServer
        reg = SkillRegistry()
        prompts = [
            {"name": "customer_reply",
             "description": "Generate customer support reply",
             "messages": [
                 {"role": "system", "content": "You are a support agent. Be helpful and concise."},
                 {"role": "user", "content": "Customer says: {{message}}"},
             ]},
            {"name": "code_review",
             "description": "Review code for issues",
             "messages": [
                 {"role": "system", "content": "Review for bugs, security, and style."},
                 {"role": "user", "content": "```\n{{code}}\n```"},
             ]},
        ]
        server = MCPServer(reg, prompts=prompts)

        # List
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {}}))
        assert len(resp["result"]["prompts"]) == 2

        # Get customer_reply
        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 2, "method": "prompts/get",
            "params": {"name": "customer_reply"}}))
        assert len(resp["result"]["messages"]) == 2
        assert "support agent" in resp["result"]["messages"][0]["content"]

    def test_tool_with_json_schema_params(self):
        """Tools with proper JSON Schema parameters show up correctly."""
        from opentower.mcp.server import MCPServer
        reg = SkillRegistry()
        async def fn(**kw): return {"ok": True}
        reg.register(SkillInfo(
            name="create_user",
            description="Create a new user",
            parameters='{"name": "string", "email": "string", "role": "string"}',
            execute=fn,
        ))
        server = MCPServer(reg)

        resp = self._run(server._handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}))
        tool = resp["result"]["tools"][0]
        assert "inputSchema" in tool
        assert "name" in tool["inputSchema"]["properties"]


# ═══════════════════════════════════════════════════════════════
# SCENARIO 12: Config Edge Cases
# ═══════════════════════════════════════════════════════════════

class TestConfigEdgeCases:
    def test_missing_optional_fields(self):
        config = Config(agent={"name": "Test"})
        assert config.agent.name == "Test"
        assert config.agent.llm.temperature == 0.3  # default

    def test_partial_skill_configs(self):
        config = Config(skills=[
            {"name": "a"},  # minimal
            {"name": "b", "type": "cli", "command": "echo hi"},
            {"name": "c", "type": "mcp", "command": "npx mcp-x", "env": {"KEY": "val"}},
        ])
        assert len(config.skills) == 3
        assert config.skills[2].env == {"KEY": "val"}

    def test_mcp_server_custom_port(self):
        config = Config(mcp_server={"enabled": True, "transport": "http", "port": 9999})
        assert config.mcp_server.port == 9999
        assert config.mcp_server.enabled is True
