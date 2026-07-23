"""Per-source sync cursors — persisted in the database.

Stores the high-water mark for each (user, source) pair so reconnects
resume from where the last sync left off — no full re-pulls.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maestro_personal_shell.connector_framework.base import SyncCursor

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent.parent / "personal.db"),
    )


def init_cursors_table(db_path: str | None = None) -> None:
    """Create the sync_cursors table if it doesn't exist."""
    from maestro_personal_shell.db_util import get_db_conn
    if db_path is None:
        db_path = _get_db_path()
    conn = get_db_conn(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_cursors (
            user_email TEXT NOT NULL,
            source TEXT NOT NULL,
            cursor_data TEXT DEFAULT '{}',
            last_sync TEXT,
            total_synced INTEGER DEFAULT 0,
            PRIMARY KEY (user_email, source)
        )
    """)
    conn.commit()
    conn.close()


def get_cursor(user_email: str, source: str, db_path: str | None = None) -> SyncCursor:
    """Load the persisted cursor for a (user, source) pair."""
    from maestro_personal_shell.db_util import get_db_conn
    if db_path is None:
        db_path = _get_db_path()
    init_cursors_table(db_path)
    conn = get_db_conn(db_path)
    conn.row_factory = __import__("sqlite3").Row
    row = conn.execute(
        "SELECT * FROM sync_cursors WHERE user_email = ? AND source = ?",
        (user_email, source),
    ).fetchone()
    conn.close()

    if row:
        cursor_data = json.loads(row["cursor_data"]) if row["cursor_data"] else {}
        last_sync = None
        if row["last_sync"]:
            try:
                last_sync = datetime.fromisoformat(row["last_sync"])
            except (ValueError, TypeError):
                pass
        return SyncCursor(
            user_email=user_email,
            source=source,
            cursor_data=cursor_data,
            last_sync=last_sync,
            total_synced=row["total_synced"],
        )
    return SyncCursor(user_email=user_email, source=source)


def save_cursor(cursor: SyncCursor, db_path: str | None = None) -> None:
    """Persist a cursor to the database."""
    from maestro_personal_shell.db_util import get_db_conn
    if db_path is None:
        db_path = _get_db_path()
    init_cursors_table(db_path)
    conn = get_db_conn(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO sync_cursors
           (user_email, source, cursor_data, last_sync, total_synced)
           VALUES (?, ?, ?, ?, ?)""",
        (
            cursor.user_email,
            cursor.source,
            json.dumps(cursor.cursor_data),
            cursor.last_sync.isoformat() if cursor.last_sync else None,
            cursor.total_synced,
        ),
    )
    conn.commit()
    conn.close()
