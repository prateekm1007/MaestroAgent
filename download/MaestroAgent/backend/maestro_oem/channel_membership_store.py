"""CRITICAL-01 Phase 2-3 — Channel membership store + provider client interface.

Phase 2: SQLite-backed ChannelMembershipStore for caching membership
synced from provider APIs (Slack, GitHub, Jira, Confluence).

Phase 3: ProviderClientBase interface + MockProviderClient for testing.
ACLResolver is updated to accept the membership store + provider clients.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Protocol

from maestro_db import sqlite_compat as sqlite3
from maestro_db.sqlite_compat import safe_pragma

logger = logging.getLogger(__name__)


class ProviderClient(Protocol):
    """Interface for provider clients that can check channel/team membership."""

    def check_membership(self, scope_id: str, user_email: str) -> bool:
        """Check if user_email is a member of scope_id (channel, team, project, space)."""
        ...


class MockProviderClient:
    """Mock provider client for testing and dev mode.

    Returns membership based on a pre-populated dict. In production,
    each provider (Slack, GitHub, etc.) implements ProviderClient with
    real API calls.
    """

    def __init__(self, membership_map: dict[str, set[str]] | None = None) -> None:
        # membership_map: {"C123456": {"alice@acme.com", "bob@acme.com"}, ...}
        self._membership = membership_map or {}

    def check_membership(self, scope_id: str, user_email: str) -> bool:
        members = self._membership.get(scope_id, set())
        return user_email in members

    def add_member(self, scope_id: str, user_email: str) -> None:
        if scope_id not in self._membership:
            self._membership[scope_id] = set()
        self._membership[scope_id].add(user_email)

    def remove_member(self, scope_id: str, user_email: str) -> None:
        if scope_id in self._membership:
            self._membership[scope_id].discard(user_email)


class ChannelMembershipStore:
    """SQLite-backed membership cache for channel/team/project/space ACLs.

    Synced periodically from provider APIs. When ACLResolver checks
    membership, it reads from this cache first (fast), then falls back
    to live API call (slow) if cache misses.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS channel_membership (
        provider TEXT NOT NULL,
        scope_id TEXT NOT NULL,
        user_email TEXT NOT NULL,
        is_member INTEGER NOT NULL,
        synced_at TEXT NOT NULL,
        PRIMARY KEY (provider, scope_id, user_email)
    );
    CREATE INDEX IF NOT EXISTS idx_membership_lookup
        ON channel_membership(provider, scope_id, user_email);
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._SCHEMA)
        safe_pragma(self._conn, self.db_path, "PRAGMA journal_mode=WAL")

    def get_membership(self, provider: str, scope_id: str, user_email: str) -> bool | None:
        """Check cached membership. Returns True/False if cached, None if not in cache."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT is_member FROM channel_membership WHERE provider = ? AND scope_id = ? AND user_email = ?",
                (provider, scope_id, user_email),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return bool(row["is_member"])

    def set_membership(self, provider: str, scope_id: str, user_email: str, is_member: bool) -> None:
        """Cache a membership result."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO channel_membership (provider, scope_id, user_email, is_member, synced_at) VALUES (?, ?, ?, ?, ?)",
                (provider, scope_id, user_email, 1 if is_member else 0, now),
            )

    def sync_members(self, provider: str, scope_id: str, members: set[str]) -> None:
        """Bulk-sync membership for a scope. Removes stale entries."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            # Clear existing entries for this scope
            self._conn.execute(
                "DELETE FROM channel_membership WHERE provider = ? AND scope_id = ?",
                (provider, scope_id),
            )
            # Insert current members
            for email in members:
                self._conn.execute(
                    "INSERT INTO channel_membership (provider, scope_id, user_email, is_member, synced_at) VALUES (?, ?, ?, ?, ?)",
                    (provider, scope_id, email, 1, now),
                )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ─── Module-level singleton ─────────────────────────────────────────────

_membership_store: ChannelMembershipStore | None = None


def get_membership_store() -> ChannelMembershipStore:
    """Get the singleton ChannelMembershipStore."""
    global _membership_store
    if _membership_store is None:
        db_path = os.environ.get("MAESTRO_MEMBERSHIP_DB", ":memory:")
        _membership_store = ChannelMembershipStore(db_path)
    return _membership_store


def reset_membership_store() -> None:
    """Reset singleton (for testing)."""
    global _membership_store
    if _membership_store:
        _membership_store.close()
    _membership_store = None
