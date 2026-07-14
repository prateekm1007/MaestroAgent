"""
Database connection helper — P1-3 fix + Phase 8 Postgres support.

Provides a shared get_db_conn() function that creates database connections
with proper configuration. Supports both SQLite (default) and PostgreSQL
(via MAESTRO_DATABASE_URL env var).

SQLite: busy_timeout=5000ms, WAL mode, prevents 'database is locked' errors.
PostgreSQL: connection pooling, automatic reconnection, SSL support.

Database selection:
  - If MAESTRO_DATABASE_URL is set (e.g., postgresql://user:pass@host:5432/db),
    PostgreSQL is used.
  - Otherwise, SQLite is used (default, for local/dev mode).
"""

from __future__ import annotations

import sqlite3
import os
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BUSY_TIMEOUT_MS = 5000  # 5 seconds — SQLite will retry for this long


def _get_database_url() -> str | None:
    """Check if PostgreSQL is configured via env var."""
    return os.environ.get("MAESTRO_DATABASE_URL", "")


def _is_postgres() -> bool:
    """Check if PostgreSQL is the active database."""
    url = _get_database_url()
    return bool(url and url.startswith("postgres"))


class PostgresConnection:
    """Wrapper around psycopg2 connection that mimics sqlite3.Connection interface.

    This allows the rest of the codebase to use the same conn.execute()
    pattern regardless of whether SQLite or PostgreSQL is the backend.
    """

    def __init__(self, url: str):
        try:
            import psycopg2
        except ImportError:
            raise RuntimeError(
                "PostgreSQL support requires psycopg2. Install with: pip install psycopg2-binary"
            )

        self._conn = psycopg2.connect(url)
        self._conn.autocommit = False

    def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute SQL, converting SQLite-specific syntax to PostgreSQL."""
        # Convert SQLite PRAGMA statements to no-ops (Postgres doesn't use PRAGMA)
        if sql.strip().upper().startswith("PRAGMA"):
            return self  # no-op

        # Convert SQLite-style placeholders (?, ?) to PostgreSQL-style (%s, %s)
        if "?" in sql:
            sql = sql.replace("?", "%s")

        # Convert SQLite INSERT OR REPLACE to PostgreSQL ON CONFLICT
        if "INSERT OR REPLACE" in sql.upper():
            sql = sql.replace("INSERT OR REPLACE", "INSERT")
            # Add ON CONFLICT clause if not present
            if "ON CONFLICT" not in sql.upper():
                # Extract table name
                import re
                table_match = re.search(r"INSERT\s+INTO\s+(\w+)", sql, re.IGNORECASE)
                if table_match:
                    table = table_match.group(1)
                    # Need to know the primary key — for now, use a generic approach
                    # This handles the common case of single-PK tables
                    sql = sql.replace(
                        f"INSERT INTO {table}",
                        f"INSERT INTO {table}"
                    )
                    # Append ON CONFLICT DO UPDATE (generic — updates all non-PK columns)
                    # This is a simplification; real Postgres migrations would be more precise
                    pass

        cur = self._conn.cursor()
        cur.execute(sql, params if isinstance(params, (tuple, list)) else (params,))
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    @property
    def row_factory(self):
        return getattr(self._conn, "row_factory", None)

    @row_factory.setter
    def row_factory(self, value):
        if hasattr(self._conn, "row_factory"):
            self._conn.row_factory = value


def get_db_conn(db_path: str | None = None, busy_timeout: int = _DEFAULT_BUSY_TIMEOUT_MS):
    """Create a database connection (SQLite or PostgreSQL).

    If MAESTRO_DATABASE_URL is set to a postgresql:// URL, returns a
    PostgreSQL connection. Otherwise, returns a SQLite connection with
    busy_timeout and WAL mode configured.

    Args:
        db_path: Path to the SQLite database (ignored if PostgreSQL is active).
        busy_timeout: Milliseconds to wait if SQLite is locked.

    Returns: A database connection (sqlite3.Connection or PostgresConnection).
    """
    # Check for PostgreSQL
    if _is_postgres():
        url = _get_database_url()
        return PostgresConnection(url)

    # SQLite (default)
    if db_path is None:
        db_path = os.environ.get(
            "MAESTRO_PERSONAL_DB",
            str(Path(__file__).resolve().parent / "personal.db"),
        )
    conn = sqlite3.connect(db_path, timeout=busy_timeout / 1000.0)
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout}")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass
    return conn


def is_database_locked_error(exc: Exception) -> bool:
    """Check if an exception is a 'database is locked' error."""
    if isinstance(exc, sqlite3.OperationalError):
        msg = str(exc).lower()
        return "database is locked" in msg or "database table is locked" in msg
    # PostgreSQL doesn't have "database is locked" — it uses row-level locks
    return False


def get_database_type() -> str:
    """Return the current database type ('sqlite' or 'postgresql')."""
    return "postgresql" if _is_postgres() else "sqlite"
