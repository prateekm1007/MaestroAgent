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
    embedding BLOB,
    entity TEXT,
    type TEXT,
    recipient TEXT,
    reason_recipient_chosen TEXT,
    timing_reason TEXT,
    depth TEXT,
    materially_changed_since_last_shown BOOLEAN,
    decision_influenced TEXT,
    follow_up_questions TEXT,
    outcome TEXT,
    learning_entry TEXT,
    PRIMARY KEY (whisper_id, org_id)
);

CREATE INDEX IF NOT EXISTS idx_whisper_history_org ON whisper_history(org_id);
"""

# Phase 2: idempotent column adds for existing databases that pre-date
# the embedding/entity/type columns. ALTER TABLE ... ADD COLUMN fails
# silently if the column already exists (caught by the try/except below).
_MIGRATIONS = [
    "ALTER TABLE whisper_history ADD COLUMN embedding BLOB",
    "ALTER TABLE whisper_history ADD COLUMN entity TEXT",
    "ALTER TABLE whisper_history ADD COLUMN type TEXT",
    # Loop 1 iteration: Delivery Intelligence + Learning Ledger columns
    "ALTER TABLE whisper_history ADD COLUMN recipient TEXT",
    "ALTER TABLE whisper_history ADD COLUMN reason_recipient_chosen TEXT",
    "ALTER TABLE whisper_history ADD COLUMN timing_reason TEXT",
    "ALTER TABLE whisper_history ADD COLUMN depth TEXT",
    "ALTER TABLE whisper_history ADD COLUMN materially_changed_since_last_shown BOOLEAN",
    "ALTER TABLE whisper_history ADD COLUMN decision_influenced TEXT",
    "ALTER TABLE whisper_history ADD COLUMN follow_up_questions TEXT",
    "ALTER TABLE whisper_history ADD COLUMN outcome TEXT",
    "ALTER TABLE whisper_history ADD COLUMN learning_entry TEXT",
]


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
            self._conn = sqlite3.connect(self._db_path, isolation_level=None, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

        # Execute schema (idempotent)
        try:
            cursor = self._conn.cursor()
            for stmt in _SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    cursor.execute(stmt)
            # Phase 2 migrations: add embedding/entity/type columns to
            # pre-existing databases. Each ALTER fails silently if the
            # column already exists (idempotent).
            for stmt in _MIGRATIONS:
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass  # Column already exists
        except Exception as e:
            logger.warning("WhisperHistoryStore schema init: %s", e)

    def record_shown(
        self,
        whisper_id: str,
        org_id: str = "default",
        insight: str = "",
        embedding: bytes | None = None,
        entity: str = "",
        whisper_type: str = "",
        recipient: str = "",
        reason_recipient_chosen: str = "",
        timing_reason: str = "",
        depth: str = "",
        materially_changed_since_last_shown: bool | None = None,
    ) -> None:
        """Record that a whisper was shown. Increments shown_count.

        Phase 2: optionally persists the insight embedding (BLOB), entity,
        and whisper type. These power the hybrid RecallEngine's semantic +
        entity search without re-embedding on every recall.

        Loop 1 iteration: also persists Delivery Intelligence fields
        (recipient, reason_recipient_chosen, timing_reason, depth,
        materially_changed_since_last_shown). These power the Loop 1
        CommitmentIntelligenceLoop's delivery decisions.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            # Upsert: insert or update
            cur.execute(
                """INSERT INTO whisper_history
                   (whisper_id, org_id, shown_count, action_taken, first_shown, last_shown,
                    insight, embedding, entity, type,
                    recipient, reason_recipient_chosen, timing_reason, depth,
                    materially_changed_since_last_shown)
                   VALUES (?, ?, 1, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(whisper_id, org_id) DO UPDATE SET
                    shown_count = shown_count + 1,
                    last_shown = excluded.last_shown,
                    insight = COALESCE(excluded.insight, whisper_history.insight),
                    embedding = COALESCE(excluded.embedding, whisper_history.embedding),
                    entity = COALESCE(excluded.entity, whisper_history.entity),
                    type = COALESCE(excluded.type, whisper_history.type),
                    recipient = COALESCE(excluded.recipient, whisper_history.recipient),
                    reason_recipient_chosen = COALESCE(excluded.reason_recipient_chosen, whisper_history.reason_recipient_chosen),
                    timing_reason = COALESCE(excluded.timing_reason, whisper_history.timing_reason),
                    depth = COALESCE(excluded.depth, whisper_history.depth),
                    materially_changed_since_last_shown = excluded.materially_changed_since_last_shown
                """,
                (whisper_id, org_id, now, now, insight, embedding, entity, whisper_type,
                 recipient, reason_recipient_chosen, timing_reason, depth,
                 materially_changed_since_last_shown),
            )

    def record_outcome(
        self,
        whisper_id: str,
        action: str,
        org_id: str = "default",
        decision_influenced: str | None = None,
        follow_up_questions: list[str] | None = None,
    ) -> None:
        """Record what the user did with a whisper (acted/ignored/overrode).

        Loop 1 iteration: also persists decision_influenced (which decision
        the Whisper affected) and follow_up_questions (what the exec asked
        after seeing the Whisper). follow_up_questions is stored as a JSON
        array string.
        """
        now = datetime.now(timezone.utc).isoformat()
        # Serialize follow_up_questions as JSON
        follow_ups_json = json.dumps(follow_up_questions) if follow_up_questions else None
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            # Update the existing record (it must have been shown first)
            cur.execute(
                """UPDATE whisper_history
                   SET action_taken = ?, last_shown = ?,
                       decision_influenced = COALESCE(?, decision_influenced),
                       follow_up_questions = COALESCE(?, follow_up_questions)
                   WHERE whisper_id = ? AND org_id = ?
                """,
                (action, now, decision_influenced, follow_ups_json, whisper_id, org_id),
            )
            # If no row was updated (whisper not yet in DB), insert it
            if cur.rowcount == 0:
                cur.execute(
                    """INSERT INTO whisper_history
                       (whisper_id, org_id, shown_count, action_taken, first_shown, last_shown, insight,
                        decision_influenced, follow_up_questions)
                       VALUES (?, ?, 0, ?, ?, ?, '', ?, ?)
                    """,
                    (whisper_id, org_id, action, now, now, decision_influenced, follow_ups_json),
                )

    def record_outcome_signal(
        self,
        whisper_id: str,
        outcome: str,
        org_id: str = "default",
    ) -> None:
        """Record the outcome signal observed after the meeting.

        Loop 1 iteration: outcome is a label string — 'honored', 'broken',
        'renegotiated', or 'unknown'. This is the signal that closes the
        loop — it tells Maestro what actually happened.
        """
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                """UPDATE whisper_history
                   SET outcome = ?
                   WHERE whisper_id = ? AND org_id = ?
                """,
                (outcome, whisper_id, org_id),
            )
            # If no row was updated, insert a minimal record
            if cur.rowcount == 0:
                now = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    """INSERT INTO whisper_history
                       (whisper_id, org_id, shown_count, action_taken, first_shown, last_shown, insight, outcome)
                       VALUES (?, ?, 0, NULL, ?, ?, '', ?)
                    """,
                    (whisper_id, org_id, now, now, outcome),
                )

    def record_learning_entry(
        self,
        whisper_id: str,
        learning_entry: str,
        org_id: str = "default",
    ) -> None:
        """Record the Learning Ledger entry (one honest sentence).

        Loop 1 iteration: the LearningLedger module composes this sentence
        from the actual entity, commitment, action, and outcome. This method
        persists it to the store.
        """
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                """UPDATE whisper_history
                   SET learning_entry = ?
                   WHERE whisper_id = ? AND org_id = ?
                """,
                (learning_entry, whisper_id, org_id),
            )
            # If no row was updated, insert a minimal record
            if cur.rowcount == 0:
                now = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    """INSERT INTO whisper_history
                       (whisper_id, org_id, shown_count, action_taken, first_shown, last_shown, insight, learning_entry)
                       VALUES (?, ?, 0, NULL, ?, ?, '', ?)
                    """,
                    (whisper_id, org_id, now, now, learning_entry),
                )

    def get_history(self, whisper_id: str, org_id: str = "default") -> dict[str, Any]:
        """Get the history for a whisper. Returns empty dict if not found.

        Loop 1 iteration: returns all Loop 1 fields (recipient,
        timing_reason, depth, materially_changed_since_last_shown,
        decision_influenced, follow_up_questions, outcome,
        learning_entry) in addition to the Phase 1/2 fields.
        """
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

            return self._row_to_history_dict(row)

    def get_all_history(self, org_id: str = "default") -> dict[str, dict[str, Any]]:
        """Get all whisper history for an org. Returns {whisper_id: {history}}.

        Phase 2: also returns entity, type, and embedding (BLOB) if present.
        Loop 1 iteration: also returns recipient, timing_reason, depth,
        materially_changed_since_last_shown, decision_influenced,
        follow_up_questions, outcome, learning_entry.
        """
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
                history = self._row_to_history_dict(row)
                wid = history.get("whisper_id", "")
                if wid:
                    result[wid] = history
            return result

    def _row_to_history_dict(self, row: Any) -> dict[str, Any]:
        """Convert a SQLite row to a history dict, handling both dict
        (sqlite_compat) and sqlite3.Row formats. Returns all Loop 1 fields."""
        if isinstance(row, dict):
            return self._extract_history_fields(row.get, row)
        else:
            keys = row.keys() if hasattr(row, "keys") else []
            return self._extract_history_fields(lambda k: row[k] if k in keys else None, row)

    def _extract_history_fields(self, get, row) -> dict[str, Any]:
        """Extract all history fields using a getter callable."""
        # Parse follow_up_questions from JSON if present
        follow_ups_raw = get("follow_up_questions")
        follow_ups = None
        if follow_ups_raw:
            try:
                follow_ups = json.loads(follow_ups_raw) if isinstance(follow_ups_raw, str) else follow_ups_raw
            except (json.JSONDecodeError, TypeError):
                follow_ups = None

        return {
            "whisper_id": get("whisper_id") or "",
            "shown_count": get("shown_count") or 0,
            "action_taken": get("action_taken"),
            "first_shown": get("first_shown"),
            "last_shown": get("last_shown"),
            "insight": get("insight") or "",
            "entity": get("entity") or "",
            "type": get("type") or "",
            "embedding": get("embedding"),
            # Loop 1 iteration: Delivery Intelligence + Learning Ledger fields
            "recipient": get("recipient"),
            "reason_recipient_chosen": get("reason_recipient_chosen"),
            "timing_reason": get("timing_reason"),
            "depth": get("depth"),
            "materially_changed_since_last_shown": get("materially_changed_since_last_shown"),
            "decision_influenced": get("decision_influenced"),
            "follow_up_questions": follow_ups,
            "outcome": get("outcome"),
            "learning_entry": get("learning_entry"),
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
