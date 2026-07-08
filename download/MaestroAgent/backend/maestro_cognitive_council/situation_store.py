"""
Maestro Cognitive Council — Persistent Situation Store.

Per the audit: "No persistent Situation store — SituationEngine rebuilds
from signals per request. Even the new API re-derives rather than evolves
a situation over time."

This module provides SQLite-backed persistence for LivingSituations.
The SituationEngine can now:
  1. Load existing situations from the store on startup
  2. Save new situations and state transitions
  3. Update situations when new signals arrive (delta-driven, not rebuild)
  4. Evolve situations across requests (persistent identity)

Usage:
    store = SituationStore(db_path="situations.db")
    engine = SituationEngine(oem_state=oem, situation_store=store)
    # Now situations persist across requests
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class SituationStore:
    """SQLite-backed persistent store for LivingSituations.

    Stores situations keyed by a stable identity (entity + org_id hash),
    not by the per-request situation_id. This means the same entity's
    situation persists and evolves across requests.

    Schema:
      situations (situation_key, situation_id, entity, org_id, state,
                  epistemic_state, data_json, created_at, updated_at)
      transitions (id, situation_key, from_state, to_state, reason,
                   timestamp, data_json)
    """

    def __init__(self, db_path: str = "situations.db"):
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite schema."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS situations (
                    situation_key TEXT PRIMARY KEY,
                    situation_id TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    org_id TEXT NOT NULL DEFAULT 'default',
                    state TEXT NOT NULL DEFAULT 'detected',
                    epistemic_state TEXT NOT NULL DEFAULT 'unknown',
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_situations_entity ON situations(entity);
                CREATE INDEX IF NOT EXISTS idx_situations_org ON situations(org_id);

                CREATE TABLE IF NOT EXISTS transitions (
                    id TEXT PRIMARY KEY,
                    situation_key TEXT NOT NULL,
                    dimension TEXT,
                    from_state TEXT,
                    to_state TEXT,
                    reason TEXT,
                    timestamp TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (situation_key) REFERENCES situations(situation_key)
                );
                CREATE INDEX IF NOT EXISTS idx_transitions_key ON transitions(situation_key);
            """)
            conn.commit()
            conn.close()

    @staticmethod
    def _situation_key(entity: str, org_id: str = "default") -> str:
        """Stable key for a situation (entity + org_id)."""
        return f"{org_id}:{entity.lower()}"

    def save_situation(self, situation: Any) -> None:
        """Save or update a LivingSituation in the store."""
        import hashlib

        key = self._situation_key(situation.entity, situation.org_id)
        data = situation.to_dict()
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                INSERT OR REPLACE INTO situations
                    (situation_key, situation_id, entity, org_id, state,
                     epistemic_state, data_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                key,
                situation.situation_id,
                situation.entity,
                situation.org_id,
                situation.state.value if hasattr(situation.state, 'value') else str(situation.state),
                situation.epistemic_state.value if hasattr(situation.epistemic_state, 'value') else str(situation.epistemic_state),
                json.dumps(data),
                situation.opened_at.isoformat() if hasattr(situation, 'opened_at') else now,
                now,
            ))
            conn.commit()
            conn.close()

    def load_situation(self, entity: str, org_id: str = "default") -> Optional[dict]:
        """Load a situation from the store by entity + org_id."""
        key = self._situation_key(entity, org_id)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT data_json FROM situations WHERE situation_key = ?",
                (key,)
            ).fetchone()
            conn.close()
            if row:
                return json.loads(row[0])
            return None

    def load_all_situations(self, org_id: str = "default") -> list[dict]:
        """Load all situations for an org."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT data_json FROM situations WHERE org_id = ? ORDER BY updated_at DESC",
                (org_id,)
            ).fetchall()
            conn.close()
            return [json.loads(r[0]) for r in rows]

    def save_transition(self, entity: str, org_id: str, transition: Any) -> None:
        """Save a state transition to the store."""
        key = self._situation_key(entity, org_id)
        transition_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        transition_data = transition.to_dict() if hasattr(transition, 'to_dict') else {}

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                INSERT INTO transitions
                    (id, situation_key, dimension, from_state, to_state, reason, timestamp, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transition_id,
                key,
                transition_data.get("dimension", ""),
                transition_data.get("from_state", transition_data.get("previous_state", "")),
                transition_data.get("to_state", transition_data.get("new_state", "")),
                transition_data.get("reason", ""),
                transition_data.get("timestamp", now),
                json.dumps(transition_data),
            ))
            conn.commit()
            conn.close()

    def load_transitions(self, entity: str, org_id: str = "default") -> list[dict]:
        """Load all transitions for a situation."""
        key = self._situation_key(entity, org_id)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT data_json FROM transitions WHERE situation_key = ? ORDER BY timestamp ASC",
                (key,)
            ).fetchall()
            conn.close()
            return [json.loads(r[0]) for r in rows]

    def delete_situation(self, entity: str, org_id: str = "default") -> bool:
        """Delete a situation from the store."""
        key = self._situation_key(entity, org_id)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM situations WHERE situation_key = ?", (key,))
            conn.execute("DELETE FROM transitions WHERE situation_key = ?", (key,))
            conn.commit()
            conn.close()
            return True

    def count(self, org_id: str = "default") -> int:
        """Count situations for an org."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT COUNT(*) FROM situations WHERE org_id = ?", (org_id,)
            ).fetchone()
            conn.close()
            return row[0] if row else 0
