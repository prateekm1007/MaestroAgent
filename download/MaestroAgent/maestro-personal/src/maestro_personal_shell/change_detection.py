"""Change detection with baseline (P78).

Tracks the user's last_seen_at timestamp and computes actual deltas —
new, modified, resolved, and contradicted signals since the last read.

Root cause (P10): /api/what-changed was listing current commitments
instead of computing actual changes. The user can't tell "what's new"
from "what exists" without a baseline.

P78: read twice, second read shows 0 changes (because last_seen_at updated).
P22: reads from the canonical ledger (ALL events), no mocks.
P85: never raises — returns empty deltas on any error.

Authored by: CTO (direct — follows the same pattern as confidence_system.py)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path

logger = logging.getLogger(__name__)

# Table for tracking per-user last_seen_at timestamps
# Created lazily on first call to ensure it exists
_LAST_SEEN_DDL = """
CREATE TABLE IF NOT EXISTS user_last_seen (
    user_email TEXT PRIMARY KEY,
    last_seen_at TEXT NOT NULL,
    last_seen_method TEXT DEFAULT 'what_changed'
)
"""


def _ensure_last_seen_table(db_path: str | None = None) -> None:
    """Create the user_last_seen table if it doesn't exist."""
    try:
        conn = get_db_conn(db_path or default_sqlite_path())
        conn.execute(_LAST_SEEN_DDL)
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("change_detection: failed to create user_last_seen table: %s", exc)


def get_last_seen(user_email: str, db_path: str | None = None) -> str | None:
    """Get the user's last_seen_at timestamp, or None if never seen.

    P85: never raises — returns None on any error.
    """
    try:
        _ensure_last_seen_table(db_path)
        conn = get_db_conn(db_path or default_sqlite_path())
        row = conn.execute(
            "SELECT last_seen_at FROM user_last_seen WHERE user_email = ?",
            (user_email,),
        ).fetchone()
        conn.close()
        if row:
            return row[0] if isinstance(row, (tuple, list)) else row.get("last_seen_at")
        return None
    except Exception as exc:
        logger.warning("change_detection: get_last_seen failed: %s", exc)
        return None


def update_last_seen(user_email: str, db_path: str | None = None) -> str:
    """Update the user's last_seen_at to now. Returns the new timestamp.

    P85: never raises — returns now() on any error.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        _ensure_last_seen_table(db_path)
        conn = get_db_conn(db_path or default_sqlite_path())
        conn.execute(
            "INSERT INTO user_last_seen (user_email, last_seen_at, last_seen_method) "
            "VALUES (?, ?, 'what_changed') "
            "ON CONFLICT(user_email) DO UPDATE SET last_seen_at = ?, last_seen_method = 'what_changed'",
            (user_email, now, now),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("change_detection: update_last_seen failed: %s", exc)
    return now


def compute_changes(user_email: str, db_path: str | None = None) -> dict:
    """Compute what changed since the user's last_seen_at (P78).

    Returns:
      {
        "last_seen_at": str | None,   # the previous baseline (None = first read)
        "current_at": str,            # now
        "new": list[dict],            # events created since last_seen_at
        "modified": list[dict],       # commitments with state transitions since last_seen_at
        "resolved": list[dict],       # commitments transitioned to completed
        "contradicted": list[dict],   # commitments transitioned to cancelled
        "total_changes": int,
      }

    P78: read twice, second read shows 0 changes (because last_seen_at updated).
    P85: never raises — returns empty deltas on any error.
    P22: reads from the canonical ledger directly, no mocks.
    """
    try:
        from maestro_personal_shell.canonical_ledger import _EVENT_COLUMNS

        _ensure_last_seen_table(db_path)
        last_seen = get_last_seen(user_email, db_path)
        now = datetime.now(timezone.utc).isoformat()

        conn = get_db_conn(db_path or default_sqlite_path())

        # Get ALL events for this user
        rows = conn.execute(
            f"SELECT {_EVENT_COLUMNS} FROM commitment_events "
            "WHERE user_email = ? ORDER BY timestamp ASC",
            (user_email,),
        ).fetchall()
        conn.close()

        # Filter events created since last_seen
        new_events = []
        modified_events = []
        resolved_events = []
        contradicted_events = []

        for row in rows:
            # Extract fields (column order from _EVENT_COLUMNS)
            event_id = row[0]
            commitment_id = row[1]
            event_type = row[2]
            actor = row[3]
            entity = row[4]
            text = row[5]
            confidence = row[7]
            timestamp = row[10]

            event_dict = {
                "event_id": event_id,
                "commitment_id": commitment_id,
                "event_type": event_type,
                "actor": actor,
                "entity": entity,
                "text": text,
                "confidence": confidence,
                "timestamp": timestamp,
            }

            # If last_seen is None (first read), everything is "new"
            if last_seen is None:
                new_events.append(event_dict)
            elif timestamp > last_seen:
                # Event created since last_seen
                new_events.append(event_dict)

                # Categorize by event_type
                if event_type == "completion":
                    resolved_events.append(event_dict)
                elif event_type == "cancellation":
                    contradicted_events.append(event_dict)
                elif event_type in ("commitment", "tentative", "request", "question",
                                    "quotation", "joke"):
                    # These are "modified" — new events on existing or new commitments
                    modified_events.append(event_dict)

        # Update last_seen to now (so the next read shows 0 changes)
        update_last_seen(user_email, db_path)

        return {
            "last_seen_at": last_seen,
            "current_at": now,
            "new": new_events,
            "modified": modified_events,
            "resolved": resolved_events,
            "contradicted": contradicted_events,
            "total_changes": len(new_events),
        }
    except Exception as exc:
        logger.exception("change_detection: compute_changes failed for user=%s: %s", user_email, exc)
        return {
            "last_seen_at": None,
            "current_at": datetime.now(timezone.utc).isoformat(),
            "new": [],
            "modified": [],
            "resolved": [],
            "contradicted": [],
            "total_changes": 0,
        }
