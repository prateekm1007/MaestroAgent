"""Long-term memory — SQLite-backed episodic store.

The long-term tier stores "episodes": promoted snapshots of important
moments in a run (a successful fix, a debate resolution, a final
artifact). Episodes are tagged with the run_id, agent_id, scope, and
free-form tags for later retrieval.

Unlike the vector tier (which is for similarity recall), the long-term
tier is for *exact* recall: "give me the final output of run X" or
"give me all episodes tagged 'architecture-decision' from last week".

Promotion policy: agents and verifiers can promote a memory entry to
long-term by calling `manager.promote(entry_id)`. The manager copies
the entry from short-term/semantic into the long-term table with a
promotion timestamp.
"""

from __future__ import annotations

import json
from maestro_db import sqlite_compat as sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes(
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_id TEXT,
    scope TEXT,
    summary TEXT,
    content TEXT,
    tags_json TEXT,
    provenance_json TEXT,
    created_at TEXT NOT NULL,
    promoted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodes_run ON episodes(run_id);
CREATE INDEX IF NOT EXISTS idx_episodes_agent ON episodes(agent_id);
CREATE INDEX IF NOT EXISTS idx_episodes_scope ON episodes(scope);
CREATE INDEX IF NOT EXISTS idx_episodes_tags ON episodes(tags_json);
"""


class LongTermMemory:
    """SQLite-backed long-term episodic memory."""

    def __init__(self, db_path: str | Path = "maestro.db") -> None:
        self.db_path = str(db_path)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()
        self._conn: sqlite3.Connection | None = None

    def _conn_get(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    async def write(
        self,
        run_id: str,
        agent_id: str | None,
        scope: str,
        content: str,
        summary: str | None = None,
        tags: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> str:
        eid = str(uuid.uuid4())
        conn = self._conn_get()
        conn.execute(
            "INSERT INTO episodes (id, run_id, agent_id, scope, summary, content, "
            "tags_json, provenance_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eid,
                run_id,
                agent_id,
                scope,
                summary or content[:200],
                content,
                json.dumps(tags or []),
                json.dumps(provenance or {}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return eid

    async def promote(self, episode_id: str) -> bool:
        conn = self._conn_get()
        cur = conn.execute(
            "UPDATE episodes SET promoted_at = ? WHERE id = ? AND promoted_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), episode_id),
        )
        conn.commit()
        return cur.rowcount > 0

    async def get(self, episode_id: str) -> dict[str, Any] | None:
        conn = self._conn_get()
        row = conn.execute(
            "SELECT * FROM episodes WHERE id = ?", (episode_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    async def list_by_run(self, run_id: str, promoted_only: bool = False) -> list[dict[str, Any]]:
        conn = self._conn_get()
        sql = "SELECT * FROM episodes WHERE run_id = ?"
        if promoted_only:
            sql += " AND promoted_at IS NOT NULL"
        sql += " ORDER BY created_at ASC"
        rows = conn.execute(sql, (run_id,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def list_by_tag(self, tag: str, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn_get()
        # JSON contains — works for SQLite's json1.
        rows = conn.execute(
            "SELECT * FROM episodes WHERE tags_json LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f'%"{tag}"%', limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Naive substring search across summary + content."""
        conn = self._conn_get()
        rows = conn.execute(
            "SELECT * FROM episodes WHERE summary LIKE ? OR content LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "agent_id": row["agent_id"],
            "scope": row["scope"],
            "summary": row["summary"],
            "content": row["content"],
            "tags": json.loads(row["tags_json"]),
            "provenance": json.loads(row["provenance_json"]),
            "created_at": row["created_at"],
            "promoted_at": row["promoted_at"],
        }
