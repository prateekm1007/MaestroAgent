"""
Database connection helper — P1-3 fix.

Provides a shared get_db_conn() function that creates SQLite connections
with busy_timeout=5000ms, preventing 'database is locked' errors under
concurrent access. All modules should use this instead of raw
sqlite3.connect() to ensure consistent connection configuration.

P1-3 fix (Finding S8): the independent product audit found that SQLite
connections had no busy_timeout set, causing 'database is locked' errors
when concurrent requests tried to write simultaneously. This helper
sets busy_timeout=5000 (5 seconds) on every connection, giving SQLite
time to retry before failing. The 503 Retry-After handling for lock
timeouts is implemented in api.py's exception handling.
"""

from __future__ import annotations

import sqlite3
import os
from pathlib import Path

_DEFAULT_BUSY_TIMEOUT_MS = 5000  # 5 seconds — SQLite will retry for this long


def get_db_conn(db_path: str | None = None, busy_timeout: int = _DEFAULT_BUSY_TIMEOUT_MS) -> sqlite3.Connection:
    """Create a SQLite connection with busy_timeout set.

    P1-3 fix: all SQLite connections should use this helper to ensure
    busy_timeout is consistently applied. This prevents 'database is
    locked' errors when concurrent requests access the same DB file.

    Args:
        db_path: Path to the SQLite database. If None, uses the
                 MAESTRO_PERSONAL_DB env var or the default personal.db.
        busy_timeout: Milliseconds to wait if the database is locked
                      before raising OperationalError. Default 5000 (5s).

    Returns: A sqlite3.Connection with busy_timeout configured.

    Usage:
        from maestro_personal_shell.db_util import get_db_conn
        conn = get_db_conn(db_path)
        try:
            rows = conn.execute("SELECT ...").fetchall()
        finally:
            conn.close()
    """
    if db_path is None:
        db_path = os.environ.get(
            "MAESTRO_PERSONAL_DB",
            str(Path(__file__).resolve().parent / "personal.db"),
        )
    conn = sqlite3.connect(db_path, timeout=busy_timeout / 1000.0)
    # Set busy_timeout PRAGMA as well — this is the SQLite-native way
    # and works even when the timeout parameter isn't respected.
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout}")
    # WAL mode for better concurrent read/write performance
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass  # WAL may not be available on all platforms
    return conn


def is_database_locked_error(exc: Exception) -> bool:
    """Check if an exception is a 'database is locked' error.

    P1-3 fix: used by API endpoints to return 503 Retry-After when
    the database is temporarily locked, instead of a generic 500.
    """
    if isinstance(exc, sqlite3.OperationalError):
        msg = str(exc).lower()
        return "database is locked" in msg or "database table is locked" in msg
    return False
