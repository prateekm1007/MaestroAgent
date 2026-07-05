"""Loop 3 — DecisionStore: SQLite-backed persistence for decisions.

C1 fix (ADVERSARIAL-AUDIT-24PHASE): _loop3_decision_store was a module-level
dict — lost on restart. This store is SQLite-backed, following the same
pattern as WhisperHistoryStore and MeetingStore.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maestro_oem.decision_v2 import Decision, DecisionStatus

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    entity TEXT NOT NULL,
    status TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_entity ON decisions(entity);
CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
"""


class DecisionStore:
    """SQLite-backed store for Decision objects.

    Usage:
        store = DecisionStore("decisions.db")
        store.record(decision)
        recovered = store.get(decision_id)
        store.close()
    """

    def __init__(self, db_path: str | Path = "") -> None:
        self._db_path = str(db_path) if db_path else ":memory:"
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._in_memory: dict[str, Decision] = {}
        self._use_sqlite = bool(db_path)
        if self._use_sqlite:
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
            logger.warning("DecisionStore schema init: %s", e)

    def record(self, decision: Decision) -> None:
        if not self._use_sqlite:
            with self._lock:
                self._in_memory[decision.decision_id] = decision
            return
        with self._lock:
            assert self._conn is not None
            data = json.dumps(decision.to_dict(), default=str)
            self._conn.execute(
                """INSERT OR REPLACE INTO decisions (decision_id, entity, status, data)
                   VALUES (?, ?, ?, ?)""",
                (decision.decision_id, decision.entity, decision.status.name, data),
            )

    def get(self, decision_id: str) -> Decision | None:
        if not self._use_sqlite:
            with self._lock:
                return self._in_memory.get(decision_id)
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM decisions WHERE decision_id = ?", (decision_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._deserialize(row["data"] if isinstance(row, dict) else row[0])

    def get_all(self) -> list[Decision]:
        if not self._use_sqlite:
            with self._lock:
                return list(self._in_memory.values())
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM decisions")
            rows = cur.fetchall()
            return [self._deserialize(r["data"] if isinstance(r, dict) else r[0]) for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _deserialize(self, data_str: str) -> Decision:
        d = json.loads(data_str)
        decision = Decision(
            intent=d.get("intent", ""),
            entity=d.get("entity", ""),
            decision_id=d.get("decision_id", ""),
        )
        decision.status = DecisionStatus[d.get("status", "PROPOSED")]
        decision.assumptions = d.get("assumptions", [])
        decision.hypothesis = d.get("hypothesis")
        decision.decision_text = d.get("decision_text")
        decision.outcome = d.get("outcome")
        decision.learning_entry = d.get("learning_entry")
        if d.get("created_at"):
            try:
                decision.created_at = datetime.fromisoformat(d["created_at"])
            except Exception:
                pass
        return decision
