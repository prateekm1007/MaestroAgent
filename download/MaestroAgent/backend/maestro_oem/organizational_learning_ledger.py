"""Loop 4 — Organizational Learning Ledger.

CEO directive (auditor recommendation, CEO-validated): "Loop 4 —
Organizational Learning: cross-case pattern detection and delivery-policy
learning. This is the final loop — it connects the first three loops into
a unified learning system."

The OrganizationalLearningLedger collects Learning Ledger entries from
all 3 loops:
  - Loop 1: commitment learnings (whisper_id, action, outcome, learning_entry)
  - Loop 2: meeting learnings (meeting_id, outcome, learning_entry)
  - Loop 3: decision learnings (decision_id, hypothesis, outcome, learning_entry)

Each entry is tagged with its source_loop ("commitment", "meeting",
"decision") so the CrossLoopPatternDetector can find patterns that span
loops.

This is the unified memory. Loops 1-3 each had their own Learning Ledger;
Loop 4 aggregates them so the system can learn about its own delivery
effectiveness.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class LearningEntry:
    """A single learning entry from any of the 3 loops.

    Attributes:
        source_loop: "commitment" | "meeting" | "decision"
        entity: The customer/org this learning is about
        learning_entry: The honest sentence from the loop's Learning Ledger
        action: For commitment entries — "acted" | "ignored" | "overrode"
        outcome: The observed outcome ("honored", "broken", etc.)
        delivery_context: For commitment entries — when/how the Whisper was delivered
        id: The loop-specific ID (whisper_id, meeting_id, decision_id)
        recorded_at: When this entry was recorded
    """

    source_loop: str
    entity: str
    learning_entry: str
    action: str | None = None
    outcome: str | None = None
    delivery_context: str | None = None
    id: str = ""
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_loop": self.source_loop,
            "entity": self.entity,
            "learning_entry": self.learning_entry,
            "action": self.action,
            "outcome": self.outcome,
            "delivery_context": self.delivery_context,
            "id": self.id,
            "recorded_at": self.recorded_at.isoformat() if hasattr(self.recorded_at, "isoformat") else str(self.recorded_at),
        }


class OrganizationalLearningLedger:
    """Collects Learning Ledger entries from all 3 loops.

    C1 fix: now SQLite-backed when db_path is provided. Falls back to
    in-memory when no db_path (backward-compatible with existing callers).

    Usage:
        ledger = OrganizationalLearningLedger("org_learning.db")
        ledger.record_commitment_learning(entity="<customer>", whisper_id="wspr-1",
            action="ignored", outcome="broken", learning_entry="...")
        all_entries = ledger.get_all_entries()
        ledger.close()
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS org_learning_entries (
        id {pk},
        source_loop TEXT NOT NULL,
        entity TEXT NOT NULL,
        learning_entry TEXT NOT NULL,
        action TEXT,
        outcome TEXT,
        delivery_context TEXT,
        ref_id TEXT,
        recorded_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_org_learning_source ON org_learning_entries(source_loop);
    CREATE INDEX IF NOT EXISTS idx_org_learning_entity ON org_learning_entries(entity);
    """

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path
        self._entries: list[LearningEntry] = []  # in-memory fallback
        self._lock = threading.RLock()
        self._conn = None
        self._use_sqlite = bool(db_path)
        if self._use_sqlite:
            self._connect()

    def _connect(self):
        import sqlite3 as _sqlite3
        try:
            from maestro_db import sqlite_compat as sqlite3_compat
            self._conn = sqlite3_compat.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3_compat.Row
        except Exception:
            self._conn = _sqlite3.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = _sqlite3.Row
        try:
            cursor = self._conn.cursor()
            # C1 fix: format schema with backend-appropriate PK syntax
            from maestro_db.sqlite_compat import autoincrement_syntax
            schema = self._SCHEMA.format(pk=autoincrement_syntax(self._db_path))
            for stmt in schema.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    cursor.execute(stmt)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("OrgLearningLedger schema init: %s", e)

    def record_commitment_learning(
        self,
        entity: str,
        whisper_id: str,
        action: str,
        outcome: str,
        learning_entry: str,
        delivery_context: str | None = None,
    ) -> None:
        """Record a learning entry from Loop 1 (commitment intelligence)."""
        entry = LearningEntry(
            source_loop="commitment",
            entity=entity,
            learning_entry=learning_entry,
            action=action,
            outcome=outcome,
            delivery_context=delivery_context,
            id=whisper_id,
        )
        self._persist(entry)

    def record_meeting_learning(
        self,
        entity: str,
        meeting_id: str,
        outcome: str,
        learning_entry: str,
    ) -> None:
        """Record a learning entry from Loop 2 (meeting intelligence)."""
        entry = LearningEntry(
            source_loop="meeting",
            entity=entity,
            learning_entry=learning_entry,
            outcome=outcome,
            id=meeting_id,
        )
        self._persist(entry)

    def record_decision_learning(
        self,
        entity: str,
        decision_id: str,
        hypothesis: str,
        outcome: str,
        learning_entry: str,
    ) -> None:
        """Record a learning entry from Loop 3 (decision intelligence)."""
        entry = LearningEntry(
            source_loop="decision",
            entity=entity,
            learning_entry=learning_entry,
            outcome=outcome,
            id=decision_id,
        )
        self._persist(entry)

    def _persist(self, entry: LearningEntry) -> None:
        """Persist an entry to SQLite (or in-memory fallback)."""
        with self._lock:
            if self._use_sqlite and self._conn:
                self._conn.execute(
                    """INSERT INTO org_learning_entries
                       (source_loop, entity, learning_entry, action, outcome, delivery_context, ref_id, recorded_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (entry.source_loop, entry.entity, entry.learning_entry,
                     entry.action, entry.outcome, entry.delivery_context,
                     entry.id, entry.recorded_at.isoformat()),
                )
            else:
                self._entries.append(entry)

    def get_all_entries(self) -> list[LearningEntry]:
        """Get all learning entries from all 3 loops."""
        with self._lock:
            if self._use_sqlite and self._conn:
                cur = self._conn.cursor()
                cur.execute("SELECT * FROM org_learning_entries ORDER BY recorded_at")
                rows = cur.fetchall()
                return [self._row_to_entry(r) for r in rows]
            return list(self._entries)

    def get_entries_by_loop(self, source_loop: str) -> list[LearningEntry]:
        """Get entries from a specific loop."""
        with self._lock:
            if self._use_sqlite and self._conn:
                cur = self._conn.cursor()
                cur.execute("SELECT * FROM org_learning_entries WHERE source_loop = ? ORDER BY recorded_at", (source_loop,))
                rows = cur.fetchall()
                return [self._row_to_entry(r) for r in rows]
            return [e for e in self._entries if e.source_loop == source_loop]

    def total_entries(self) -> int:
        """Total number of learning entries across all loops."""
        with self._lock:
            if self._use_sqlite and self._conn:
                cur = self._conn.cursor()
                cur.execute("SELECT COUNT(*) as cnt FROM org_learning_entries")
                row = cur.fetchone()
                if row is None:
                    return 0
                if isinstance(row, dict):
                    return row.get("cnt", 0)
                try:
                    return row[0]
                except (KeyError, IndexError):
                    return row["cnt"] if "cnt" in (row.keys() if hasattr(row, 'keys') else []) else 0
            return len(self._entries)

    def clear(self) -> None:
        """Clear all entries (for testing)."""
        with self._lock:
            if self._use_sqlite and self._conn:
                self._conn.execute("DELETE FROM org_learning_entries")
            else:
                self._entries.clear()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _row_to_entry(self, row) -> LearningEntry:
        d = row if isinstance(row, dict) else {k: row[k] for k in (row.keys() if hasattr(row, 'keys') else range(len(row)))}
        return LearningEntry(
            source_loop=d.get("source_loop", ""),
            entity=d.get("entity", ""),
            learning_entry=d.get("learning_entry", ""),
            action=d.get("action"),
            outcome=d.get("outcome"),
            delivery_context=d.get("delivery_context"),
            id=d.get("ref_id", ""),
            recorded_at=datetime.fromisoformat(d["recorded_at"]) if d.get("recorded_at") else datetime.now(timezone.utc),
        )
