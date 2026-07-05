"""Step 3: SQLite-backed conversation state for multi-turn Ask Maestro.

Enables pronoun resolution and entity carry-forward across turns.
"What did we promise TestCorp?" → "What about their pricing concern?"
The second turn resolves "their" → TestCorp from the first turn's context.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    intent TEXT,
    entities TEXT,
    evidence_refs TEXT,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_history(session_id);
"""


class ConversationStore:
    """SQLite-backed conversation history for multi-turn Ask Maestro."""

    def __init__(self, db_path: str | Path = "") -> None:
        self._db_path = str(db_path) if db_path else ":memory:"
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            from maestro_db import sqlite_compat as sqlite3_compat
            self._conn = sqlite3_compat.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3_compat.Row
        except Exception:
            self._conn = sqlite3.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
        try:
            cursor = self._conn.cursor()
            for stmt in _SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    cursor.execute(stmt)
        except Exception as e:
            logger.warning("ConversationStore schema init: %s", e)

    def add_turn(
        self,
        session_id: str,
        turn: int,
        role: str,
        content: str,
        intent: str = "",
        entities: list[str] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> None:
        """Add a conversation turn."""
        from datetime import datetime, timezone
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                """INSERT INTO conversation_history
                   (session_id, turn, role, content, intent, entities, evidence_refs, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, turn, role, content, intent,
                 json.dumps(entities or []), json.dumps(evidence_refs or []),
                 datetime.now(timezone.utc).isoformat()),
            )

    def get_history(self, session_id: str, last_n: int = 10) -> list[dict[str, Any]]:
        """Get conversation history for a session."""
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM conversation_history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, last_n),
            )
            rows = cur.fetchall()
            result = []
            for row in reversed(rows):  # Reverse to get chronological order
                if isinstance(row, dict):
                    d = row
                else:
                    keys = row.keys() if hasattr(row, 'keys') else []
                    d = {k: row[k] for k in keys} if keys else {}
                d["entities"] = json.loads(d.get("entities", "[]"))
                d["evidence_refs"] = json.loads(d.get("evidence_refs", "[]"))
                result.append(d)
            return result

    def get_last_entities(self, session_id: str) -> list[str]:
        """Get entities from the most recent turns (for pronoun resolution)."""
        history = self.get_history(session_id, last_n=4)
        entities = []
        for turn in reversed(history):
            for e in turn.get("entities", []):
                if e not in entities:
                    entities.append(e)
        return entities

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
