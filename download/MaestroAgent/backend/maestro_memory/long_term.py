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
import logging
from maestro_db import sqlite_compat as sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maestro_memory.vector import VectorMemory

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes(
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_id TEXT,
    scope TEXT,
    org_id TEXT NOT NULL DEFAULT 'default',
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
CREATE INDEX IF NOT EXISTS idx_episodes_org ON episodes(org_id);
"""


class LongTermMemory:
    """SQLite-backed long-term episodic memory.

    When a ``VectorMemory`` is provided at construction, episodes are also
    indexed into the vector store on write, and search() queries the vector
    layer first (semantic ranking), falling back to SQL LIKE only when no
    vector is configured or the vector query returns nothing. The fallback
    is logged loudly (Principle 6: no silent swallows).
    """

    def __init__(
        self,
        db_path: str | Path = "maestro.db",
        vector: "VectorMemory | None" = None,
        org_id: str = "default",
    ) -> None:
        """Initialize the long-term memory store.

        ``org_id`` scopes all queries to a single organization (Principle 7).
        Two LongTermMemory instances with different org_ids sharing the same
        DB file must never see each other's episodes. Before this fix, the
        episodes table had no org_id column — any tenant could read any
        other tenant's episodic memories.

        Phase 4.2 fix (auditor recommendation #4): default to
        InMemoryVectorMemory when no vector backend is provided. Before this
        fix, LongTermMemory(db_path=':memory:') had vector=None and fell
        back to SQL LIKE. Now it always has a vector backend (TF-IDF by
        default, ChromaDB when available, neural when sentence-transformers
        is installed).
        """
        self.db_path = str(db_path)
        # Default to InMemoryVectorMemory so search() always has a vector
        # backend. The caller can override with ChromaVectorMemory or a
        # neural backend. Without this default, search() falls back to SQL
        # LIKE — which the auditor correctly flagged as "not semantic."
        if vector is None:
            from maestro_memory.vector import InMemoryVectorMemory
            vector = InMemoryVectorMemory()
        self.vector = vector
        self.org_id = org_id
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
        # INSERT includes org_id
        conn.execute(
            "INSERT INTO episodes (id, run_id, agent_id, scope, org_id, summary, content, "
            "tags_json, provenance_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eid,
                run_id,
                agent_id,
                scope,
                self.org_id,
                summary or content[:200],
                content,
                json.dumps(tags or []),
                json.dumps(provenance or {}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        # Index into the vector store so search() can rank semantically.
        if self.vector is not None:
            try:
                await self.vector.add(
                    run_id=run_id,
                    agent_id=agent_id,
                    scope=scope,
                    content=summary or content,
                    metadata={"episode_id": eid, "org_id": self.org_id},
                )
            except Exception:
                # Principle 6: log loudly, don't silently swallow. SQLite is
                # the source of truth; a vector index failure is non-fatal but
                # must be visible.
                logger.warning(
                    "Vector index failed for episode %s — search will fall back to SQL LIKE", eid,
                    exc_info=True,
                )
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
        """Get an episode by ID. Returns None if not found OR if the episode
        belongs to a different org (Principle 7: isolation by default)."""
        conn = self._conn_get()
        row = conn.execute(
            "SELECT * FROM episodes WHERE id = ? AND org_id = ?",
            (episode_id, self.org_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    async def list_by_run(self, run_id: str, promoted_only: bool = False) -> list[dict[str, Any]]:
        """List episodes for a run, scoped to self.org_id."""
        conn = self._conn_get()
        sql = "SELECT * FROM episodes WHERE run_id = ? AND org_id = ?"
        if promoted_only:
            sql += " AND promoted_at IS NOT NULL"
        sql += " ORDER BY created_at ASC"
        rows = conn.execute(sql, (run_id, self.org_id)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def list_by_tag(self, tag: str, limit: int = 50) -> list[dict[str, Any]]:
        """List episodes by tag, scoped to self.org_id."""
        conn = self._conn_get()
        rows = conn.execute(
            "SELECT * FROM episodes WHERE tags_json LIKE ? AND org_id = ? ORDER BY created_at DESC LIMIT ?",
            (f'%"{tag}"%', self.org_id, limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search across summary + content.

        When a ``VectorMemory`` is configured, queries the vector layer first
        for semantic ranking, then hydrates the matching SQLite rows. Falls
        back to SQL LIKE (substring) only when no vector is configured or the
        vector query returns nothing. The fallback is logged loudly (P6).

        Principle 1 note: the prior version of this method (the "Round 53 H3
        fix" docstring above) instantiated ``VectorMemory()`` — an ABC that
        raises TypeError — and called ``.search()`` — a method that does not
        exist on the interface. Both errors were swallowed by a bare
        ``except Exception: pass``, so every call fell through to SQL LIKE
        while the docstring claimed semantic ranking. This is the C1 bug from
        the forensic audit. Fixed below to use the real ``.query()`` interface
        on an injected concrete subclass.
        """
        if self.vector is not None:
            try:
                entries = await self.vector.query(query_text=query, top_k=limit)
            except Exception:
                logger.warning(
                    "Vector query failed — falling back to SQL LIKE", exc_info=True,
                )
                entries = []
            if entries:
                # Filter vector results by org_id (the vector store is shared
                # across orgs — only return entries belonging to self.org_id).
                wanted = [
                    e.metadata.get("episode_id")
                    for e in entries
                    if e.metadata.get("episode_id")
                    and e.metadata.get("org_id") == self.org_id
                ]
                hydrated = await self._hydrate_by_ids(wanted)
                id_to_row = {r["id"]: r for r in hydrated}
                ordered = [id_to_row[eid] for eid in wanted if eid in id_to_row]
                if ordered:
                    return ordered
                logger.warning("Vector returned entries but none matched SQLite rows — falling back to SQL LIKE")
            else:
                logger.warning("Vector query returned no entries — falling back to SQL LIKE")

        # Fallback: SQL LIKE (substring matching), scoped to org_id.
        conn = self._conn_get()
        rows = conn.execute(
            "SELECT * FROM episodes WHERE org_id = ? AND (summary LIKE ? OR content LIKE ?) "
            "ORDER BY created_at DESC LIMIT ?",
            (self.org_id, f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def _hydrate_by_ids(self, episode_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch full episode rows for a list of ids, scoped to org_id."""
        if not episode_ids:
            return []
        conn = self._conn_get()
        placeholders = ",".join("?" * len(episode_ids))
        rows = conn.execute(
            f"SELECT * FROM episodes WHERE id IN ({placeholders}) AND org_id = ?",
            (*episode_ids, self.org_id),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "agent_id": row["agent_id"],
            "scope": row["scope"],
            "org_id": row["org_id"],
            "summary": row["summary"],
            "content": row["content"],
            "tags": json.loads(row["tags_json"]),
            "provenance": json.loads(row["provenance_json"]),
            "created_at": row["created_at"],
            "promoted_at": row["promoted_at"],
        }
