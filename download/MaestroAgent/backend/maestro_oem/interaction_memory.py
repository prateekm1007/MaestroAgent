"""Priority 3: Interaction Memory — the full lifecycle of how an exec
engages with a Whisper.

CEO directive (2026-07-04):
> Remember shown/opened/dismissed/deferred/acted/delegated/contradicted/
> resolved — not just whisper content.

The current WhisperHistoryStore tracks a SINGLE `action_taken` field that
gets overwritten. There's no event log — no way to know the sequence:
"shown → opened → deferred → shown again → acted". This module adds an
append-only event log.

The 8 event types:
  1. SHOWN        — Whisper was surfaced to the exec
  2. OPENED       — exec expanded/opened the Whisper (engagement signal)
  3. DISMISSED    — exec explicitly dismissed it (different from "never opened")
  4. DEFERRED     — exec snoozed/deferred it (intent to revisit)
  5. ACTED        — exec took action based on the Whisper
  6. DELEGATED    — exec delegated the action to someone else
  7. CONTRADICTED — exec disagreed with the Whisper (negative feedback)
  8. RESOLVED     — the situation resolved (commitment kept, objection withdrawn, etc.)

This enriches the AttributionAnalyzer (Priority 1) because:
  - "shown but never opened" ≠ "opened but dismissed" ≠ "opened, deferred, then acted"
  - The current exec_action="ignored" is too coarse — it conflates 3 different
    engagement patterns that have different attribution implications
  - The governed adaptation loop can form better hypotheses when it knows
    the full interaction history

Wiring (P11):
  - whisper.py records SHOWN events when a Whisper is delivered
  - governed_adaptation.py's AttributionAnalyzer reads interaction_history
    from the outcome dict to form richer hypotheses
  - InteractionMemory is ADDITIVE — it doesn't replace WhisperHistoryStore,
    it enriches it (backward-compatible)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class InteractionEventType(str, Enum):
    """The 8 interaction event types — the full lifecycle of exec engagement."""

    SHOWN = "shown"              # Whisper was surfaced to the exec
    OPENED = "opened"            # exec expanded/opened the Whisper
    DISMISSED = "dismissed"      # exec explicitly dismissed it
    DEFERRED = "deferred"        # exec snoozed/deferred it
    ACTED = "acted"              # exec took action based on the Whisper
    DELEGATED = "delegated"      # exec delegated the action to someone else
    CONTRADICTED = "contradicted"  # exec disagreed with the Whisper
    RESOLVED = "resolved"        # the situation resolved


_SCHEMA = """
CREATE TABLE IF NOT EXISTS interaction_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    whisper_id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_interaction_whisper ON interaction_events(whisper_id, org_id);
CREATE INDEX IF NOT EXISTS idx_interaction_timestamp ON interaction_events(timestamp);
"""


class InteractionMemory:
    """SQLite-backed append-only event log for Whisper interactions.

    Every interaction (shown, opened, dismissed, deferred, acted, delegated,
    contradicted, resolved) is recorded as a separate event with a timestamp.
    The full sequence is preserved — events are NEVER overwritten.

    Usage:
        mem = InteractionMemory("interactions.db")
        mem.record("wspr-1", InteractionEventType.SHOWN, org_id="default")
        mem.record("wspr-1", InteractionEventType.OPENED, org_id="default")
        history = mem.get_history("wspr-1", org_id="default")
        summary = mem.get_interaction_summary("wspr-1", org_id="default")
    """

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path or ":memory:"
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            from maestro_db import sqlite_compat as sqlite3_compat
            self._conn = sqlite3_compat.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3_compat.Row
        except Exception:
            self._conn = sqlite3.connect(self._db_path, isolation_level=None, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        try:
            cursor = self._conn.cursor()
            for stmt in _SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    cursor.execute(stmt)
        except Exception as e:
            logger.warning("InteractionMemory schema init: %s", e)

    def record(
        self,
        whisper_id: str,
        event_type: InteractionEventType,
        org_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record an interaction event (append-only).

        Args:
            whisper_id: The Whisper ID
            event_type: One of InteractionEventType
            org_id: Organization ID
            metadata: Optional dict with extra context (e.g., who delegated to)

        Returns:
            The event_id of the recorded event.
        """
        event_id = f"evt-{uuid4().hex[:8]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(metadata or {})

        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                """INSERT INTO interaction_events
                   (event_id, whisper_id, org_id, event_type, timestamp, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (event_id, whisper_id, org_id, event_type.value, timestamp, metadata_json),
            )
        return event_id

    def get_history(
        self,
        whisper_id: str,
        org_id: str = "default",
    ) -> list[dict[str, Any]]:
        """Get the full interaction history for a Whisper (chronological order).

        Returns a list of dicts with: event_id, whisper_id, org_id,
        event_type, timestamp, metadata.
        """
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                """SELECT * FROM interaction_events
                   WHERE whisper_id = ? AND org_id = ?
                   ORDER BY id ASC""",
                (whisper_id, org_id),
            )
            rows = cur.fetchall()
            result = []
            for row in rows:
                if isinstance(row, dict):
                    d = row
                else:
                    d = {k: row[k] for k in row.keys()}
                d["metadata"] = json.loads(d.get("metadata", "{}"))
                result.append(d)
            return result

    def get_interaction_summary(
        self,
        whisper_id: str,
        org_id: str = "default",
    ) -> dict[str, Any]:
        """Get a structured summary of the interaction history.

        Returns a dict with:
          - final_state: the last event type (e.g., "RESOLVED", "ACTED", "DISMISSED")
          - shown_count: how many times the Whisper was shown
          - opened_count: how many times it was opened
          - deferred_count: how many times it was deferred
          - acted: bool — did the exec act on it?
          - delegated: bool — did the exec delegate?
          - contradicted: bool — did the exec contradict it?
          - resolved: bool — was the situation resolved?
          - total_events: total number of interaction events
        """
        history = self.get_history(whisper_id, org_id)
        if not history:
            return {
                "final_state": "NONE",
                "shown_count": 0,
                "opened_count": 0,
                "deferred_count": 0,
                "acted": False,
                "delegated": False,
                "contradicted": False,
                "resolved": False,
                "total_events": 0,
            }

        event_types = [h["event_type"] for h in history]
        return {
            "final_state": event_types[-1].upper(),
            "shown_count": event_types.count(InteractionEventType.SHOWN.value),
            "opened_count": event_types.count(InteractionEventType.OPENED.value),
            "deferred_count": event_types.count(InteractionEventType.DEFERRED.value),
            "acted": InteractionEventType.ACTED.value in event_types,
            "delegated": InteractionEventType.DELEGATED.value in event_types,
            "contradicted": InteractionEventType.CONTRADICTED.value in event_types,
            "resolved": InteractionEventType.RESOLVED.value in event_types,
            "total_events": len(history),
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ─── Module-level singleton (lazy) ──────────────────────────────────────────

_default_memory: InteractionMemory | None = None


def get_default_memory() -> InteractionMemory:
    """Get the default InteractionMemory singleton.

    In production, this is initialized with a SQLite path from
    MAESTRO_INTERACTION_DB. In tests, it can be replaced via
    set_default_memory().
    """
    global _default_memory
    if _default_memory is None:
        import os
        db_path = os.environ.get("MAESTRO_INTERACTION_DB", "interactions.db")
        _default_memory = InteractionMemory(db_path)
    return _default_memory


def set_default_memory(memory: InteractionMemory) -> None:
    """Set the default InteractionMemory (for testing)."""
    global _default_memory
    _default_memory = memory
