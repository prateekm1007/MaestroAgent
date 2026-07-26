"""BaseConnector — the Onyx Load/Poll/Slim pattern, unified with the Signal model.

Every adapter (Gmail, Slack, GitHub, Outlook, etc.) subclasses this and
implements load_from_state, poll_source, and slim_check. The Signal model
ensures all sources produce the same output format.

SyncCursor (from PipesHub) provides per-(user, source) incremental sync
state that persists in the database — no full re-pulls on reconnect.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from maestro_personal_shell.connector_framework import Signal

logger = logging.getLogger(__name__)


@dataclass
class SyncCursor:
    """Per-(user, source) sync state — the PipesHub sync-point pattern.

    Persisted in the database so reconnects resume from the high-water mark
    instead of re-pulling everything. Each adapter defines its own cursor
    format (Gmail historyId, Slack latest_ts per channel, GH since, etc.)
    """
    user_email: str
    source: str
    cursor_data: dict[str, Any] = field(default_factory=dict)
    last_sync: datetime | None = None
    total_synced: int = 0

    def is_first_sync(self) -> bool:
        return self.last_sync is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_email": self.user_email,
            "source": self.source,
            "cursor_data": self.cursor_data,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "total_synced": self.total_synced,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SyncCursor":
        last_sync = None
        if d.get("last_sync"):
            try:
                last_sync = datetime.fromisoformat(d["last_sync"])
            except (ValueError, TypeError):
                pass
        return cls(
            user_email=d.get("user_email", ""),
            source=d.get("source", ""),
            cursor_data=d.get("cursor_data", {}),
            last_sync=last_sync,
            total_synced=d.get("total_synced", 0),
        )


class BaseConnector(ABC):
    """Base class for all Maestro connectors.

    Subclasses implement the 3 Onyx flows (load, poll, slim) plus
    credential management. All return Signal objects — the unified model.

    The connector_name is used as the source field in Signals and as the
    key in the SourceAdapter registry.
    """

    connector_name: str = "base"

    @abstractmethod
    def load_from_state(self, user_email: str) -> list[Signal]:
        """Bulk load all signals (initial sync / first connection).

        Called on first connection. Returns a list of Signal objects.
        """
        pass

    @abstractmethod
    def poll_source(self, user_email: str, cursor: SyncCursor) -> tuple[list[Signal], SyncCursor]:
        """Incremental sync — fetch only changes since the cursor.

        Args:
            user_email: The user's email for per-user sync
            cursor: The persisted sync state from the last successful sync

        Returns:
            (new_signals, updated_cursor) — the cursor must be persisted
            by the caller after successful ingestion.
        """
        pass

    @abstractmethod
    def slim_check(self, user_email: str) -> list[str]:
        """Return IDs of all signals that still exist (for pruning).

        Called periodically to identify deleted signals. The caller
        compares against stored signals and removes stale ones.
        """
        pass

    @abstractmethod
    def load_credentials(self, credentials: dict[str, Any]) -> None:
        """Load OAuth tokens or API keys."""
        pass

    def test_connection(self) -> bool:
        """Test if credentials are valid and the source is reachable."""
        try:
            cursor = SyncCursor(user_email="test", source=self.connector_name)
            self.poll_source("test", cursor)
            return True
        except Exception:
            return False

    def get_cursor(self, user_email: str) -> SyncCursor:
        """Get or create a sync cursor for this connector + user."""
        return SyncCursor(
            user_email=user_email,
            source=self.connector_name,
        )
