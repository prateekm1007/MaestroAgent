"""
Database helper — bridge layer for migrating from sqlite3 to SQLAlchemy.

Provides a cursor-like interface that works with both SQLite and PostgreSQL.
Each store can migrate from `import sqlite3` to this helper with minimal
code changes — same execute/fetchall pattern, but backed by SQLAlchemy.

Key design: uses SQLAlchemy's text() for SQL with proper parameter binding.
Supports both ? (SQLite) and :param (SQLAlchemy) style parameters.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_engines: dict[str, Engine] = {}


class DBRow(dict):
    """A row that supports both dict access and attribute access."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{key}'")


class DBCursor:
    """A cursor-like wrapper around a SQLAlchemy connection.

    Provides the same interface as sqlite3.Cursor:
      - execute(sql, params)
      - fetchone() -> DBRow | None
      - fetchall() -> list[DBRow]
      - rowcount
    """

    def __init__(self, conn):
        self._conn = conn
        self._result = None
        self._rowcount = 0

    def execute(self, sql: str, params: tuple = ()) -> 'DBCursor':
        # Convert ? params to :param0, :param1, ... for SQLAlchemy
        if '?' in sql and params:
            param_dict = {}
            new_sql = sql
            for i, p in enumerate(params):
                key = f"param{i}"
                new_sql = new_sql.replace('?', f':{key}', 1)
                param_dict[key] = p
            stmt = text(new_sql)
            self._result = self._conn.execute(stmt, param_dict)
        else:
            stmt = text(sql)
            self._result = self._conn.execute(stmt, params if isinstance(params, dict) else {})

        if self._result is not None:
            self._rowcount = self._result.rowcount
        return self

    def fetchone(self) -> DBRow | None:
        if self._result is None:
            return None
        row = self._result.fetchone()
        if row is None:
            return None
        return DBRow(row._mapping)

    def fetchall(self) -> list[DBRow]:
        if self._result is None:
            return []
        return [DBRow(row._mapping) for row in self._result.fetchall()]

    @property
    def rowcount(self) -> int:
        return self._rowcount

    @property
    def lastrowid(self) -> int | None:
        return getattr(self._result, 'lastrowid', None) if self._result else None


def _get_engine(db_path_or_url: str) -> Engine:
    """Get or create a SQLAlchemy engine."""
    if db_path_or_url in _engines:
        return _engines[db_path_or_url]

    if db_path_or_url.startswith(("postgresql://", "postgresql+psycopg2://", "mysql://")):
        engine = create_engine(
            db_path_or_url,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=10,
            pool_recycle=3600,
        )
    elif db_path_or_url.startswith("sqlite:///"):
        engine = create_engine(
            db_path_or_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
    else:
        engine = create_engine(
            f"sqlite:///{db_path_or_url}",
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )

    _engines[db_path_or_url] = engine
    return engine


@contextmanager
def db_cursor(db_path_or_url: str) -> Generator[DBCursor, None, None]:
    """Context manager yielding a DBCursor.

    Drop-in replacement for:
        conn = sqlite3.connect(db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("BEGIN")
        ...
        cur.execute("COMMIT")

    Usage:
        with db_cursor(db_path) as cur:
            cur.execute("SELECT * FROM predictions WHERE status = ?", ("pending",))
            for row in cur.fetchall():
                print(row["status"])
    """
    engine = _get_engine(db_path_or_url)
    conn = engine.connect()
    try:
        cur = DBCursor(conn)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def db_execute(db_path_or_url: str, sql: str, params: tuple = ()) -> list[DBRow]:
    """Execute a query and return all rows."""
    with db_cursor(db_path_or_url) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def db_execute_one(db_path_or_url: str, sql: str, params: tuple = ()) -> DBRow | None:
    """Execute and return first row."""
    with db_cursor(db_path_or_url) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def db_execute_write(db_path_or_url: str, sql: str, params: tuple = ()) -> int:
    """Execute a write query. Returns rowcount."""
    with db_cursor(db_path_or_url) as cur:
        cur.execute(sql, params)
        return cur.rowcount


def close_all_engines() -> None:
    """Close all cached engines."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


def get_db_url_for_learning() -> str:
    """Get the database URL/path for the learning database.

    Replaces the old file-path-based pattern which was broken for
    PostgreSQL connection strings.
    """
    from maestro_db.base import get_db_path_for_file_db
    return get_db_path_for_file_db("learning.db")
