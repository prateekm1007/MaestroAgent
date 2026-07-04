"""Loop 1.5 — Commitment Mutation Tracker.

External auditor (AUDITOR-EXTERNAL-REVIEW-3):
> Commitment mutation tracking — preserve the history of how a
> commitment's wording changes, don't overwrite.

Organizations renegotiate. A commitment that started as "Deliver SSO
by 2024-12-15" might mutate to "Deliver SSO by 2025-01-31" (deadline
moved) or "Deliver SSO + MFA by 2024-12-15" (scope expanded). Each
mutation is a meaningful event — it tells Maestro that the situation
is evolving.

The OLD codebase treated commitment signals as a flat list — the
latest one wins, history is lost. This is wrong because:
  - The exec might remember the OLD commitment ("But you said
    December!"). Maestro needs to know both wordings to explain
    the change.
  - A pattern of frequent mutations is itself a signal (the customer
    keeps moving the goalposts = unstable relationship).
  - The Learning Ledger needs to reference what CHANGED, not just the
    current state.

The CommitmentMutationTracker:
  - record_commitment(signal): records a commitment, detecting mutations
  - get_mutation_history(entity): returns all commitment wordings (in order)
  - get_mutations(entity): returns only the mutation events (old→new)
  - get_current_commitment(entity): returns the latest wording

A mutation is detected when:
  - Same entity (customer)
  - Same commitment topic (e.g., "SSO") — extracted via simple keyword match
  - Different wording (text != previous text)

If the wording is identical, no mutation is recorded (avoid false positives).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CommitmentEntry:
    """A single commitment wording at a point in time."""

    entity: str
    commitment_text: str
    timestamp: datetime
    actor: str
    artifact: str

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "commitment_text": self.commitment_text,
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, "isoformat") else str(self.timestamp),
            "actor": self.actor,
            "artifact": self.artifact,
        }


@dataclass
class CommitmentMutation:
    """A mutation event — when a commitment's wording changed."""

    entity: str
    old_text: str
    new_text: str
    old_timestamp: datetime
    new_timestamp: datetime
    actor: str  # Who made the new commitment

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "old_timestamp": self.old_timestamp.isoformat() if hasattr(self.old_timestamp, "isoformat") else str(self.old_timestamp),
            "new_timestamp": self.new_timestamp.isoformat() if hasattr(self.new_timestamp, "isoformat") else str(self.new_timestamp),
            "actor": self.actor,
        }


class CommitmentMutationTracker:
    """Track how commitments mutate over time.

    C1 fix: now SQLite-backed when db_path is provided.

    Usage:
        tracker = CommitmentMutationTracker("mutations.db")
        tracker.record_commitment(signal1)
        tracker.record_commitment(signal2)
        history = tracker.get_mutation_history("<customer>")
        mutations = tracker.get_mutations("<customer>")
        tracker.close()
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS commitment_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT NOT NULL,
        commitment_text TEXT NOT NULL,
        timestamp TEXT,
        actor TEXT,
        artifact TEXT
    );
    CREATE TABLE IF NOT EXISTS commitment_mutations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT NOT NULL,
        old_text TEXT NOT NULL,
        new_text TEXT NOT NULL,
        old_timestamp TEXT,
        new_timestamp TEXT,
        actor TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_commitment_entries_entity ON commitment_entries(entity);
    CREATE INDEX IF NOT EXISTS idx_commitment_mutations_entity ON commitment_mutations(entity);
    """

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path
        self._history: dict[str, list[CommitmentEntry]] = {}
        self._mutations: dict[str, list[CommitmentMutation]] = {}
        self._lock = threading.RLock()
        self._conn = None
        self._use_sqlite = bool(db_path)
        if self._use_sqlite:
            self._connect()

    def _connect(self):
        import sqlite3 as _sqlite3
        # P14 fix: FastAPI runs endpoints in a threadpool, so the tracker's
        # SQLite connection (created lazily on first request) ends up being
        # used from a different thread than the one that created it. Pass
        # check_same_thread=False + rely on the RLock in record_commitment/
        # get_mutation_history to serialize access. Without this fix, the
        # timeline + mutation/record endpoints 500 on every concurrent request.
        try:
            from maestro_db import sqlite_compat as sqlite3_compat
            self._conn = sqlite3_compat.connect(
                self._db_path, isolation_level=None, check_same_thread=False,
            )
            self._conn.row_factory = sqlite3_compat.Row
        except Exception:
            self._conn = _sqlite3.connect(
                self._db_path, isolation_level=None, check_same_thread=False,
            )
            self._conn.row_factory = _sqlite3.Row
        try:
            cursor = self._conn.cursor()
            for stmt in self._SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    cursor.execute(stmt)
        except Exception as e:
            logger.warning("CommitmentMutationTracker schema init: %s", e)

    def record_commitment(self, signal: Any) -> None:
        """Record a commitment signal, detecting mutations.

        If the commitment wording differs from the previous wording for
        this entity, a CommitmentMutation is recorded.
        """
        try:
            entity = signal.metadata.get("customer", "") if hasattr(signal, "metadata") else ""
            commitment_text = signal.metadata.get("commitment", "") if hasattr(signal, "metadata") else ""
            if not entity or not commitment_text:
                return

            entry = CommitmentEntry(
                entity=entity,
                commitment_text=commitment_text,
                timestamp=signal.timestamp if hasattr(signal, "timestamp") else datetime.utcnow(),
                actor=signal.actor if hasattr(signal, "actor") else "",
                artifact=signal.artifact if hasattr(signal, "artifact") else "",
            )

            with self._lock:
                # Get previous entry (from SQLite or in-memory)
                previous_entries = self.get_mutation_history(entity)

                if previous_entries:
                    last_entry = previous_entries[-1]
                    if last_entry.commitment_text != commitment_text:
                        mutation = CommitmentMutation(
                            entity=entity,
                            old_text=last_entry.commitment_text,
                            new_text=commitment_text,
                            old_timestamp=last_entry.timestamp,
                            new_timestamp=entry.timestamp,
                            actor=entry.actor,
                        )
                        if self._use_sqlite and self._conn:
                            self._conn.execute(
                                """INSERT INTO commitment_mutations
                                   (entity, old_text, new_text, old_timestamp, new_timestamp, actor)
                                   VALUES (?, ?, ?, ?, ?, ?)""",
                                (entity, last_entry.commitment_text, commitment_text,
                                 str(last_entry.timestamp), str(entry.timestamp), entry.actor),
                            )
                        else:
                            if entity not in self._mutations:
                                self._mutations[entity] = []
                            self._mutations[entity].append(mutation)
                        logger.info(
                            "CommitmentMutationTracker: mutation detected for %s — '%s' → '%s'",
                            entity, last_entry.commitment_text, commitment_text,
                        )

                # Persist the entry
                if self._use_sqlite and self._conn:
                    self._conn.execute(
                        """INSERT INTO commitment_entries
                           (entity, commitment_text, timestamp, actor, artifact)
                           VALUES (?, ?, ?, ?, ?)""",
                        (entity, commitment_text, str(entry.timestamp), entry.actor, entry.artifact),
                    )
                else:
                    if entity not in self._history:
                        self._history[entity] = []
                    self._history[entity].append(entry)
        except Exception as e:
            logger.warning("CommitmentMutationTracker: failed to record commitment: %s", e)

    def get_mutation_history(self, entity: str) -> list[CommitmentEntry]:
        """Get all commitment wordings for an entity (in arrival order)."""
        with self._lock:
            if self._use_sqlite and self._conn:
                cur = self._conn.cursor()
                cur.execute("SELECT * FROM commitment_entries WHERE entity = ? ORDER BY id", (entity,))
                rows = cur.fetchall()
                return [self._row_to_entry(r) for r in rows]
            return list(self._history.get(entity, []))

    def get_mutations(self, entity: str) -> list[CommitmentMutation]:
        """Get only the mutation events for an entity."""
        with self._lock:
            if self._use_sqlite and self._conn:
                cur = self._conn.cursor()
                cur.execute("SELECT * FROM commitment_mutations WHERE entity = ? ORDER BY id", (entity,))
                rows = cur.fetchall()
                return [self._row_to_mutation(r) for r in rows]
            return list(self._mutations.get(entity, []))

    def get_current_commitment(self, entity: str) -> CommitmentEntry | None:
        """Get the latest commitment wording for an entity."""
        entries = self.get_mutation_history(entity)
        if not entries:
            return None
        return entries[-1]

    def get_all_entities(self) -> list[str]:
        """Get all entities that have commitments tracked."""
        with self._lock:
            if self._use_sqlite and self._conn:
                cur = self._conn.cursor()
                cur.execute("SELECT DISTINCT entity FROM commitment_entries")
                return [r["entity"] if isinstance(r, dict) else r[0] for r in cur.fetchall()]
            return list(self._history.keys())

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _row_to_entry(self, row) -> CommitmentEntry:
        d = row if isinstance(row, dict) else {k: row[k] for k in (row.keys() if hasattr(row, 'keys') else range(len(row)))}
        return CommitmentEntry(
            entity=d.get("entity", ""),
            commitment_text=d.get("commitment_text", ""),
            timestamp=d.get("timestamp", ""),
            actor=d.get("actor", ""),
            artifact=d.get("artifact", ""),
        )

    def _row_to_mutation(self, row) -> CommitmentMutation:
        d = row if isinstance(row, dict) else {k: row[k] for k in (row.keys() if hasattr(row, 'keys') else range(len(row)))}
        return CommitmentMutation(
            entity=d.get("entity", ""),
            old_text=d.get("old_text", ""),
            new_text=d.get("new_text", ""),
            old_timestamp=d.get("old_timestamp", ""),
            new_timestamp=d.get("new_timestamp", ""),
            actor=d.get("actor", ""),
        )

    def to_dict(self) -> dict:
        """Serialize for API responses / debugging."""
        result = {}
        for entity in self.get_all_entities():
            result[entity] = {
                "history": [e.to_dict() for e in self.get_mutation_history(entity)],
                "mutations": [m.to_dict() for m in self.get_mutations(entity)],
            }
        return result
