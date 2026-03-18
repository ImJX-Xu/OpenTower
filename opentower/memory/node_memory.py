"""Per-Node Memory — agent memory with lesson learning.

Each agent gets its own SQLite tables:
  - memory_{id}: interaction history (input/output)
  - lessons_{id}: failure lessons (skill errors + fixes)

Lessons are automatically injected into LLM context,
enabling the agent to learn from past mistakes and
avoid repeating them — "可审计知识，跨模型迁移".
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger("opentower.memory.node")


class NodeMemory:
    """Scoped memory + lesson learning for an agent.

    Usage::

        mem = NodeMemory("agent", db)
        await mem.init()
        await mem.record("user", "do X")
        await mem.record_lesson("shell", "rm -rf /", "Permission denied")
        lessons = await mem.get_lessons()  # injected into LLM context
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
        self._lesson_table = f"lessons_{node_id.replace('-', '_')}"
        self.max_history = max_history

    async def init(self) -> None:
        """Create memory and lesson tables."""
        await self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp TEXT    NOT NULL
            )
        """)
        await self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._lesson_table} (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                skill     TEXT    NOT NULL,
                input     TEXT    NOT NULL,
                error     TEXT    NOT NULL,
                fix       TEXT    DEFAULT '',
                timestamp TEXT    NOT NULL
            )
        """)
        await self._db.commit()
        logger.debug("[%s] Memory + lessons initialized", self.node_id)

    # ── Conversation Memory ───────────────────────────────────

    async def record(self, role: str, content: str) -> None:
        """Store a memory entry."""
        await self._db.execute(
            f"INSERT INTO {self._table} (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content[:2000], datetime.now(timezone.utc).isoformat()),
        )
        await self._db.commit()

        count_cursor = await self._db.execute(f"SELECT COUNT(*) FROM {self._table}")
        (count,) = await count_cursor.fetchone()
        if count > self.max_history:
            await self._trim()

    async def get_context(self, n: int = 5) -> str:
        """Return last N entries as formatted text."""
        cursor = await self._db.execute(
            f"SELECT role, content FROM {self._table} ORDER BY id DESC LIMIT ?",
            (n,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return ""

        lines = []
        for role, content in reversed(rows):
            prefix = "📥" if role == "user" else "📤" if role == "agent" else "📋"
            lines.append(f"{prefix} [{role}] {content[:300]}")
        return "\n".join(lines)

    async def get_all(self) -> list[dict]:
        cursor = await self._db.execute(
            f"SELECT id, role, content, timestamp FROM {self._table} ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [{"id": r[0], "role": r[1], "content": r[2], "timestamp": r[3]} for r in rows]

    async def _trim(self) -> None:
        await self._db.execute(f"""
            DELETE FROM {self._table}
            WHERE id NOT IN (
                SELECT id FROM {self._table}
                ORDER BY id DESC LIMIT {self.max_history}
            )
        """)
        await self._db.commit()

    async def clear(self) -> None:
        await self._db.execute(f"DELETE FROM {self._table}")
        await self._db.commit()

    # ── Lesson Learning ───────────────────────────────────────

    async def record_lesson(self, skill: str, input_desc: str, error: str, fix: str = "") -> None:
        """Record a lesson from a skill failure.

        Args:
            skill: Name of the skill that failed.
            input_desc: What was attempted.
            error: What went wrong.
            fix: How it was fixed (if known).
        """
        await self._db.execute(
            f"INSERT INTO {self._lesson_table} (skill, input, error, fix, timestamp) VALUES (?, ?, ?, ?, ?)",
            (skill, input_desc[:500], error[:500], fix[:500], datetime.now(timezone.utc).isoformat()),
        )
        await self._db.commit()
        logger.info("[%s] Lesson recorded: %s — %s", self.node_id, skill, error[:60])

    async def get_lessons(self, skill: str = "", n: int = 10) -> str:
        """Get recent lessons, optionally filtered by skill.

        Returns formatted text for LLM injection.
        """
        if skill:
            cursor = await self._db.execute(
                f"SELECT skill, input, error, fix FROM {self._lesson_table} WHERE skill = ? ORDER BY id DESC LIMIT ?",
                (skill, n),
            )
        else:
            cursor = await self._db.execute(
                f"SELECT skill, input, error, fix FROM {self._lesson_table} ORDER BY id DESC LIMIT ?",
                (n,),
            )
        rows = await cursor.fetchall()
        if not rows:
            return ""

        lines = ["⚠️ Past failures to avoid:"]
        for skill_name, inp, err, fix in rows:
            line = f"  - Skill `{skill_name}`: tried '{inp[:80]}' → ERROR: {err[:100]}"
            if fix:
                line += f" → FIX: {fix[:80]}"
            lines.append(line)
        return "\n".join(lines)

    async def clear_lessons(self) -> None:
        """Clear all lessons."""
        await self._db.execute(f"DELETE FROM {self._lesson_table}")
        await self._db.commit()
