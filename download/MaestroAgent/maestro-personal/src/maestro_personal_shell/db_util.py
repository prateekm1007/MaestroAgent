"""Database connection helper — P1-3 fix + Phase 8 Postgres support.

P40 fix (auditor 2026-07-24): production reliability is a trust property.
The SQLite 503 "database is locked" errors under concurrent load are the
PRODUCT's concurrency ceiling, not a gate hygiene issue. This module now
includes:
  - WAL mode (already present — allows concurrent reads)
  - busy_timeout increased from 5s to 30s (the auditor found 31s under
    5 concurrent; 30s gives writes a fighting chance)
  - synchronous = NORMAL (WAL + NORMAL is safe and much faster than FULL)
  - A process-level write mutex that serializes writes in-process, so
    concurrent requests don't each open a new connection and contend at
    the SQLite level. This is the "write queue" pattern recommended for
    SQLite in concurrent server environments.
"""

from __future__ import annotations

import sqlite3
import os
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BUSY_TIMEOUT_MS = 30000  # 30 seconds — was 5s, increased for P40

# Process-level write mutex — serializes writes so concurrent requests
# don't each open a new connection and contend at the SQLite level.
# This is the "write queue" pattern for SQLite in concurrent servers.
_write_lock = threading.Lock()


def _get_database_url() -> str | None:
    """Check if PostgreSQL is configured via env var."""
    return os.environ.get("MAESTRO_DATABASE_URL", "")


def default_sqlite_path() -> str:
    """Return the canonical SQLite path — matches api.py's DB_PATH resolution."""
    env = os.environ.get("MAESTRO_PERSONAL_DB")
    if env:
        return env
    return str(Path(__file__).resolve().parent / "personal.db")


def _is_postgres() -> bool:
    """Check if PostgreSQL is the active database."""
    url = _get_database_url()
    return bool(url and url.startswith("postgres"))


class PostgresConnection:
    """Wrapper around psycopg2 connection that mimics sqlite3.Connection interface.

    This allows the rest of the codebase to use the same conn.execute()
    pattern regardless of whether SQLite or PostgreSQL is the backend.

    K3-DATA-002 / TICKET-13 fix (2026-07-25): the INSERT OR REPLACE →
    ON CONFLICT conversion was previously a `pass` (line 101), which meant
    any upsert would fail with a duplicate-key error on Postgres. Now we
    introspect the table's primary key from pg_constraint and build the
    ON CONFLICT clause dynamically. PK lookups are cached per-table.
    """

    def __init__(self, url: str):
        try:
            import psycopg2
        except ImportError:
            raise RuntimeError(
                "PostgreSQL support requires psycopg2. Install with: pip install psycopg2-binary"
            )
        # K3-DATA-002 fix: use DictCursorFactory so rows support both
        # `row["col"]` (sqlite3.Row pattern) and `row[0]` (tuple pattern).
        # The codebase sets `conn.row_factory = sqlite3.Row` in 14 places
        # and accesses rows by column name; DictCursor makes that work on
        # Postgres without touching any caller.
        try:
            from psycopg2.extras import DictCursor
            self._conn = psycopg2.connect(url, cursor_factory=DictCursor)
        except ImportError:
            self._conn = psycopg2.connect(url)
        self._conn.autocommit = False
        self._pk_cache: dict[str, list[str]] = {}
        # Per-connection cursor for metadata lookups (PK introspection).
        # We use a separate cursor so we don't disturb the caller's transaction.
        self._meta_cursor = self._conn.cursor()

    def _get_primary_key(self, table: str) -> list[str]:
        """Return the list of PK column names for a table. Cached per-table.

        Uses pg_constraint + pg_attribute to find the primary key columns.
        Returns [] if the table has no PK (in which case ON CONFLICT is impossible).
        """
        if table in self._pk_cache:
            return self._pk_cache[table]
        try:
            self._meta_cursor.execute(
                """
                SELECT a.attname
                FROM pg_constraint c
                JOIN pg_attribute a
                  ON a.attrelid = c.conrelid
                 AND a.attnum = ANY(c.conkey)
                WHERE c.contype = 'p'
                  AND c.conrelid = %s::regclass
                ORDER BY array_position(c.conkey, a.attnum)
                """,
                (table,),
            )
            cols = [r[0] for r in self._meta_cursor.fetchall()]
        except Exception as e:
            logger.debug("PK lookup for %s failed: %s", table, e)
            cols = []
        self._pk_cache[table] = cols
        return cols

    @staticmethod
    def _parse_insert_columns(sql: str, table: str) -> list[str] | None:
        """Parse the column list out of `INSERT INTO table (col1, col2, ...) VALUES ...`.

        Returns the list of column names (lowercased for comparison), or None if
        the INSERT has no explicit column list (e.g. `INSERT INTO table VALUES (...)`).
        """
        import re
        # Match `INSERT [OR REPLACE|OR IGNORE] INTO <table> (<cols>) VALUES`
        m = re.search(
            r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+" + re.escape(table) + r"\s*\(([^)]+)\)\s*VALUES",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return None
        return [c.strip().strip('"').strip("'").lower() for c in m.group(1).split(",")]

    def _convert_insert_or_replace(self, sql: str) -> str:
        """Convert `INSERT OR REPLACE INTO t (cols) VALUES (...)` to Postgres UPSERT.

        Strategy: parse the table + columns, look up the PK, build
        `ON CONFLICT (pk_cols) DO UPDATE SET non_pk_cols = EXCLUDED.non_pk_cols`.
        If the table has no PK or the column list can't be parsed, fall back to
        `ON CONFLICT DO NOTHING` (safer than failing — the caller's intent was
        "insert or replace", and DO NOTHING at least doesn't crash).
        """
        import re
        table_match = re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)", sql, re.IGNORECASE)
        if not table_match:
            return sql.replace("INSERT OR REPLACE", "INSERT", 1)  # defensive
        table = table_match.group(1)
        pk_cols = self._get_primary_key(table)
        insert_cols = self._parse_insert_columns(sql, table) or []

        # Strip the "OR REPLACE" so Postgres accepts the INSERT
        sql = re.sub(r"INSERT\s+OR\s+REPLACE\s+INTO", "INSERT INTO", sql, count=1, flags=re.IGNORECASE)

        if not pk_cols or not insert_cols:
            # No PK or no column list — DO NOTHING is the safe fallback
            return sql.rstrip(";").rstrip() + " ON CONFLICT DO NOTHING"

        # Build ON CONFLICT (pk) DO UPDATE SET non_pk = EXCLUDED.non_pk
        non_pk_cols = [c for c in insert_cols if c not in [p.lower() for p in pk_cols]]
        pk_list = ", ".join(f'"{c}"' for c in pk_cols)
        if non_pk_cols:
            set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in non_pk_cols)
            on_conflict = f" ON CONFLICT ({pk_list}) DO UPDATE SET {set_clause}"
        else:
            # All columns are PK columns — DO NOTHING (no non-PK to update)
            on_conflict = f" ON CONFLICT ({pk_list}) DO NOTHING"
        return sql.rstrip(";").rstrip() + on_conflict

    def _convert_insert_or_ignore(self, sql: str) -> str:
        """Convert `INSERT OR IGNORE INTO t (...) VALUES (...)` to Postgres ON CONFLICT DO NOTHING."""
        import re
        table_match = re.search(r"INSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)", sql, re.IGNORECASE)
        if not table_match:
            return sql.replace("INSERT OR IGNORE", "INSERT", 1)
        table = table_match.group(1)
        pk_cols = self._get_primary_key(table)
        sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, count=1, flags=re.IGNORECASE)
        if pk_cols:
            pk_list = ", ".join(f'"{c}"' for c in pk_cols)
            return sql.rstrip(";").rstrip() + f" ON CONFLICT ({pk_list}) DO NOTHING"
        return sql.rstrip(";").rstrip() + " ON CONFLICT DO NOTHING"

    def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute SQL, converting SQLite-specific syntax to PostgreSQL."""
        import re
        sql_upper = sql.strip().upper()

        # SQLite PRAGMA → no-op (Postgres doesn't use PRAGMA)
        if sql_upper.startswith("PRAGMA"):
            return self  # no-op

        # Convert SQLite-style placeholders (?, ?) to PostgreSQL-style (%s, %s)
        if "?" in sql:
            sql = sql.replace("?", "%s")

        # Convert SQLite CREATE TABLE syntax to Postgres-compatible:
        # `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
        # (Postgres doesn't support AUTOINCREMENT; SERIAL creates an implicit
        # sequence + int4 column. BIGINT PRIMARY KEY AUTOINCREMENT → BIGSERIAL.)
        if "AUTOINCREMENT" in sql_upper:
            sql = re.sub(
                r"BIGINT\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
                "BIGSERIAL PRIMARY KEY",
                sql,
                flags=re.IGNORECASE,
            )
            sql = re.sub(
                r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
                "SERIAL PRIMARY KEY",
                sql,
                flags=re.IGNORECASE,
            )
            # Strip any remaining bare AUTOINCREMENT keywords (defensive)
            sql = re.sub(r"\s+AUTOINCREMENT\b", "", sql, flags=re.IGNORECASE)

        # Convert SQLite INSERT OR REPLACE → Postgres UPSERT (ON CONFLICT DO UPDATE)
        if "INSERT OR REPLACE" in sql_upper:
            sql = self._convert_insert_or_replace(sql)
        # Convert SQLite INSERT OR IGNORE → Postgres ON CONFLICT DO NOTHING
        elif "INSERT OR IGNORE" in sql_upper:
            sql = self._convert_insert_or_ignore(sql)

        cur = self._conn.cursor()
        cur.execute(sql, params if isinstance(params, (tuple, list)) else (params,))
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        try:
            try:
                self._meta_cursor.close()
            except Exception:
                pass
            self._conn.close()
        except Exception as e:
            logger.debug("close failed: %s", e)

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
        # P40: synchronous = NORMAL is safe with WAL and much faster than FULL.
        # This reduces fsync calls on writes, which is the main bottleneck
        # under concurrent load.
        conn.execute("PRAGMA synchronous = NORMAL")
    except Exception as e:
        logger.debug("execute failed: %s", e)
    return conn


def get_write_lock() -> threading.Lock:
    """Return the process-level write mutex for serializing SQLite writes.

    Callers that perform writes should acquire this lock before writing:

        with get_write_lock():
            conn = get_db_conn()
            conn.execute("INSERT ...")
            conn.commit()
            conn.close()

    This prevents concurrent in-process writes from contending at the
    SQLite level, which is the root cause of "database is locked" errors.
    """
    return _write_lock


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
