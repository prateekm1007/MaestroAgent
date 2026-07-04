"""Loop 2 — MeetingStore: SQLite-backed persistence for meetings.

C1 fix (ADVERSARIAL-AUDIT-24PHASE): All cognitive state was in-memory —
lost on restart. This store is now SQLite-backed, following the same
pattern as WhisperHistoryStore.

The store supports:
  - record(meeting): upsert a meeting
  - get(meeting_id): retrieve a meeting
  - get_all(): retrieve all meetings
  - get_by_entity(entity): retrieve all meetings for an entity
  - get_by_status(status): retrieve all meetings in a lifecycle state
  - close(): close the SQLite connection

Meetings are serialized as JSON in a single TEXT column. This is simpler
than normalizing the schema and sufficient for the current scale.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maestro_oem.meeting import Meeting, MeetingStatus

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    meeting_id TEXT PRIMARY KEY,
    entity TEXT NOT NULL,
    status TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meetings_entity ON meetings(entity);
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(status);
"""


class MeetingStore:
    """SQLite-backed store for Meeting objects.

    Usage:
        store = MeetingStore("meetings.db")
        store.record(meeting)
        recovered = store.get(meeting_id)
        store.close()
    """

    def __init__(self, db_path: str | Path = "") -> None:
        self._db_path = str(db_path) if db_path else ":memory:"
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._in_memory: dict[str, Meeting] = {}  # fallback for no db_path
        self._use_sqlite = bool(db_path)
        if self._use_sqlite:
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
            logger.warning("MeetingStore schema init: %s", e)

    def record(self, meeting: Meeting) -> None:
        if not self._use_sqlite:
            with self._lock:
                self._in_memory[meeting.meeting_id] = meeting
            return
        with self._lock:
            assert self._conn is not None
            data = self._serialize(meeting)
            self._conn.execute(
                """INSERT OR REPLACE INTO meetings (meeting_id, entity, status, data)
                   VALUES (?, ?, ?, ?)""",
                (meeting.meeting_id, meeting.entity, meeting.status.name, data),
            )

    def get(self, meeting_id: str) -> Meeting | None:
        if not self._use_sqlite:
            with self._lock:
                return self._in_memory.get(meeting_id)
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM meetings WHERE meeting_id = ?", (meeting_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._deserialize(row["data"] if isinstance(row, dict) else row[0])

    def get_all(self) -> list[Meeting]:
        if not self._use_sqlite:
            with self._lock:
                return list(self._in_memory.values())
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM meetings")
            rows = cur.fetchall()
            return [self._deserialize(r["data"] if isinstance(r, dict) else r[0]) for r in rows]

    def get_by_entity(self, entity: str) -> list[Meeting]:
        if not self._use_sqlite:
            with self._lock:
                return [m for m in self._in_memory.values() if m.entity == entity]
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM meetings WHERE entity = ?", (entity,))
            rows = cur.fetchall()
            return [self._deserialize(r["data"] if isinstance(r, dict) else r[0]) for r in rows]

    def get_by_status(self, status: MeetingStatus) -> list[Meeting]:
        if not self._use_sqlite:
            with self._lock:
                return [m for m in self._in_memory.values() if m.status == status]
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM meetings WHERE status = ?", (status.name,))
            rows = cur.fetchall()
            return [self._deserialize(r["data"] if isinstance(r, dict) else r[0]) for r in rows]

    def clear(self) -> None:
        if not self._use_sqlite:
            with self._lock:
                self._in_memory.clear()
            return
        with self._lock:
            assert self._conn is not None
            self._conn.execute("DELETE FROM meetings")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _serialize(self, meeting: Meeting) -> str:
        d = meeting.to_dict()
        return json.dumps(d, default=str)

    def _deserialize(self, data_str: str) -> Meeting:
        d = json.loads(data_str)
        meeting = Meeting(
            title=d.get("title", ""),
            entity=d.get("entity", ""),
            attendees=d.get("attendees", []),
            start=datetime.fromisoformat(d["start"]) if d.get("start") else datetime.now(timezone.utc),
            end=datetime.fromisoformat(d["end"]) if d.get("end") else datetime.now(timezone.utc),
            meeting_id=d.get("meeting_id", ""),
        )
        meeting.status = MeetingStatus[d.get("status", "SCHEDULED")]
        meeting.topics_discussed = d.get("topics_discussed", [])
        meeting.commitments_made = d.get("commitments_made", [])
        meeting.outcome = d.get("outcome")
        meeting.learning_entry = d.get("learning_entry")
        # situation is complex — skip for now (can be re-assembled from signals)
        return meeting
