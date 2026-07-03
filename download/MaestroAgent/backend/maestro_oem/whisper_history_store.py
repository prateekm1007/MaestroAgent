"""Whisper History Store — durable persistence for whisper memory.

CEO Feature 2 (Whisper Card Memory) and Feature 3 (Urgency Decay) require
state that survives server restarts. This store persists:
  - whisper_id: unique identifier per whisper
  - shown_count: how many times this whisper has been shown
  - action_taken: "acted" | "ignored" | "overrode" | None
  - first_shown: ISO timestamp of first display (for urgency decay)
  - last_shown: ISO timestamp of most recent display

The store is SQLite-backed (same as CheckpointStore) and org-scoped
for multi-tenant isolation (P7).

External reviewer H1 (2026-07-03): "Whisper memory is in-process only,
not durably persisted. The history resets on every server restart."
This store fixes that — memory now survives restarts.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS whisper_history (
    whisper_id TEXT NOT NULL,
    org_id TEXT NOT NULL DEFAULT 'default',
    shown_count INTEGER NOT NULL DEFAULT 0,
    action_taken TEXT,
    first_shown TEXT,
    last_shown TEXT,
    insight TEXT,
    PRIMARY KEY (whisper_id, org_id)
);

CREATE INDEX IF NOT EXISTS idx_whisper_history_org ON whisper_history(org_id);
"""


class WhisperHistoryStore:
    """Durable persistence for whisper memory (survives server restarts).

    Usage:
        store = WhisperHistoryStore("whisper_history.db")
        store.record_shown("wspr-test", org_id="default", insight="test")
        store.record_outcome("wspr-test", org_id="default", action="ignored")
        history = store.get_history("wspr-test", org_id="default")
        # history = {"shown_count": 1, "action_taken": "ignored", "first_shown": "...", "last_shown": "..."}
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        """Open the SQLite connection and initialize the schema."""
        from maestro_db import sqlite_compat as sqlite3_compat
        try:
            self._conn = sqlite3_compat.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3_compat.Row
        except Exception:
            # Fall back to raw sqlite3 if sqlite_compat is unavailable
            self._conn = sqlite3.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3.Row

        # Execute schema (idempotent)
        try:
            cursor = self._conn.cursor()
            for stmt in _SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    cursor.execute(stmt)
        except Exception as e:
            logger.warning("WhisperHistoryStore schema init: %s", e)

    def record_shown(self, whisper_id: str, org_id: str = "default", insight: str = "") -> None:
        """Record that a whisper was shown. Increments shown_count."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            # Upsert: insert or update
            cur.execute(
                """INSERT INTO whisper_history (whisper_id, org_id, shown_count, action_taken, first_shown, last_shown, insight)
                   VALUES (?, ?, 1, NULL, ?, ?, ?)
                   ON CONFLICT(whisper_id, org_id) DO UPDATE SET
                    shown_count = shown_count + 1,
                    last_shown = excluded.last_shown,
                    insight = COALESCE(excluded.insight, whisper_history.insight)
                """,
                (whisper_id, org_id, now, now, insight),
            )

    def record_outcome(self, whisper_id: str, action: str, org_id: str = "default") -> None:
        """Record what the user did with a whisper (acted/ignored/overrode)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            # Update the existing record (it must have been shown first)
            cur.execute(
                """UPDATE whisper_history
                   SET action_taken = ?, last_shown = ?
                   WHERE whisper_id = ? AND org_id = ?
                """,
                (action, now, whisper_id, org_id),
            )
            # If no row was updated (whisper not yet in DB), insert it
            if cur.rowcount == 0:
                cur.execute(
                    """INSERT INTO whisper_history (whisper_id, org_id, shown_count, action_taken, first_shown, last_shown, insight)
                       VALUES (?, ?, 0, ?, ?, ?, '')
                    """,
                    (whisper_id, org_id, action, now, now),
                )

    def get_history(self, whisper_id: str, org_id: str = "default") -> dict[str, Any]:
        """Get the history for a whisper. Returns empty dict if not found."""
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM whisper_history WHERE whisper_id = ? AND org_id = ?",
                (whisper_id, org_id),
            )
            row = cur.fetchone()
            if not row:
                return {
                    "shown_count": 0,
                    "action_taken": None,
                    "first_shown": None,
                    "last_shown": None,
                }

            # Handle both dict (sqlite_compat) and sqlite3.Row
            if isinstance(row, dict):
                return {
                    "shown_count": row.get("shown_count", 0),
                    "action_taken": row.get("action_taken"),
                    "first_shown": row.get("first_shown"),
                    "last_shown": row.get("last_shown"),
                }
            else:
                return {
                    "shown_count": row["shown_count"],
                    "action_taken": row["action_taken"],
                    "first_shown": row["first_shown"],
                    "last_shown": row["last_shown"],
                }

    def get_all_history(self, org_id: str = "default") -> dict[str, dict[str, Any]]:
        """Get all whisper history for an org. Returns {whisper_id: {history}}."""
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM whisper_history WHERE org_id = ?",
                (org_id,),
            )
            rows = cur.fetchall()
            result = {}
            for row in rows:
                if isinstance(row, dict):
                    wid = row.get("whisper_id", "")
                    result[wid] = {
                        "shown_count": row.get("shown_count", 0),
                        "action_taken": row.get("action_taken"),
                        "first_shown": row.get("first_shown"),
                        "last_shown": row.get("last_shown"),
                    }
                else:
                    wid = row["whisper_id"]
                    result[wid] = {
                        "shown_count": row["shown_count"],
                        "action_taken": row["action_taken"],
                        "first_shown": row["first_shown"],
                        "last_shown": row["last_shown"],
                    }
            return result

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
