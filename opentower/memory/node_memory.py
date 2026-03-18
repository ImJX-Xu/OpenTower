"""Per-Node Memory — independent scoped memory for each agent.

Each agent gets its own SQLite table to store interaction history.
Memories are automatically injected into LLM calls as context.
Old memories can be summarized to prevent context window overflow.

Design:
    Global StateWall (audit log) ← write-only, full trace
    Per-Node Memory (this)       ← read/write, scoped to each agent
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger("opentower.memory.node")


class NodeMemory:
    """Scoped memory for a single agent node.

    Each node has its own table: ``memory_{node_id}``.
    Stores input/output pairs and provides recent context retrieval.

    Usage::

        mem = NodeMemory("ceo", db)
        await mem.init()
        await mem.record("user asked X", "I decomposed into Y")
        context = await mem.get_context(n=5)
    """

    def __init__(
        self,
        node_id: str,
        db: aiosqlite.Connection,
        max_history: int = 50,
    ) -> None:
        self.node_id = node_id
        self._db = db
        self._table = f"memory_{node_id.replace('-', '_')}"
        self.max_history = max_history

    async def init(self) -> None:
        """Create the memory table if it doesn't exist."""
        await self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp TEXT    NOT NULL
            )
        """)
        await self._db.commit()
        logger.debug("[%s] Memory table initialized", self.node_id)

    async def record(self, role: str, content: str) -> None:
        """Store a memory entry (role = 'input' | 'output' | 'summary')."""
        await self._db.execute(
            f"INSERT INTO {self._table} (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content[:2000], datetime.now(timezone.utc).isoformat()),
        )
        await self._db.commit()

        # Auto-trim if exceeding max_history
        count_cursor = await self._db.execute(
            f"SELECT COUNT(*) FROM {self._table}"
        )
        (count,) = await count_cursor.fetchone()
        if count > self.max_history:
            await self._trim()

    async def get_context(self, n: int = 5) -> str:
        """Return the last N memory entries as formatted text for LLM injection."""
        cursor = await self._db.execute(
            f"SELECT role, content FROM {self._table} ORDER BY id DESC LIMIT ?",
            (n,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return ""

        lines = []
        for role, content in reversed(rows):  # chronological order
            prefix = "📥" if role == "input" else "📤" if role == "output" else "📋"
            lines.append(f"{prefix} [{role}] {content[:300]}")

        return "\n".join(lines)

    async def get_all(self) -> list[dict]:
        """Return all memories as dicts."""
        cursor = await self._db.execute(
            f"SELECT id, role, content, timestamp FROM {self._table} ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [
            {"id": r[0], "role": r[1], "content": r[2], "timestamp": r[3]}
            for r in rows
        ]

    async def _trim(self) -> None:
        """Keep only the most recent max_history entries."""
        await self._db.execute(f"""
            DELETE FROM {self._table}
            WHERE id NOT IN (
                SELECT id FROM {self._table}
                ORDER BY id DESC LIMIT {self.max_history}
            )
        """)
        await self._db.commit()
        logger.debug("[%s] Memory trimmed to %d entries", self.node_id, self.max_history)

    async def clear(self) -> None:
        """Clear all memories for this node."""
        await self._db.execute(f"DELETE FROM {self._table}")
        await self._db.commit()
