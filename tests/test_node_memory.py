"""Tests for per-node memory (V2.0)."""

import pytest
import pytest_asyncio
import aiosqlite

from opentower.memory.node_memory import NodeMemory


@pytest_asyncio.fixture
async def memory_db():
    """In-memory SQLite for testing."""
    db = await aiosqlite.connect(":memory:")
    yield db
    await db.close()


@pytest_asyncio.fixture
async def mem(memory_db):
    """A NodeMemory instance for testing."""
    m = NodeMemory("test_agent", memory_db, max_history=5)
    await m.init()
    return m


@pytest.mark.asyncio
async def test_record_and_retrieve(mem):
    """Record entries and retrieve context."""
    await mem.record("input", "hello world")
    await mem.record("output", "response here")

    ctx = await mem.get_context(n=5)
    assert "hello world" in ctx
    assert "response here" in ctx


@pytest.mark.asyncio
async def test_context_order(mem):
    """Context should be in chronological order."""
    for i in range(3):
        await mem.record("input", f"msg-{i}")

    ctx = await mem.get_context(n=5)
    lines = ctx.strip().split("\n")
    assert len(lines) == 3
    assert "msg-0" in lines[0]
    assert "msg-2" in lines[2]


@pytest.mark.asyncio
async def test_auto_trim(mem):
    """Memory auto-trims when exceeding max_history."""
    for i in range(10):
        await mem.record("input", f"entry-{i}")

    all_entries = await mem.get_all()
    assert len(all_entries) <= 5  # max_history=5


@pytest.mark.asyncio
async def test_empty_context(mem):
    """Empty memory returns empty string."""
    ctx = await mem.get_context(n=5)
    assert ctx == ""


@pytest.mark.asyncio
async def test_clear(mem):
    """Clear removes all entries."""
    await mem.record("input", "test")
    await mem.clear()
    ctx = await mem.get_context(n=5)
    assert ctx == ""


@pytest.mark.asyncio
async def test_multiple_nodes(memory_db):
    """Different nodes get independent tables."""
    mem_a = NodeMemory("agent_a", memory_db)
    mem_b = NodeMemory("agent_b", memory_db)
    await mem_a.init()
    await mem_b.init()

    await mem_a.record("input", "from A")
    await mem_b.record("input", "from B")

    ctx_a = await mem_a.get_context(n=5)
    ctx_b = await mem_b.get_context(n=5)

    assert "from A" in ctx_a
    assert "from B" not in ctx_a
    assert "from B" in ctx_b
    assert "from A" not in ctx_b
