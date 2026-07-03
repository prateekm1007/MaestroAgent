"""Loop 2 — MeetingStore: in-memory persistence for meetings.

Stores meetings by meeting_id. In-memory for this iteration — SQLite
migration deferred (trigger: first production deployment requiring
meetings to survive a server restart).

The store supports:
  - record(meeting): upsert a meeting
  - get(meeting_id): retrieve a meeting
  - get_all(): retrieve all meetings
  - get_by_entity(entity): retrieve all meetings for an entity
  - get_by_status(status): retrieve all meetings in a lifecycle state
"""

from __future__ import annotations

import threading
from typing import Any

from maestro_oem.meeting import Meeting, MeetingStatus


class MeetingStore:
    """In-memory store for Meeting objects.

    Thread-safe via a single lock. Persists for the lifetime of the
    process. For production, replace with a SQLite-backed store (same
    interface) — the MeetingIntelligenceLoop does not change.
    """

    def __init__(self) -> None:
        self._meetings: dict[str, Meeting] = {}
        self._lock = threading.Lock()

    def record(self, meeting: Meeting) -> None:
        """Upsert a meeting (by meeting_id)."""
        with self._lock:
            self._meetings[meeting.meeting_id] = meeting

    def get(self, meeting_id: str) -> Meeting | None:
        """Retrieve a meeting by ID. Returns None if not found."""
        with self._lock:
            return self._meetings.get(meeting_id)

    def get_all(self) -> list[Meeting]:
        """Retrieve all meetings."""
        with self._lock:
            return list(self._meetings.values())

    def get_by_entity(self, entity: str) -> list[Meeting]:
        """Retrieve all meetings for a specific entity."""
        with self._lock:
            return [m for m in self._meetings.values() if m.entity == entity]

    def get_by_status(self, status: MeetingStatus) -> list[Meeting]:
        """Retrieve all meetings in a specific lifecycle state."""
        with self._lock:
            return [m for m in self._meetings.values() if m.status == status]

    def clear(self) -> None:
        """Clear all meetings (for testing)."""
        with self._lock:
            self._meetings.clear()
