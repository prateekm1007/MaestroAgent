"""
V8 Personal Mode — Incognito Session (Guideline P6).

A session mode where no data is persisted. The user can have a
conversation with Maestro about a sensitive topic and nothing is
stored — no signals, no learning objects, no attention signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IncognitoSession:
    """An incognito session — no data is persisted.

    When active, all personal data operations are in-memory only.
    When the session ends, all data is discarded. No signals, no
    learning objects, no attention signals are stored.
    """
    session_id: str
    user_id: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: str | None = None
    _ephemeral_data: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    def add_ephemeral(self, key: str, value: Any) -> None:
        """Add data to the ephemeral store (lost when session ends)."""
        self._ephemeral_data.append({"key": key, "value": value, "timestamp": datetime.now(timezone.utc).isoformat()})

    def get_ephemeral(self, key: str) -> list[Any]:
        """Get ephemeral data by key."""
        return [d["value"] for d in self._ephemeral_data if d["key"] == key]

    def end(self) -> None:
        """End the session — all ephemeral data is discarded."""
        self.ended_at = datetime.now(timezone.utc).isoformat()
        count = len(self._ephemeral_data)
        self._ephemeral_data.clear()
        logger.info("Incognito session ended: %s (%d ephemeral items discarded)", self.session_id, count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "is_active": self.is_active,
            "ephemeral_count": len(self._ephemeral_data),
        }


class IncognitoManager:
    """Manages incognito sessions.

    Only one incognito session per user at a time. When a session is
    active, the PersonalDataStore checks IncognitoManager before
    persisting anything — if incognito is active, data goes to the
    ephemeral store instead of the persistent store.
    """

    _sessions: dict[str, IncognitoSession] = {}  # user_id → active session

    @classmethod
    def start_session(cls, user_id: str) -> IncognitoSession:
        """Start an incognito session for a user."""
        from uuid import uuid4
        # End any existing session
        if user_id in cls._sessions and cls._sessions[user_id].is_active:
            cls._sessions[user_id].end()
        session = IncognitoSession(
            session_id=str(uuid4()),
            user_id=user_id,
        )
        cls._sessions[user_id] = session
        logger.info("Incognito session started: user=%s session=%s", user_id, session.session_id)
        return session

    @classmethod
    def get_session(cls, user_id: str) -> IncognitoSession | None:
        """Get the active incognito session for a user, if any."""
        session = cls._sessions.get(user_id)
        if session and session.is_active:
            return session
        return None

    @classmethod
    def is_incognito(cls, user_id: str) -> bool:
        """Check if a user is currently in incognito mode."""
        return cls.get_session(user_id) is not None

    @classmethod
    def end_session(cls, user_id: str) -> bool:
        """End the incognito session for a user. Returns True if a session was ended."""
        session = cls._sessions.get(user_id)
        if session and session.is_active:
            session.end()
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        """Clear all sessions (for testing)."""
        cls._sessions = {}
