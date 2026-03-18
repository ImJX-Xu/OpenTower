"""SQLite State Wall — persistent EMP trace log.

Records every EMP packet that flows through the system so the agents
can retrieve full context chains and the operator can audit the trace.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import aiosqlite

from opentower.schema.emp import EMPPacket

logger = logging.getLogger("opentower.memory")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS emp_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id        TEXT    NOT NULL,
    parent_trace_id TEXT,
    source          TEXT    NOT NULL,
    target          TEXT,
    intent_type     TEXT    NOT NULL,
    action          TEXT    NOT NULL,
    payload_json    TEXT    NOT NULL,
    token_budget    INTEGER NOT NULL,
    timestamp       TEXT    NOT NULL
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trace ON emp_log(trace_id);
"""


class StateWall:
    """Async SQLite-backed log of all EMP packets.

    Usage::

        wall = StateWall("opentower.db")
        await wall.open()
        await wall.record(packet)
        history = await wall.query_by_trace("abc123")
        await wall.close()
    """

    def __init__(self, db_path: str | Path = "opentower.db") -> None:
        self._db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_CREATE_TABLE)
        await self._db.execute(_CREATE_INDEX)
        await self._db.commit()
        logger.info("StateWall opened: %s", self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("StateWall closed")

    async def record(self, packet: EMPPacket) -> None:
        """Persist a single EMP packet."""
        assert self._db is not None, "StateWall not opened"
        await self._db.execute(
            """INSERT INTO emp_log
               (trace_id, parent_trace_id, source, target,
                intent_type, action, payload_json, token_budget, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                packet.trace_id,
                packet.parent_trace_id,
                packet.source,
                packet.target,
                packet.intent_type,
                packet.action,
                json.dumps(packet.payload, ensure_ascii=False),
                packet.token_budget,
                packet.timestamp.isoformat(),
            ),
        )
        await self._db.commit()

    async def query_by_trace(self, trace_id: str) -> list[dict]:
        """Return all packets sharing the same initial trace_id lineage."""
        assert self._db is not None, "StateWall not opened"
        cursor = await self._db.execute(
            """SELECT * FROM emp_log
               WHERE trace_id = ? OR parent_trace_id = ?
               ORDER BY id""",
            (trace_id, trace_id),
        )
        rows = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in rows]

    async def get_recent(self, n: int = 10) -> list[dict]:
        """Return the *n* most recent packets (newest first)."""
        assert self._db is not None, "StateWall not opened"
        cursor = await self._db.execute(
            "SELECT * FROM emp_log ORDER BY id DESC LIMIT ?", (n,)
        )
        rows = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
