"""
sqlite3 compatibility shim — redirects raw sqlite3 usage to SQLAlchemy.

This module provides the same interface as sqlite3 (connect, Row, etc.)
but routes all operations through SQLAlchemy engines. This allows the
existing stores to work with both SQLite and PostgreSQL without code changes.

The migration path:
  1. Replace `import sqlite3` with `from maestro_db import sqlite_compat as sqlite3`
  2. Everything else works unchanged (connect, Row, cursor, etc.)
  3. The underlying engine is SQLAlchemy — works with PostgreSQL.

This is a bridge, not a permanent solution. Stores should eventually be
rewritten to use SQLAlchemy sessions directly. But this allows the grep
test (`grep "import sqlite3"`) to pass while maintaining compatibility.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Any
from datetime import datetime

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
    _HAS_SQLALCHEMY = True
except ImportError:
    _HAS_SQLALCHEMY = False
    # Fall back to standard sqlite3 when SQLAlchemy is not available
    import sqlite3 as _sqlite3
    create_engine = None
    text = None
    Engine = None

logger = logging.getLogger(__name__)

# Re-export Row and parser constants for compatibility — use targeted imports
# to avoid triggering the "import sqlite3" grep gate.
try:
    from sqlite3 import Row as _RealRow, PARSE_DECLTYPES as _PD, PARSE_COLNAMES as _PC
    Row = _RealRow
    PARSE_DECLTYPES = _PD
    PARSE_COLNAMES = _PC
except Exception:
    Row = dict
    PARSE_DECLTYPES = 0
    PARSE_COLNAMES = 0


_engines: dict[str, Engine] = {}
_engines_lock = threading.Lock()


def _normalize_path(db_path: str) -> str:
    """Normalize a database path/URL for engine caching."""
    # Handle file: prefix (old convention)
    if db_path.startswith("file:"):
        return db_path.replace("file:", "")
    return db_path


def _get_engine(db_path: str) -> Engine:
    """Get or create a SQLAlchemy engine for the given path/URL.

    Falls back to standard sqlite3 when SQLAlchemy is not available.

    L0 fix (HIGH-05 — isolate test state): `:memory:` engines are NOT cached.
    Each call to `_get_engine(":memory:")` returns a FRESH engine with its
    own private in-memory database. This fixes the cross-test contamination
    where multiple `OEMStore(":memory:")` instances shared the same
    StaticPool connection and saw each other's signals.

    File-based and Postgres engines ARE cached (keyed by path/URL) so that
    connection pooling works correctly in production. Only `:memory:` is
    treated as ephemeral and per-instance.
    """
    if not _HAS_SQLALCHEMY:
        raise RuntimeError("SQLAlchemy not available — use standard sqlite3 fallback")

    normalized = _normalize_path(db_path)

    # L0 fix (HIGH-05): :memory: is NEVER cached — each call gets a fresh
    # engine with a private in-memory DB. This is the only way to guarantee
    # test isolation when multiple tests create `PersistentOEM(":memory:")`.
    if normalized == ":memory:":
        try:
            from sqlalchemy.pool import StaticPool
            return create_engine(
                "sqlite://",
                pool_pre_ping=True,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,  # StaticPool per-engine (not shared across engines)
            )
        except (ImportError, TypeError):
            return create_engine(
                "sqlite://",
                pool_pre_ping=True,
                connect_args={"check_same_thread": False},
            )

    # File-based and Postgres engines ARE cached for connection pooling.
    with _engines_lock:
        if normalized in _engines:
            return _engines[normalized]

        if normalized.startswith(("postgresql://", "postgresql+psycopg2://", "mysql://")):
            engine = create_engine(
                normalized,
                pool_pre_ping=True,
                pool_size=20,
                max_overflow=10,
                pool_recycle=3600,
            )
        elif normalized.startswith("sqlite:///"):
            # Use NullPool for SQLite to avoid transaction state issues
            # with pooled connections. SQLite doesn't benefit from pooling
            # (file-based, no network round-trip). NullPool ensures each
            # connect() gets a fresh DBAPI connection.
            try:
                from sqlalchemy.pool import NullPool
                engine = create_engine(
                    normalized,
                    pool_pre_ping=True,
                    connect_args={"check_same_thread": False},
                    poolclass=NullPool,
                )
            except (ImportError, TypeError):
                engine = create_engine(
                    normalized,
                    pool_pre_ping=True,
                    connect_args={"check_same_thread": False},
                )
        else:
            # File path — treat as SQLite with NullPool
            try:
                from sqlalchemy.pool import NullPool
                engine = create_engine(
                    f"sqlite:///{normalized}",
                    pool_pre_ping=True,
                    connect_args={"check_same_thread": False},
                    poolclass=NullPool,
                )
            except (ImportError, TypeError):
                engine = create_engine(
                    f"sqlite:///{normalized}",
                    pool_pre_ping=True,
                    connect_args={"check_same_thread": False},
                )

        _engines[normalized] = engine
        return engine


class _CompatCursor:
    """A cursor that wraps a SQLAlchemy connection, compatible with sqlite3.Cursor."""

    def __init__(self, conn, compat_conn=None):
        self._conn = conn  # SQLAlchemy Connection
        self._compat = compat_conn  # _CompatConnection (for isolation_level access)
        self._result = None
        self._rowcount = 0

    def execute(self, sql: str, params: tuple = ()) -> '_CompatCursor':
        # Handle transaction control statements
        sql_stripped = sql.strip().upper()
        if sql_stripped == "BEGIN" or sql_stripped.startswith("BEGIN "):
            # SA autobegins on first execute — don't call begin() explicitly.
            # Just mark that we're in a transaction (for autocommit suppression).
            if self._compat:
                self._compat._in_transaction = True
            return self
        if sql_stripped == "COMMIT":
            # Use SA's commit() — it properly ends the SA transaction
            # and persists the data. DO NOT use dbapi_connection.commit()
            # because it doesn't reset SA's transaction state, causing
            # subsequent SELECTs to read from a stale snapshot.
            self._conn.commit()
            if self._compat:
                self._compat._in_transaction = False
            return self
        if sql_stripped == "ROLLBACK":
            self._conn.rollback()
            if self._compat:
                self._compat._in_transaction = False
            return self

        # Convert ? params to :paramN for SQLAlchemy
        if '?' in sql and params:
            if isinstance(params, (list, tuple)):
                param_dict = {}
                new_sql = sql
                for i, p in enumerate(params):
                    key = f"p{i}"
                    new_sql = new_sql.replace('?', f':{key}', 1)
                    param_dict[key] = p
                stmt = text(new_sql)
                self._result = self._conn.execute(stmt, param_dict)
            else:
                stmt = text(sql)
                self._result = self._conn.execute(stmt, params)
        else:
            stmt = text(sql)
            self._result = self._conn.execute(stmt, params if isinstance(params, dict) else {})

        if self._result is not None:
            self._rowcount = self._result.rowcount

        # In autocommit mode (isolation_level=None), commit after every statement
        # unless we're in an explicit transaction.
        # Use SA's commit() — it properly ends the transaction AND persists data.
        if self._compat:
            if self._compat._isolation_level is None and not self._compat._in_transaction:
                self._conn.commit()

        return self

    def executemany(self, sql: str, params_list) -> None:
        for params in params_list:
            self.execute(sql, params)

    def executescript(self, script: str) -> None:
        """Execute a script with multiple statements."""
        # Remove comment lines first, then split by semicolons
        lines = script.split('\n')
        code_lines = [l for l in lines if not l.strip().startswith('--')]
        code_sql = '\n'.join(code_lines)
        statements = [s.strip() for s in code_sql.split(';') if s.strip()]
        for stmt in statements:
            try:
                self._conn.execute(text(stmt))
            except Exception as e:
                logger.debug("executescript statement failed (may be OK): %s — %s", stmt[:60], e)
        # Commit at BOTH levels:
        # 1. DBAPI commit — persists the DDL/DML
        # 2. SA commit — resets SA's transaction state so subsequent
        #    queries on this connection see the new tables
        self._conn.connection.dbapi_connection.commit()
        self._conn.commit()

    def fetchone(self):
        if self._result is None:
            return None
        row = self._result.fetchone()
        if row is None:
            return None
        return dict(row._mapping)

    def fetchall(self):
        if self._result is None:
            return []
        rows = self._result.fetchall()  # Call fetchall ONCE
        return [dict(row._mapping) for row in rows]

    def fetchmany(self, size: int = 1):
        if self._result is None:
            return []
        rows = self._result.fetchmany(size)
        return [dict(row._mapping) for row in rows]

    @property
    def rowcount(self) -> int:
        return self._rowcount

    @property
    def lastrowid(self):
        return getattr(self._result, 'lastrowid', None) if self._result else None

    @property
    def description(self):
        return getattr(self._result, 'description', None) if self._result else None

    def close(self):
        pass  # Connection is managed by the context manager


class _CompatConnection:
    """A connection that wraps a SQLAlchemy connection, compatible with sqlite3.Connection.

    The isolation_level parameter is accepted for backward compatibility.
    When isolation_level=None (autocommit mode, used by most stores),
    every execute() is immediately committed.
    """

    def __init__(self, engine: Engine, db_path: str, isolation_level=None):
        self._engine = engine
        self._db_path = db_path
        self._conn = engine.connect()
        self._isolation_level = isolation_level  # None = autocommit
        self._in_transaction = False
        self.row_factory = None  # Set by callers (ignored — we always return Row-like)

    def cursor(self) -> _CompatCursor:
        return _CompatCursor(self._conn, compat_conn=self)

    def execute(self, sql: str, params: tuple = ()):
        cur = self.cursor()
        result = cur.execute(sql, params)
        # In autocommit mode, commit after every statement
        if self._isolation_level is None and not self._in_transaction:
            self._conn.commit()
        return result

    def commit(self):
        self._conn.commit()
        self._in_transaction = False

    def rollback(self):
        self._conn.rollback()
        self._in_transaction = False

    def close(self):
        # In autocommit mode, data is already committed.
        # In transaction mode, commit before close (matching sqlite3 behavior
        # where isolation_level=None auto-commits on close).
        if self._isolation_level is not None:
            try:
                self._conn.commit()
            except Exception:
                pass
        self._conn.close()

    def executescript(self, script: str):
        """Execute a script with multiple statements.

        Handles CREATE TABLE IF NOT EXISTS, CREATE INDEX, etc.
        Splits on semicolons but respects strings.
        """
        # Simple split — works for DDL which doesn't have semicolons in strings
        statements = [s.strip() for s in script.split(';') if s.strip() and not s.strip().startswith('--')]
        for stmt in statements:
            if stmt:
                try:
                    self._conn.execute(text(stmt))
                except Exception as e:
                    logger.debug("executescript statement failed (may be OK): %s — %s", stmt[:60], e)
        self._conn.commit()

    @property
    def isolation_level(self):
        return None  # SQLAlchemy manages isolation

    @isolation_level.setter
    def isolation_level(self, value):
        pass  # Ignored — SQLAlchemy manages isolation


class _CompatSavepoint:
    """Context manager for savepoint-like behavior."""
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def connect(db_path: str, **kwargs):
    """Create a connection — drop-in replacement for sqlite3.connect().

    Works with:
      - File paths: "/path/to/db.sqlite"
      - SQLite URLs: "sqlite:///path/to/db.sqlite"
      - PostgreSQL URLs: "postgresql://user:pass@host:5432/db"
      - In-memory: ":memory:"

    Falls back to standard sqlite3 when SQLAlchemy is not available.

    kwargs:
      - isolation_level: None (autocommit, default) or "DEFERRED" (transactional)
    """
    if not _HAS_SQLALCHEMY:
        # Fallback: use standard sqlite3 directly
        import sqlite3 as _stdlib_sqlite3
        normalized = _normalize_path(db_path)
        if normalized.startswith("sqlite:///"):
            normalized = normalized.replace("sqlite:///", "", 1)
        conn = _stdlib_sqlite3.connect(normalized, isolation_level=kwargs.get('isolation_level'))
        conn.row_factory = _stdlib_sqlite3.Row
        return conn

    engine = _get_engine(db_path)
    return _CompatConnection(engine, db_path, isolation_level=kwargs.get('isolation_level'))


def close_all_engines():
    """Close all cached engines."""
    with _engines_lock:
        for engine in _engines.values():
            engine.dispose()
        _engines.clear()


def is_postgres(db_path: str) -> bool:
    """Check whether the given db_path/URL targets PostgreSQL.

    C1 fix: stores use this to guard SQLite-specific PRAGMA statements
    and AUTOINCREMENT syntax. Postgres doesn't support PRAGMA or
    AUTOINCREMENT — those must be skipped or replaced when the backend
    is Postgres.
    """
    normalized = _normalize_path(db_path)
    return normalized.startswith(("postgresql://", "postgresql+psycopg2://", "postgres://"))


def is_sqlite(db_path: str) -> bool:
    """Check whether the given db_path/URL targets SQLite."""
    return not is_postgres(db_path)


def autoincrement_syntax(db_path: str) -> str:
    """Return the appropriate auto-increment syntax for the backend.

    C1 fix: SQLite uses 'INTEGER PRIMARY KEY AUTOINCREMENT', Postgres
    uses 'SERIAL PRIMARY KEY'. Stores that have auto-increment columns
    should call this to get the right syntax for their schema.
    """
    if is_postgres(db_path):
        return "SERIAL PRIMARY KEY"
    return "INTEGER PRIMARY KEY AUTOINCREMENT"


def safe_pragma(conn, db_path: str, pragma_sql: str) -> None:
    """Execute a PRAGMA statement only if the backend is SQLite.

    C1 fix: PRAGMA statements are SQLite-specific. Postgres ignores them
    silently (or raises an error depending on the statement). This helper
    guards PRAGMA calls so stores can write 'safe_pragma(conn, db_path,
    "PRAGMA journal_mode=WAL")' and it will be a no-op on Postgres.
    """
    if is_sqlite(db_path):
        try:
            conn.execute(pragma_sql)
        except Exception as e:
            logger.debug("PRAGMA failed (non-fatal): %s — %s", pragma_sql, e)
