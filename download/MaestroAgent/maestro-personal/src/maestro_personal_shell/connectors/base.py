"""Base connector architecture — adapted from Onyx's Load/Poll/Slim pattern.

Onyx connectors come in 3 flows:
  - Load Connector: bulk indexes documents (initial sync)
  - Poll Connector: incrementally updates based on time range
  - Slim Connector: lightweight check for document existence (pruning)

Each Maestro connector implements all three via a single class, plus
load_credentials() for OAuth token management.

SyncPoint (from PipesHub) stores the last sync state for delta syncs.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SyncPoint:
    """Checkpoint for incremental sync — adapted from PipesHub.

    Stores the last sync state so poll_source() can fetch only changes
    since the last successful sync, not the full corpus every time.

    Attributes:
        connector_name: e.g. "gmail", "calendar"
        user_id: the user's email/ID for per-user sync state
        last_sync: when the last successful sync completed
        delta_link: provider-specific cursor (e.g. Gmail historyId, Graph delta link)
        total_synced: running count of signals synced
    """

    connector_name: str
    user_id: str
    last_sync: datetime | None = None
    delta_link: str | None = None
    total_synced: int = 0

    def is_first_sync(self) -> bool:
        """True if no sync has ever completed."""
        return self.last_sync is None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "connector_name": self.connector_name,
            "user_id": self.user_id,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "delta_link": self.delta_link,
            "total_synced": self.total_synced,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncPoint":
        """Deserialize from storage."""
        last_sync = None
        if data.get("last_sync"):
            try:
                last_sync = datetime.fromisoformat(data["last_sync"])
            except (ValueError, TypeError):
                pass
        return cls(
            connector_name=data.get("connector_name", ""),
            user_id=data.get("user_id", ""),
            last_sync=last_sync,
            delta_link=data.get("delta_link"),
            total_synced=data.get("total_synced", 0),
        )


class BaseConnector(ABC):
    """Base class for all Maestro connectors.

    Subclasses implement the 3 Onyx flows (load, poll, slim) plus
    credential management. The test_connection() method provides
    a health check for the connector.

    Usage:
        connector = GmailConnector()
        connector.load_credentials({"access_token": "...", "refresh_token": "..."})
        if connector.test_connection():
            signals = connector.load_from_state()  # initial sync
            # Later:
            signals = connector.poll_source(last_sync, now)  # incremental
    """

    connector_name: str = "base"

    @abstractmethod
    def load_from_state(self) -> list[dict[str, Any]]:
        """Bulk load all signals (initial sync).

        Called on first connection or when the user requests a full re-sync.
        Returns a list of signal dicts ready for save_signal_to_db().

        Returns:
            List of signals, each with keys: signal_id, entity, text,
            signal_type, timestamp, metadata
        """
        pass

    @abstractmethod
    def poll_source(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Incremental sync — only fetch changes since last poll.

        Called on a schedule (e.g. every 5 minutes) to fetch new/modified
        signals since the last sync. Uses the SyncPoint's delta_link when
        available for provider-specific delta sync.

        Args:
            start: fetch signals modified after this time
            end: fetch signals modified before this time

        Returns:
            List of new/modified signals
        """
        pass

    @abstractmethod
    def slim_check(self) -> list[str]:
        """Return IDs of all signals that still exist (for pruning).

        Called periodically to identify signals that have been deleted
        from the source. The caller compares this list against stored
        signals and removes any that no longer exist.

        Returns:
            List of source-specific IDs (e.g. Gmail message IDs)
        """
        pass

    @abstractmethod
    def load_credentials(self, credentials: dict[str, Any]) -> None:
        """Load OAuth tokens or API keys.

        Called before any API request. Subclasses should store credentials
        and implement token refresh logic (Onyx pattern: check expiry
        before each API call).

        Args:
            credentials: dict with keys like access_token, refresh_token,
                         client_id, client_secret
        """
        pass

    def test_connection(self) -> bool:
        """Test if credentials are valid and the source is reachable.

        Default implementation: try a small poll and return True if it
        succeeds. Subclasses can override with a lighter-weight check
        (e.g. a profile API call).

        Returns:
            True if the connection works, False otherwise
        """
        try:
            now = datetime.now(timezone.utc)
            self.poll_source(now, now)
            return True
        except Exception:
            return False

    def get_sync_point(self, user_id: str) -> SyncPoint:
        """Get or create the sync point for this connector + user.

        Subclasses should override this to persist/load the sync point
        from the database. The default implementation returns a fresh
        SyncPoint (first sync).

        Returns:
            SyncPoint for this connector + user
        """
        return SyncPoint(
            connector_name=self.connector_name,
            user_id=user_id,
        )
